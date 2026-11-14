import { useState } from "react";
import type { ScenarioOut, SessionOut, StartSessionOut, TurnOut } from "./api/client";
import { ScenariosView } from "./features/scenarios/ScenariosView";
import { SessionView } from "./features/session/SessionView";
import { FeedbackView } from "./features/feedback/FeedbackView";

type ActiveTab = "scenarios" | "session" | "feedback";

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("scenarios");
  const [currentScenario, setCurrentScenario] = useState<ScenarioOut | null>(null);
  const [currentSession, setCurrentSession] = useState<SessionOut | null>(null);
  const [initialTurns, setInitialTurns] = useState<TurnOut[]>([]);
  const [evaluationSessionId, setEvaluationSessionId] = useState<string | null>(null);

  const handleSessionStarted = (
    session: SessionOut,
    startData: StartSessionOut,
    scenario: ScenarioOut,
  ) => {
    setCurrentSession(startData.session ?? session);
    setCurrentScenario(scenario);
    setInitialTurns(
      startData.interviewer_turns?.length
        ? startData.interviewer_turns
        : [startData.interviewer_turn],
    );
    setEvaluationSessionId(session.id);
    setActiveTab("session");
  };

  const handleViewFeedback = (sessionId: string) => {
    setEvaluationSessionId(sessionId);
    setActiveTab("feedback");
  };

  const handleBackToScenarios = () => {
    setActiveTab("scenarios");
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
      {/* Top Navigation Bar */}
      <header className="border-b border-slate-200 bg-white shadow-sm sticky top-0 z-30">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600 text-white font-bold text-lg shadow-sm">
              E
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-900 leading-tight">
                EchoRole
              </h1>
              <p className="text-[11px] text-slate-500 font-medium">
                AI Spoken Roleplay &amp; Communication Coach
              </p>
            </div>
          </div>

          {/* Stepper Tabs */}
          <nav aria-label="Main Navigation" className="flex items-center gap-1 sm:gap-2">
            <button
              type="button"
              onClick={() => setActiveTab("scenarios")}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                activeTab === "scenarios"
                  ? "bg-indigo-50 text-indigo-700 border border-indigo-200"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              1. Scenarios
            </button>

            <span className="text-slate-300 text-xs">&rarr;</span>

            <button
              type="button"
              disabled={!currentSession || !currentScenario}
              onClick={() => setActiveTab("session")}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                activeTab === "session"
                  ? "bg-indigo-50 text-indigo-700 border border-indigo-200"
                  : "text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent"
              }`}
            >
              2. Session
            </button>

            <span className="text-slate-300 text-xs">&rarr;</span>

            <button
              type="button"
              disabled={!evaluationSessionId}
              onClick={() => setActiveTab("feedback")}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                activeTab === "feedback"
                  ? "bg-indigo-50 text-indigo-700 border border-indigo-200"
                  : "text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent"
              }`}
            >
              3. Feedback
            </button>
          </nav>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="mx-auto flex-1 w-full max-w-5xl px-4 py-6 sm:px-6">
        {activeTab === "scenarios" && (
          <ScenariosView onSessionStarted={handleSessionStarted} />
        )}

        {activeTab === "session" && currentSession && currentScenario && (
          <SessionView
            initialSession={currentSession}
            scenario={currentScenario}
            initialTurns={initialTurns}
            onViewFeedback={handleViewFeedback}
          />
        )}

        {activeTab === "feedback" && evaluationSessionId && (
          <FeedbackView
            sessionId={evaluationSessionId}
            onBackToScenarios={handleBackToScenarios}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-4 text-center text-xs text-slate-400">
        EchoRole MVP &bull; Phase 1 Track D (Frontend) &bull; Push-to-Talk Simulation &bull; Local Speech &amp; LLM
      </footer>
    </div>
  );
}
