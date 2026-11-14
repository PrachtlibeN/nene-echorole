import React from "react";
import type { ScenarioSummary } from "../../api/client";

interface ScenarioCardProps {
  scenario: ScenarioSummary;
  onSelect: (scenarioId: string) => void;
  onQuickStart: (scenarioId: string) => void;
}

export const ScenarioCard: React.FC<ScenarioCardProps> = ({
  scenario,
  onSelect,
  onQuickStart,
}) => {
  const difficultyBadge = (level: number) => {
    switch (level) {
      case 1:
        return <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">Easy</span>;
      case 2:
        return <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">Medium</span>;
      case 3:
        return <span className="rounded bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-800">Hard</span>;
      default:
        return <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-800">Level {level}</span>;
    }
  };

  return (
    <div className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:border-indigo-300 hover:shadow-md">
      <div>
        <div className="flex items-center justify-between">
          {difficultyBadge(scenario.difficulty)}
          <span className="text-xs text-slate-400">
            {scenario.estimated_minutes} mins &bull; {scenario.max_turns} turns
          </span>
        </div>
        <h3 className="mt-3 text-lg font-bold text-slate-900 line-clamp-1">
          {scenario.title}
        </h3>
        <p className="mt-2 text-sm text-slate-600 line-clamp-3">
          {scenario.description}
        </p>
        {scenario.personas?.length === 2 && (
          <div className="mt-3 space-y-2">
            <span className="inline-flex rounded-full bg-indigo-50 px-2.5 py-1 text-[11px] font-semibold text-indigo-700">
              2-on-1 Panel
            </span>
            <div className="space-y-1">
              {scenario.personas.map((persona, index) => (
                <p key={persona.id} className="text-xs text-slate-600">
                  <span className="font-semibold text-slate-800">
                    AI #{index + 1}: {persona.name}
                  </span>{" "}
                  &middot; {persona.role_title}
                </p>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-5 flex items-center justify-between gap-3 border-t border-slate-100 pt-4">
        <button
          type="button"
          onClick={() => onSelect(scenario.id)}
          className="text-sm font-medium text-slate-600 hover:text-indigo-600 focus:outline-none"
        >
          View Details
        </button>
        <button
          type="button"
          onClick={() => onQuickStart(scenario.id)}
          className="rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 focus:outline-none"
        >
          Start Session
        </button>
      </div>
    </div>
  );
};
