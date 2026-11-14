import React from "react";
import type { InteractionMode, PushToTalkState } from "./types";

interface PushToTalkButtonProps {
  state: PushToTalkState;
  mode: InteractionMode;
  onModeChange: (mode: InteractionMode) => void;
  onStartRecording: () => void;
  onStopRecording: () => void;
  recordingSeconds: number;
  maxAudioSeconds: number;
  isMicDenied: boolean;
  onMuteSpeaker?: () => void;
}

export const PushToTalkButton: React.FC<PushToTalkButtonProps> = ({
  state,
  mode,
  onModeChange,
  onStartRecording,
  onStopRecording,
  recordingSeconds,
  maxAudioSeconds,
  isMicDenied,
  onMuteSpeaker,
}) => {
  const isRecording = state === "recording";
  const isMicLocked =
    state === "waiting_reply" ||
    state === "speaking" ||
    state === "transcribing" ||
    state === "sending";

  const handlePointerDown = (e: React.PointerEvent) => {
    if (isMicLocked || isMicDenied) return;
    if (mode === "hold" && state === "idle") {
      e.preventDefault();
      onStartRecording();
    }
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (mode === "hold" && isRecording) {
      e.preventDefault();
      onStopRecording();
    }
  };

  const handleClick = (e: React.MouseEvent) => {
    if (isMicLocked || isMicDenied) return;
    if (mode === "toggle") {
      e.preventDefault();
      if (isRecording) {
        onStopRecording();
      } else if (state === "idle") {
        onStartRecording();
      }
    }
  };

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Mode switch */}
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <span>Mode:</span>
        <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5">
          <button
            type="button"
            onClick={() => onModeChange("hold")}
            className={`rounded-md px-2.5 py-1 font-medium transition-all ${
              mode === "hold"
                ? "bg-white text-indigo-700 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Press &amp; Hold
          </button>
          <button
            type="button"
            onClick={() => onModeChange("toggle")}
            className={`rounded-md px-2.5 py-1 font-medium transition-all ${
              mode === "toggle"
                ? "bg-white text-indigo-700 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Click to Toggle
          </button>
        </div>
      </div>

      {/* Main Push-To-Talk Button */}
      <div className="relative flex flex-col items-center">
        {isRecording && (
          <div className="absolute -inset-3 rounded-full bg-rose-400 opacity-30 animate-ping pointer-events-none" />
        )}
        <button
          type="button"
          disabled={isMicLocked || isMicDenied}
          aria-label={
            isRecording
              ? "Stop recording"
              : isMicLocked
                ? "Microphone locked"
                : "Push to talk"
          }
          onPointerDown={handlePointerDown}
          onPointerUp={handlePointerUp}
          onClick={handleClick}
          className={`relative flex h-20 w-20 items-center justify-center rounded-full shadow-lg transition-all focus:outline-none ${
            isMicLocked || isMicDenied
              ? "bg-slate-300 text-slate-500 cursor-not-allowed opacity-60"
              : isRecording
                ? "bg-rose-600 text-white scale-105 shadow-rose-200"
                : "bg-indigo-600 text-white hover:bg-indigo-500 active:scale-95 shadow-indigo-200"
          }`}
        >
          {isRecording ? (
            /* Stop Square or Mic Active */
            <svg
              className="h-8 w-8 text-white"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          ) : isMicLocked ? (
            /* Lock Icon */
            <svg
              className="h-8 w-8 text-slate-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
              />
            </svg>
          ) : (
            /* Microphone Icon */
            <svg
              className="h-8 w-8 text-white"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
              />
            </svg>
          )}
        </button>

        {/* Status text under button */}
        <div className="mt-2 text-center text-xs">
          {isRecording ? (
            <div className="flex flex-col items-center text-rose-600 font-semibold">
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-rose-600 animate-pulse" />
                Recording ({recordingSeconds}s / {maxAudioSeconds}s)
              </span>
              <span className="text-[11px] font-normal text-rose-500">
                {mode === "hold" ? "Release to transcribe" : "Click to stop & transcribe"}
              </span>
            </div>
          ) : state === "waiting_reply" ? (
            <span className="font-medium text-amber-600">
              Interviewer is thinking... (Mic locked)
            </span>
          ) : state === "speaking" ? (
            <div className="flex items-center gap-2">
              <span className="font-medium text-purple-600">
                Interviewer is speaking... (Mic locked)
              </span>
              {onMuteSpeaker && (
                <button
                  type="button"
                  onClick={onMuteSpeaker}
                  className="rounded bg-purple-100 px-2 py-0.5 text-[11px] font-bold text-purple-800 hover:bg-purple-200"
                >
                  Mute
                </button>
              )}
            </div>
          ) : isMicDenied ? (
            <span className="font-medium text-rose-500">
              Mic unavailable &bull; Use typed response below
            </span>
          ) : (
            <span className="text-slate-500">
              {mode === "hold" ? "Hold button to speak" : "Click button to start recording"}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
