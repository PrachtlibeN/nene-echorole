import React, { useEffect, useRef } from "react";
import type { ScenarioOut, TurnOut } from "../../api/client";

interface TurnListProps {
  turns: TurnOut[];
  interviewerName: string;
  personas: ScenarioOut["definition"]["personas"];
  onReplayTurn: (text: string, speakerId?: string) => void;
  isSpeaking: boolean;
}

export const TurnList: React.FC<TurnListProps> = ({
  turns,
  interviewerName,
  personas,
  onReplayTurn,
  isSpeaking,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [turns, turns.length]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4 max-h-[460px] min-h-[280px] bg-slate-50/50 rounded-lg border border-slate-200">
      {turns.map((turn) => {
        const isInterviewer = turn.speaker === "interviewer";
        const panelPersonas = personas ?? [];
        const personaIndex = panelPersonas.findIndex(
          (persona) => persona.id === turn.speaker_id,
        );
        const persona = panelPersonas[personaIndex];
        const speakerName = persona
          ? `${persona.name} - ${persona.role_title}`
          : turn.speaker_name ?? interviewerName;
        const interviewerBadge =
          personaIndex === 0
            ? "bg-amber-100 text-amber-800"
            : personaIndex === 1
              ? "bg-sky-100 text-sky-800"
              : "bg-slate-100 text-slate-700";
        return (
          <div
            key={`${turn.id}-${turn.idx}-${turn.speaker}`}
            className={`flex flex-col ${
              isInterviewer ? "items-start" : "items-end"
            }`}
          >
            <div className="flex items-center gap-2 mb-1 px-1">
              <span className="text-xs font-semibold text-slate-600">
                {isInterviewer ? speakerName : "You (Candidate)"}
              </span>
              {isInterviewer && persona && (
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${interviewerBadge}`}
                >
                  AI #{personaIndex + 1}
                </span>
              )}
              <span className="text-[10px] text-slate-400">
                Turn {turn.idx}
              </span>
              {!isInterviewer && (
                <span
                  className={`rounded px-1.5 py-0.2 text-[10px] font-medium uppercase ${
                    turn.source === "speech"
                      ? "bg-purple-100 text-purple-700"
                      : "bg-blue-100 text-blue-700"
                  }`}
                >
                  {turn.source}
                </span>
              )}
            </div>

            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm ${
                isInterviewer
                  ? "bg-white text-slate-900 border border-slate-200 rounded-tl-sm"
                  : "bg-indigo-600 text-white rounded-tr-sm"
              }`}
            >
              <p className="whitespace-pre-wrap leading-relaxed">{turn.text}</p>

              {/* Speech metadata badge */}
              {turn.speech_meta && (
                <div className="mt-2 pt-2 border-t border-indigo-500/30 flex flex-wrap gap-2 text-[11px] text-indigo-100">
                  <span>
                    {(turn.speech_meta.duration_ms / 1000).toFixed(1)}s
                  </span>
                  <span>&bull;</span>
                  <span>{turn.speech_meta.word_count} words</span>
                  {turn.speech_meta.avg_confidence != null && (
                    <>
                      <span>&bull;</span>
                      <span>
                        {Math.round(turn.speech_meta.avg_confidence * 100)}% conf
                      </span>
                    </>
                  )}
                </div>
              )}

              {/* Replay button for Interviewer */}
              {isInterviewer && (
                <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => onReplayTurn(turn.text, turn.speaker_id ?? undefined)}
                    aria-label="Replay speech"
                    className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium focus:outline-none"
                  >
                    <svg
                      className="h-3.5 w-3.5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"
                      />
                    </svg>
                    <span>{isSpeaking ? "Speaking..." : "Replay voice"}</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
};
