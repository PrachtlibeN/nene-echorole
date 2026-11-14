import React from "react";
import type { DeliveryMetrics } from "../../api/client";

interface DeliveryMetricsPanelProps {
  metrics: DeliveryMetrics | null;
}

export const DeliveryMetricsPanel: React.FC<DeliveryMetricsPanelProps> = ({
  metrics,
}) => {
  if (!metrics) {
    return (
      <div
        data-testid="delivery-metrics-panel"
        className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">
          Panel 2: Delivery &amp; Speech Metrics
        </h3>
        <p className="mt-4 text-xs text-slate-400">
          No delivery metrics recorded for this session.
        </p>
      </div>
    );
  }

  const formatSpeakingTime = (ms: number | null): string => {
    if (ms == null) return "N/A (typed)";
    const totalSeconds = Math.round(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    if (minutes > 0) {
      return `${minutes}m ${seconds}s`;
    }
    return `${totalSeconds}s`;
  };

  const fillerEntries = Object.entries(metrics.filler_words.breakdown || {});

  return (
    <div
      data-testid="delivery-metrics-panel"
      className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-6"
    >
      <div className="border-b border-slate-100 pb-4">
        <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
          Panel 2: Delivery &amp; Speech Metrics
        </span>
        <h2 className="text-xl font-bold text-slate-900 mt-1">
          Pacing &amp; Speaking Analysis
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Objective, deterministic speech metrics. These numbers are purely descriptive and do not affect your qualitative coach score.
        </p>
      </div>

      {/* Grid of Key Metrics Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {/* Candidate Turns */}
        <div className="rounded-lg bg-slate-50 p-3.5 border border-slate-100">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
            Candidate Turns
          </span>
          <span className="text-2xl font-black text-slate-900 mt-1 block">
            {metrics.candidate_turns}
          </span>
        </div>

        {/* Total Words */}
        <div className="rounded-lg bg-slate-50 p-3.5 border border-slate-100">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
            Total Words
          </span>
          <span className="text-2xl font-black text-slate-900 mt-1 block">
            {metrics.total_words}
          </span>
        </div>

        {/* Avg Words per Turn */}
        <div className="rounded-lg bg-slate-50 p-3.5 border border-slate-100">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
            Avg Words / Turn
          </span>
          <span className="text-2xl font-black text-slate-900 mt-1 block">
            {metrics.avg_words_per_turn.toFixed(1)}
          </span>
        </div>

        {/* Words per Minute (WPM) */}
        <div className="rounded-lg bg-slate-50 p-3.5 border border-slate-100">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
            Speaking Pace (WPM)
          </span>
          <span className="text-2xl font-black text-indigo-700 mt-1 block">
            {metrics.words_per_minute != null
              ? metrics.words_per_minute.toFixed(1)
              : "N/A"}
          </span>
          <span className="text-[10px] text-slate-400">Target: 120-150 WPM</span>
        </div>

        {/* Speaking Duration */}
        <div className="rounded-lg bg-slate-50 p-3.5 border border-slate-100">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
            Speaking Time
          </span>
          <span className="text-2xl font-black text-slate-900 mt-1 block">
            {formatSpeakingTime(metrics.speaking_time_ms)}
          </span>
        </div>

        {/* STT Recognition Confidence */}
        <div className="rounded-lg bg-slate-50 p-3.5 border border-slate-100">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
            STT Confidence
          </span>
          <span className="text-2xl font-black text-slate-900 mt-1 block">
            {metrics.avg_stt_confidence != null
              ? `${Math.round(metrics.avg_stt_confidence * 100)}%`
              : "N/A"}
          </span>
          <span className="text-[10px] text-slate-400">Whisper accuracy</span>
        </div>

        {/* Filler Words Summary */}
        <div className="col-span-2 rounded-lg bg-slate-50 p-3.5 border border-slate-100 flex items-center justify-between">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
              Filler Words Total
            </span>
            <span className="text-2xl font-black text-amber-700 mt-1 block">
              {metrics.filler_words.total}
            </span>
          </div>
          <div className="text-right">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
              Density
            </span>
            <span className="text-lg font-bold text-slate-800">
              {metrics.filler_words.per_100_words.toFixed(1)}
              <span className="text-xs text-slate-400 font-normal"> / 100 words</span>
            </span>
          </div>
        </div>
      </div>

      {/* Filler Words Breakdown Chips */}
      <div>
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">
          Filler Word Breakdown
        </h4>
        {fillerEntries.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {fillerEntries.map(([word, count]) => (
              <span
                key={word}
                className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-900"
              >
                <span className="font-semibold">&ldquo;{word}&rdquo;:</span>
                <span className="rounded-full bg-amber-200/80 px-1.5 py-0.2 text-[10px] font-bold text-amber-950">
                  {count}
                </span>
              </span>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-400">
            No common filler words were detected in your speech.
          </p>
        )}
      </div>
    </div>
  );
};
