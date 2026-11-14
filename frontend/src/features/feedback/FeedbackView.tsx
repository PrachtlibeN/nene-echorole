import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type EvaluationOut } from "../../api/client";
import { getErrorMessage } from "../../api/errors";
import { ErrorAlert } from "../../components/ErrorAlert";
import { CoachFeedbackPanel } from "./CoachFeedbackPanel";
import { DeliveryMetricsPanel } from "./DeliveryMetricsPanel";

interface FeedbackViewProps {
  sessionId: string;
  onBackToScenarios: () => void;
  pollIntervalMs?: number;
}

async function startOrLoadEvaluation(sessionId: string): Promise<EvaluationOut> {
  try {
    return await api.startEvaluation(sessionId);
  } catch (error) {
    if (error instanceof ApiError && error.code === "EVALUATION_IN_PROGRESS") {
      return api.getEvaluation(sessionId);
    }
    throw error;
  }
}

export const FeedbackView: React.FC<FeedbackViewProps> = ({
  sessionId,
  onBackToScenarios,
  pollIntervalMs = 2000,
}) => {
  const [evaluation, setEvaluation] = useState<EvaluationOut | null>(null);
  const [isPolling, setIsPolling] = useState<boolean>(true);
  const [error, setError] = useState<unknown | null>(null);
  const [pollCount, setPollCount] = useState<number>(0);

  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setIsPolling(false);
  };

  const startPolling = useCallback(() => {
    stopPolling();
    setIsPolling(true);

    pollTimerRef.current = setInterval(async () => {
      try {
        const result = await api.getEvaluation(sessionId);
        setEvaluation(result);
        setPollCount((prev) => prev + 1);

        if (result.status === "completed" || result.status === "failed") {
          stopPolling();
        }
      } catch (err) {
        setError(err);
        stopPolling();
      }
    }, pollIntervalMs);
  }, [sessionId, pollIntervalMs]);

  // Initial load: fetch evaluation or start it if not started
  const initEvaluation = useCallback(async () => {
    setError(null);
    setIsPolling(true);
    try {
      let initial: EvaluationOut;
      try {
        initial = await api.getEvaluation(sessionId);
      } catch (err) {
        if (err instanceof ApiError && (err.status === 404 || err.code === "EVALUATION_NOT_FOUND")) {
          initial = await startOrLoadEvaluation(sessionId);
        } else {
          throw err;
        }
      }

      setEvaluation(initial);

      if (initial.status === "completed" || initial.status === "failed") {
        setIsPolling(false);
      } else {
        // Pending or running: start 2-second polling
        startPolling();
      }
    } catch (err) {
      setError(err);
      setIsPolling(false);
    }
  }, [sessionId, startPolling]);

  useEffect(() => {
    initEvaluation();
    return () => {
      stopPolling();
    };
  }, [initEvaluation]);

  // Retry evaluation on failure
  const handleRetry = async () => {
    setError(null);
    setIsPolling(true);
    try {
      const restarted = await startOrLoadEvaluation(sessionId);
      setEvaluation(restarted);
      startPolling();
    } catch (err) {
      setError(err);
      setIsPolling(false);
    }
  };

  const isCompleted = evaluation?.status === "completed";
  const isFailed = evaluation?.status === "failed";
  const isPendingOrRunning =
    isPolling || evaluation?.status === "pending" || evaluation?.status === "running";

  return (
    <div className="space-y-6">
      {/* Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div>
          <button
            type="button"
            onClick={onBackToScenarios}
            className="flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-800 focus:outline-none mb-1"
          >
            &larr; Return to Scenarios
          </button>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">
            Session Performance Evaluation
          </h1>
          <p className="text-xs text-slate-500">
            Session ID: <span className="font-mono text-slate-700">{sessionId}</span>
            {evaluation?.attempt != null && (
              <span> &bull; Attempt #{evaluation.attempt}</span>
            )}
            {evaluation?.rubric_version && (
              <span> &bull; Rubric v{evaluation.rubric_version}</span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {evaluation && (
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wider ${
                isCompleted
                  ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                  : isFailed
                    ? "bg-rose-100 text-rose-800 border border-rose-200"
                    : "bg-amber-100 text-amber-800 border border-amber-200 animate-pulse"
              }`}
            >
              Status: {evaluation.status}
            </span>
          )}
          <button
            type="button"
            onClick={onBackToScenarios}
            className="rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 focus:outline-none"
          >
            Practice New Scenario
          </button>
        </div>
      </div>

      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      {/* Evaluating / Polling Indicator */}
      {isPendingOrRunning && !isCompleted && !isFailed && (
        <div
          role="status"
          className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-8 text-center shadow-sm space-y-4"
        >
          <div className="flex justify-center">
            <svg
              className="h-10 w-10 animate-spin text-indigo-600"
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
          </div>
          <div>
            <h3 className="text-lg font-bold text-indigo-950">
              AI Coach is Evaluating Your Performance...
            </h3>
            <p className="mt-1 text-sm text-indigo-700">
              Polling evaluation progress every 2 seconds. Please wait while the coach analyzes your dialogue transcript.
            </p>
            {pollCount > 0 && (
              <span className="mt-2 inline-block rounded bg-indigo-100 px-2 py-0.5 text-xs font-mono text-indigo-800">
                Poll checks: {pollCount}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Failed Evaluation State with Retry */}
      {isFailed && (
        <div
          role="alert"
          className="rounded-xl border border-rose-200 bg-rose-50 p-6 shadow-sm space-y-4"
        >
          <div className="flex items-start gap-3">
            <svg
              className="h-6 w-6 flex-shrink-0 text-rose-600 mt-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <div>
              <h3 className="text-base font-bold text-rose-900">
                Evaluation Attempt Failed
              </h3>
              <p className="mt-1 text-sm text-rose-800">
                {getErrorMessage(
                  evaluation?.error?.code,
                  evaluation?.error?.message,
                )}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              type="button"
              onClick={handleRetry}
              disabled={isPolling}
              className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-rose-500 focus:outline-none disabled:opacity-50"
            >
              {isPolling ? "Retrying..." : "Retry Evaluation"}
            </button>
          </div>
        </div>
      )}

      {/* When completed: Show the 2 Separate Panels */}
      {isCompleted && evaluation.result && (
        <div className="space-y-6">
          {/* Panel 1: Coach Qualitative Feedback & Raw Scores */}
          <CoachFeedbackPanel result={evaluation.result} />

          {/* Panel 2: Delivery & Speech Metrics */}
          <DeliveryMetricsPanel metrics={evaluation.metrics} />
        </div>
      )}

      {/* If failed but metrics exist: Show Panel 2 */}
      {isFailed && evaluation?.metrics && (
        <div className="mt-4">
          <DeliveryMetricsPanel metrics={evaluation.metrics} />
        </div>
      )}
    </div>
  );
};
