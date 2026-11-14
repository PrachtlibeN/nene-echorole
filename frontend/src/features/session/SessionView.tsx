import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  type ScenarioOut,
  type SessionOut,
  type SpeechMeta,
  type TurnOut,
} from "../../api/client";
import { ErrorAlert } from "../../components/ErrorAlert";
import {
  createSpeechSynthesisController,
  type SpeechSequenceItem,
} from "../../utils/speech";
import { PushToTalkButton } from "./PushToTalkButton";
import { TranscriptReview } from "./TranscriptReview";
import { TurnList } from "./TurnList";
import { TypedInputFallback } from "./TypedInputFallback";
import type { InteractionMode, PushToTalkState } from "./types";

const EMPTY_TURNS: TurnOut[] = [];

interface SessionViewProps {
  initialSession: SessionOut;
  scenario: ScenarioOut;
  initialTurns?: TurnOut[];
  initialTurn?: TurnOut | null;
  onViewFeedback: (sessionId: string) => void;
  onEndSessionComplete?: (session: SessionOut) => void;
  /** Test hook to inject custom audio blob creation */
  onMockRecordAudio?: () => Promise<Blob>;
}

export const SessionView: React.FC<SessionViewProps> = ({
  initialSession,
  scenario,
  initialTurns,
  initialTurn,
  onViewFeedback,
  onEndSessionComplete,
  onMockRecordAudio,
}) => {
  const [session, setSession] = useState<SessionOut>(initialSession);
  const openingTurns = useMemo(
    () => initialTurns ?? (initialTurn ? [initialTurn] : EMPTY_TURNS),
    [initialTurns, initialTurn],
  );
  const [turns, setTurns] = useState<TurnOut[]>(
    openingTurns,
  );
  const [state, setState] = useState<PushToTalkState>(
    openingTurns.some((turn) => turn.speaker === "interviewer")
      ? "speaking"
      : "idle",
  );
  const [mode, setMode] = useState<InteractionMode>("hold");
  const [recordingSeconds, setRecordingSeconds] = useState<number>(0);
  const [maxAudioSeconds, setMaxAudioSeconds] = useState<number>(120);

  const [reviewText, setReviewText] = useState<string>("");
  const [reviewSpeechMeta, setReviewSpeechMeta] = useState<SpeechMeta | null>(null);

  const [isMicDenied, setIsMicDenied] = useState<boolean>(false);
  const [error, setError] = useState<unknown | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const speechRef = useRef(createSpeechSynthesisController());

  // Fetch speech status limits on mount
  useEffect(() => {
    let mounted = true;
    api
      .getSpeechStatus()
      .then((status) => {
        if (!mounted) return;
        if (status.limits?.max_audio_seconds) {
          setMaxAudioSeconds(status.limits.max_audio_seconds);
        }
        if (status.stt?.status === "unavailable") {
          setIsMicDenied(true);
        }
      })
      .catch(() => {
        // Fallback to default 120s if endpoint fails
      });
    const speech = speechRef.current;
    return () => {
      mounted = false;
      if (timerRef.current) clearInterval(timerRef.current);
      speech.stop();
    };
  }, []);

  // Speak opening panel turns in order when starting a session.
  useEffect(() => {
    const openingInterviewerTurns = openingTurns.filter(
      (turn) => turn.speaker === "interviewer",
    );
    if (openingInterviewerTurns.length > 0) {
      setState("speaking");
      speechRef.current.speakSequence(
        openingInterviewerTurns.map((turn) =>
          speechItemForTurn(turn, scenario),
        ),
        () => setState("idle"),
        () => setState("idle"),
      );
    }
  }, [openingTurns, scenario]);

  // Push-to-talk: Start recording
  const handleStartRecording = async () => {
    if (state !== "idle") return;
    setError(null);

    // If a mock audio recorder hook is provided (for tests)
    if (onMockRecordAudio) {
      setState("recording");
      setRecordingSeconds(0);
      startTimer();
      return;
    }

    try {
      if (
        typeof navigator === "undefined" ||
        !navigator.mediaDevices ||
        !navigator.mediaDevices.getUserMedia
      ) {
        throw new Error("Microphone API is not supported in this browser.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];

      let mimeType = "audio/webm";
      if (typeof MediaRecorder !== "undefined" && !MediaRecorder.isTypeSupported("audio/webm")) {
        mimeType = "";
      }

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const audioBlob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        await processAudioTranscription(audioBlob);
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setState("recording");
      setRecordingSeconds(0);
      startTimer();
    } catch (err: unknown) {
      setIsMicDenied(true);
      setError(
        err instanceof Error
          ? err
          : new Error("Microphone access was denied or could not be initialized."),
      );
    }
  };

  const startTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setRecordingSeconds((prev) => {
        const next = prev + 1;
        if (next >= maxAudioSeconds) {
          // Auto-stop at max duration limit
          handleStopRecording();
        }
        return next;
      });
    }, 1000);
  };

  // Push-to-talk: Stop recording
  const handleStopRecording = async () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    if (onMockRecordAudio) {
      setState("transcribing");
      try {
        const audioBlob = await onMockRecordAudio();
        await processAudioTranscription(audioBlob);
      } catch (err) {
        setError(err);
        setState("idle");
      }
      return;
    }

    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "recording"
    ) {
      setState("transcribing");
      mediaRecorderRef.current.stop();
    } else {
      setState("idle");
    }
  };

  // Process transcription via POST /api/v1/speech/transcribe
  const processAudioTranscription = async (blob: Blob) => {
    setState("transcribing");
    setError(null);
    try {
      const transcription = await api.transcribeAudio(blob);
      setReviewText(transcription.text);
      setReviewSpeechMeta({
        duration_ms: transcription.duration_ms,
        avg_confidence: transcription.avg_confidence,
        word_count: transcription.word_count,
        language: transcription.language,
      });
      // Transition to review: No auto-send!
      setState("review");
    } catch (err) {
      if (err instanceof ApiError && (err.code === "STT_UNAVAILABLE" || err.code === "STT_NOT_READY")) {
        setIsMicDenied(true);
      }
      setError(err);
      setState("idle");
    }
  };

  // Submit candidate turn to POST /api/v1/sessions/{id}/turns
  const submitTurn = async (
    text: string,
    source: "speech" | "typed",
    speechMeta: SpeechMeta | null,
  ) => {
    setState("sending");
    setError(null);
    try {
      // Waiting reply from interviewer
      setState("waiting_reply");

      const response = await api.submitTurn(session.id, {
        text,
        source,
        speech_meta: source === "speech" ? speechMeta : null,
      });

      const interviewerTurns =
        response.interviewer_turns && response.interviewer_turns.length > 0
          ? response.interviewer_turns
          : [response.interviewer_turn];

      setTurns((prev) => [...prev, response.candidate_turn, ...interviewerTurns]);

      // Update session
      setSession(response.session);

      // Clear review state
      setReviewText("");
      setReviewSpeechMeta(null);

      // Play interviewer's reply with SpeechSynthesis
      if (interviewerTurns.some((turn) => turn.text)) {
        setState("speaking");
        speechRef.current.speakSequence(
          interviewerTurns.map((turn) => speechItemForTurn(turn, scenario)),
          () => setState("idle"),
          () => setState("idle"),
        );
      } else {
        setState("idle");
      }
    } catch (err) {
      if (err instanceof ApiError && (err.code === "STT_UNAVAILABLE" || err.code === "STT_NOT_READY")) {
        setIsMicDenied(true);
      }
      setError(err);
      setState("idle");
    }
  };

  // User confirms sending review text
  const handleSendReviewedSpeech = (text: string) => {
    submitTurn(text, "speech", reviewSpeechMeta);
  };

  // User discards review
  const handleDiscardReview = () => {
    setReviewText("");
    setReviewSpeechMeta(null);
    setState("idle");
  };

  // User submits typed text fallback
  const handleSendTyped = (text: string) => {
    submitTurn(text, "typed", null);
  };

  // Mute SpeechSynthesis
  const handleMuteSpeaker = () => {
    speechRef.current.stop();
    setState("idle");
  };

  // Replay turn voice
  const handleReplayTurn = (text: string, speakerId?: string) => {
    setState("speaking");
    const persona = (scenario.definition.personas ?? []).find(
      (panelPersona) => panelPersona.id === speakerId,
    );
    speechRef.current.speakSequence(
      [{ text, voiceGender: persona?.voice_gender }],
      () => setState("idle"),
      () => setState("idle"),
    );
  };

  // End session manually
  const handleEndSession = async () => {
    setError(null);
    try {
      speechRef.current.stop();
      const endedSession = await api.endSession(session.id);
      setSession(endedSession);
      setState("idle");
      onEndSessionComplete?.(endedSession);
    } catch (err) {
      setError(err);
    }
  };

  const isSessionEnded = session.status === "ended" || session.status === "abandoned";
  const interviewerName = scenario.definition.persona.name;
  const personas = scenario.definition.personas ?? [];

  return (
    <div className="flex flex-col space-y-4">
      {/* Session Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                isSessionEnded ? "bg-slate-400" : "bg-emerald-500 animate-pulse"
              }`}
            />
            <h2 className="text-base font-bold text-slate-900">
              {scenario.title}
            </h2>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
              {session.status.toUpperCase()}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            {personas.length === 2 ? (
              <>
                Panel:{" "}
                {personas.map((persona, index) => (
                  <React.Fragment key={persona.id}>
                    {index > 0 ? " and " : ""}
                    <span className="font-semibold text-slate-700">
                      {persona.name}
                    </span>{" "}
                    ({persona.role_title})
                  </React.Fragment>
                ))}
              </>
            ) : (
              <>
                Interviewer:{" "}
                <span className="font-semibold text-slate-700">{interviewerName}</span>{" "}
                ({scenario.definition.persona.role})
              </>
            )}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-900 border border-indigo-100">
            Turns: {session.turn_count} / {session.max_turns}
          </div>

          {!isSessionEnded ? (
            <button
              type="button"
              onClick={handleEndSession}
              disabled={state === "recording" || state === "sending"}
              className="rounded-lg border border-rose-300 bg-rose-50 px-3.5 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-100 focus:outline-none disabled:opacity-50"
            >
              End Session
            </button>
          ) : (
            <button
              type="button"
              onClick={() => onViewFeedback(session.id)}
              className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 focus:outline-none"
            >
              View Feedback &rarr;
            </button>
          )}
        </div>
      </div>

      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      {/* Session Completed Banner */}
      {isSessionEnded && (
        <div className="rounded-xl border border-indigo-200 bg-indigo-50/70 p-5 text-center shadow-sm">
          <h3 className="text-lg font-bold text-indigo-950">
            Practice Session Completed!
          </h3>
          <p className="mt-1 text-sm text-indigo-800">
            End reason:{" "}
            <span className="font-semibold uppercase">
              {session.end_reason ?? "Completed"}
            </span>
            . You can now view detailed Coach feedback and delivery metrics.
          </p>
          <div className="mt-4">
            <button
              type="button"
              onClick={() => onViewFeedback(session.id)}
              className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow hover:bg-indigo-500 focus:outline-none"
            >
              View Coach Evaluation &amp; Metrics &rarr;
            </button>
          </div>
        </div>
      )}

      {/* Dialogue Turns History */}
      <TurnList
        turns={turns}
        interviewerName={interviewerName}
        personas={scenario.definition.personas}
        onReplayTurn={handleReplayTurn}
        isSpeaking={state === "speaking"}
      />

      {/* Interaction Controls */}
      {!isSessionEnded && (
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
          {/* Review Transcript Stage (No Auto-Send) */}
          {state === "review" && (
            <TranscriptReview
              initialText={reviewText}
              speechMeta={reviewSpeechMeta}
              onSend={handleSendReviewedSpeech}
              onDiscard={handleDiscardReview}
              isSending={false}
            />
          )}

          {/* Transcribing loader */}
          {state === "transcribing" && (
            <div className="flex items-center justify-center gap-3 p-4 text-sm font-medium text-indigo-600">
              <svg
                className="h-5 w-5 animate-spin"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v8z"
                />
              </svg>
              <span>Transcribing your speech with AI speech engine...</span>
            </div>
          )}

          {/* Push to Talk Button */}
          {state !== "review" && (
            <div className="py-2 border-b border-slate-100">
              <PushToTalkButton
                state={state}
                mode={mode}
                onModeChange={setMode}
                onStartRecording={handleStartRecording}
                onStopRecording={handleStopRecording}
                recordingSeconds={recordingSeconds}
                maxAudioSeconds={maxAudioSeconds}
                isMicDenied={isMicDenied}
                onMuteSpeaker={handleMuteSpeaker}
              />
            </div>
          )}

          {/* Typed Fallback Input */}
          <TypedInputFallback
            isMicDenied={isMicDenied}
            isDisabled={
              state === "transcribing" ||
              state === "waiting_reply" ||
              state === "speaking"
            }
            isSending={state === "sending"}
            onSendTyped={handleSendTyped}
          />
        </div>
      )}
    </div>
  );
};

function speechItemForTurn(turn: TurnOut, scenario: ScenarioOut): SpeechSequenceItem {
  const persona = (scenario.definition.personas ?? []).find(
    (panelPersona) => panelPersona.id === turn.speaker_id,
  );
  return { text: turn.text, voiceGender: persona?.voice_gender };
}
