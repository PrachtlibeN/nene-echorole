import React from "react";
import type { ScenarioOut } from "../../api/client";

interface ScenarioDetailProps {
  scenario: ScenarioOut;
  onStartSession: (scenario: ScenarioOut) => void;
  onBack: () => void;
  isStarting: boolean;
}

export const ScenarioDetail: React.FC<ScenarioDetailProps> = ({
  scenario,
  onStartSession,
  onBack,
  isStarting,
}) => {
  const { persona, personas, task, evaluation_focus } = scenario.definition;
  const panelPersonas = personas ?? [];

  const difficultyLabels: Record<number, { text: string; color: string }> = {
    1: { text: "Level 1: Beginner", color: "bg-emerald-100 text-emerald-800 border-emerald-200" },
    2: { text: "Level 2: Intermediate", color: "bg-amber-100 text-amber-800 border-amber-200" },
    3: { text: "Level 3: Advanced", color: "bg-rose-100 text-rose-800 border-rose-200" },
  };

  const difficultyInfo = difficultyLabels[scenario.difficulty] ?? {
    text: `Level ${scenario.difficulty}`,
    color: "bg-slate-100 text-slate-800 border-slate-200",
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900 focus:outline-none"
        >
          &larr; Back to all scenarios
        </button>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-semibold ${difficultyInfo.color}`}
        >
          {difficultyInfo.text}
        </span>
      </div>

      <div className="border-b border-slate-100 pb-5">
        <h2 className="text-2xl font-bold tracking-tight text-slate-900">
          {scenario.title}
        </h2>
        <p className="mt-2 text-base text-slate-600">{scenario.description}</p>
        <div className="mt-4 flex flex-wrap gap-4 text-xs font-medium text-slate-500">
          <span className="flex items-center gap-1">
            <span className="text-slate-400">Estimated:</span> {scenario.estimated_minutes} mins
          </span>
          <span className="flex items-center gap-1">
            <span className="text-slate-400">Max turns:</span> {scenario.max_turns} turns
          </span>
          <span className="flex items-center gap-1">
            <span className="text-slate-400">Language:</span> {scenario.language.toUpperCase()}
          </span>
        </div>
      </div>

      <div className="grid gap-6 py-6 md:grid-cols-2">
        {panelPersonas.length === 2 ? (
          <section className="rounded-lg border border-indigo-100 bg-indigo-50/50 p-4 md:col-span-2">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-indigo-900">
                2-on-1 Panel
              </h3>
              <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-indigo-700">
                Two AI interviewers
              </span>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {panelPersonas.map((panelPersona, index) => (
                <div
                  key={panelPersona.id}
                  className={`rounded-lg border bg-white p-4 ${
                    index === 0 ? "border-amber-200" : "border-sky-200"
                  }`}
                >
                  <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
                    AI #{index + 1} &middot; {panelPersona.focus_area}
                  </div>
                  <p className="mt-2 text-lg font-bold text-slate-900">
                    {panelPersona.name}
                  </p>
                  <p className="text-sm font-medium text-indigo-600">
                    {panelPersona.role_title}
                  </p>
                </div>
              ))}
            </div>
          </section>
        ) : (
          <div className="rounded-lg border border-slate-100 bg-slate-50/70 p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Interviewer Persona
              </h3>
              <span className="rounded bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700">
                Pressure Level: {persona.pressure_level}/3
              </span>
            </div>
            <p className="mt-2 text-lg font-bold text-slate-900">{persona.name}</p>
            <p className="text-sm font-medium text-indigo-600">{persona.role}</p>
            <div className="mt-3 text-sm text-slate-700">
              <span className="font-semibold text-slate-900">Style: </span>
              {persona.style}
            </div>
          </div>
        )}

        {/* Task & Goal Panel */}
        <div className="rounded-lg border border-slate-100 bg-slate-50/70 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Your Objective
          </h3>
          <p className="mt-2 text-sm font-medium text-slate-900">{task.goal}</p>

          <h4 className="mt-3 text-xs font-semibold text-slate-700">Success Criteria:</h4>
          <ul className="mt-1.5 list-inside list-disc space-y-1 text-xs text-slate-600">
            {task.success_criteria.map((criteria, index) => (
              <li key={index}>{criteria}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Evaluation Focus */}
      <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-indigo-900">
          Coach Evaluation Focus
        </h3>
        <p className="mt-1 text-xs text-indigo-700">
          The coach will specifically analyze your answers across these criteria:
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {evaluation_focus.map((focus) => (
            <span
              key={focus}
              className="rounded-md bg-white px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-indigo-800 shadow-sm border border-indigo-200"
            >
              {focus.replace("_", " ")}
            </span>
          ))}
        </div>
      </div>

      <div className="mt-6 flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
        <button
          type="button"
          onClick={onBack}
          className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none"
        >
          Cancel
        </button>
        <button
          type="button"
          disabled={isStarting}
          onClick={() => onStartSession(scenario)}
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 focus:outline-none disabled:opacity-50"
        >
          {isStarting ? (
            <>
              <svg
                className="h-4 w-4 animate-spin text-white"
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
              Starting Session...
            </>
          ) : (
            "Start Practice Session"
          )}
        </button>
      </div>
    </div>
  );
};
