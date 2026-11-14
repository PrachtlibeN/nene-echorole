import React from "react";
import type { EvaluationResult } from "../../api/client";

interface CoachFeedbackPanelProps {
  result: EvaluationResult;
}

const CRITERION_LABELS: Record<string, string> = {
  relevance: "Relevance & Goal Alignment",
  structure: "Structure & Organization (STAR)",
  clarity: "Clarity & Precision",
  composure: "Composure Under Pressure",
  conciseness: "Conciseness & Efficiency",
  language_accuracy: "Language Accuracy & Register",
};

export const CoachFeedbackPanel: React.FC<CoachFeedbackPanelProps> = ({
  result,
}) => {
  const outcomeBadge = () => {
    switch (result.task_outcome.achieved) {
      case "yes":
        return (
          <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-800 border border-emerald-200">
            Task Achieved
          </span>
        );
      case "partially":
        return (
          <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-800 border border-amber-200">
            Partially Achieved
          </span>
        );
      case "no":
        return (
          <span className="rounded-full bg-rose-100 px-3 py-1 text-xs font-bold text-rose-800 border border-rose-200">
            Not Achieved
          </span>
        );
    }
  };

  return (
    <div
      data-testid="coach-feedback-panel"
      className="rounded-xl border border-indigo-200 bg-white p-6 shadow-sm space-y-6"
    >
      {/* Panel 1 Header: Overall Score & Summary */}
      <div className="border-b border-slate-100 pb-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-indigo-600">
              Panel 1: Coach Assessment &amp; Scores
            </span>
            <h2 className="text-2xl font-black text-slate-900 mt-1">
              Communication Feedback
            </h2>
          </div>
          <div className="flex items-center gap-3">
            {outcomeBadge()}
            {/* Display raw overall_score from API - ZERO arithmetic */}
            <div className="flex flex-col items-end rounded-lg bg-indigo-50 px-4 py-2 border border-indigo-100">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-indigo-700">
                Overall Score
              </span>
              <span
                data-testid="overall-score-display"
                className="text-3xl font-black text-indigo-950"
              >
                {result.overall_score}
                <span className="text-sm font-medium text-slate-500">/100</span>
              </span>
            </div>
          </div>
        </div>

        {/* Summary & Task Outcome */}
        <p className="mt-4 text-base font-medium text-slate-800 bg-slate-50 p-3.5 rounded-lg border border-slate-100">
          &ldquo;{result.summary}&rdquo;
        </p>
        <p className="mt-2 text-xs text-slate-500">
          <span className="font-semibold text-slate-700">Goal Assessment: </span>
          {result.task_outcome.explanation}
        </p>
      </div>

      {/* Rubric Criteria: 6 Criteria with Raw Scores & Weighted Points */}
      <div>
        <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700 mb-3">
          Rubric Criteria Scores
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {result.criteria.map((item) => {
            const displayName =
              CRITERION_LABELS[item.criterion] ?? item.criterion.replace("_", " ");
            return (
              <div
                key={item.criterion}
                data-testid={`criterion-${item.criterion}`}
                className="rounded-lg border border-slate-200 bg-slate-50/60 p-4 space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <h4 className="text-xs font-bold text-slate-900">
                    {displayName}
                  </h4>
                  {/* Raw score and raw weighted_points from API */}
                  <div className="text-right">
                    <span className="text-sm font-extrabold text-indigo-700">
                      {item.score}/10
                    </span>
                    <span
                      data-testid={`weighted-points-${item.criterion}`}
                      className="block text-[11px] font-semibold text-slate-500"
                    >
                      {item.weighted_points} pts ({item.weight_percent}%)
                    </span>
                  </div>
                </div>

                <p className="text-xs text-slate-600 leading-relaxed">
                  {item.rationale}
                </p>

                {item.evidence_turn_ids.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 pt-1 text-[11px] text-slate-400">
                    <span>Evidence:</span>
                    {item.evidence_turn_ids.map((id) => (
                      <span
                        key={id}
                        className="rounded bg-slate-200/80 px-1.5 py-0.5 font-mono text-[10px] text-slate-700"
                      >
                        {id}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Strengths & Improvements */}
      <div className="grid gap-6 md:grid-cols-2 pt-2 border-t border-slate-100">
        {/* Strengths */}
        <div className="space-y-3">
          <h3 className="flex items-center gap-1.5 text-sm font-bold text-emerald-800">
            <svg
              className="h-4 w-4 text-emerald-600"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
                clipRule="evenodd"
              />
            </svg>
            Key Strengths
          </h3>
          <ul className="space-y-2">
            {result.strengths.map((strength, idx) => (
              <li
                key={idx}
                className="rounded-lg border border-emerald-100 bg-emerald-50/50 p-3 text-xs text-emerald-950"
              >
                <p className="font-medium">{strength.text}</p>
                {strength.evidence_turn_ids.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1 text-[10px] text-emerald-700">
                    <span>Turns:</span>
                    {strength.evidence_turn_ids.map((id) => (
                      <span key={id} className="font-mono underline">
                        {id}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>

        {/* Improvements */}
        <div className="space-y-3">
          <h3 className="flex items-center gap-1.5 text-sm font-bold text-amber-800">
            <svg
              className="h-4 w-4 text-amber-600"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
                clipRule="evenodd"
              />
            </svg>
            Areas for Growth
          </h3>
          <ul className="space-y-2">
            {result.improvements.map((improvement, idx) => (
              <li
                key={idx}
                className="rounded-lg border border-amber-100 bg-amber-50/50 p-3 text-xs text-amber-950 space-y-1.5"
              >
                <p className="font-medium">{improvement.text}</p>
                {improvement.example_rewrite && (
                  <div className="rounded bg-white p-2 border border-amber-200 text-amber-900">
                    <span className="font-bold text-[10px] uppercase text-amber-700 block">
                      Suggested Phrasing:
                    </span>
                    <span className="italic">
                      &ldquo;{improvement.example_rewrite}&rdquo;
                    </span>
                  </div>
                )}
                {improvement.evidence_turn_ids.length > 0 && (
                  <div className="flex flex-wrap gap-1 text-[10px] text-amber-700">
                    <span>Turns:</span>
                    {improvement.evidence_turn_ids.map((id) => (
                      <span key={id} className="font-mono underline">
                        {id}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Next Task (TBLT) */}
      <div className="rounded-xl border border-indigo-200 bg-gradient-to-r from-indigo-50 to-purple-50 p-4">
        <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-700">
          Recommended Follow-Up Task (TBLT)
        </span>
        <h4 className="text-base font-bold text-indigo-950 mt-1">
          {result.next_task.title}
        </h4>
        <p className="mt-1 text-xs text-indigo-900 leading-relaxed">
          {result.next_task.instructions}
        </p>
      </div>
    </div>
  );
};
