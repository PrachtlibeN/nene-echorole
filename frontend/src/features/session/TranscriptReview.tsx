import React, { useState } from "react";
import type { SpeechMeta } from "../../api/client";

interface TranscriptReviewProps {
  initialText: string;
  speechMeta: SpeechMeta | null;
  onSend: (text: string) => void;
  onDiscard: () => void;
  isSending: boolean;
}

export const TranscriptReview: React.FC<TranscriptReviewProps> = ({
  initialText,
  speechMeta,
  onSend,
  onDiscard,
  isSending,
}) => {
  const [text, setText] = useState<string>(initialText);

  const handleSend = () => {
    if (text.trim().length === 0) return;
    onSend(text.trim());
  };

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-emerald-500" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-indigo-900">
            Review Your Spoken Response (No Auto-Send)
          </h4>
        </div>
        {speechMeta && (
          <span className="text-xs text-indigo-700">
            {(speechMeta.duration_ms / 1000).toFixed(1)}s &bull;{" "}
            {speechMeta.avg_confidence != null
              ? `${Math.round(speechMeta.avg_confidence * 100)}% confidence`
              : ""}
          </span>
        )}
      </div>

      <p className="text-xs text-indigo-800">
        Review and edit the transcription below before submitting to the interviewer.
      </p>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        className="w-full rounded-lg border border-indigo-200 bg-white p-3 text-sm text-slate-900 shadow-inner focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        placeholder="Edit your transcribed response..."
        disabled={isSending}
      />

      <div className="flex items-center justify-between pt-1">
        <span className="text-xs text-slate-500">
          {text.trim().split(/\s+/).filter(Boolean).length} words
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onDiscard}
            disabled={isSending}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 focus:outline-none disabled:opacity-50"
          >
            Discard
          </button>
          <button
            type="button"
            onClick={handleSend}
            disabled={isSending || text.trim().length === 0}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 focus:outline-none disabled:opacity-50"
          >
            {isSending ? (
              <>
                <svg
                  className="h-3.5 w-3.5 animate-spin text-white"
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
                Sending...
              </>
            ) : (
              "Send Answer"
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
