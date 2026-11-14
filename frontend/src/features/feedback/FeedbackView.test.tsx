import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { FeedbackView } from "./FeedbackView";
import {
  completedEvaluationExample,
  evaluationExample,
} from "../../mocks/examples";
import { handlers } from "../../mocks/handlers";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("FeedbackView - 2-Panel Layout & 2s Polling", () => {
  it("renders both separate panels when evaluation is completed", async () => {
    render(
      <FeedbackView
        sessionId="ses_9c1f40"
        onBackToScenarios={vi.fn()}
      />,
    );

    // Verify Panel 1: Coach assessment & scores
    await waitFor(() => {
      expect(screen.getByTestId("coach-feedback-panel")).toBeInTheDocument();
      expect(screen.getByTestId("delivery-metrics-panel")).toBeInTheDocument();
    });

    // Panel 1: displays raw overall_score directly from API (66), zero UI arithmetic
    const overallScoreEl = screen.getByTestId("overall-score-display");
    expect(overallScoreEl).toHaveTextContent("66");
    expect(overallScoreEl).toHaveTextContent("/100");

    // Panel 1: displays raw weighted_points directly from API (17.5 pts for relevance)
    const relevancePoints = screen.getByTestId("weighted-points-relevance");
    expect(relevancePoints).toHaveTextContent("17.5 pts");
    expect(relevancePoints).toHaveTextContent("25%");

    // Panel 1: displays qualitative feedback
    expect(
      screen.getByText(/Solid content, but answers lacked measurable outcomes/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Quantify your impact")).toBeInTheDocument();

    // Panel 2: displays delivery metrics
    expect(screen.getByText("Panel 2: Delivery & Speech Metrics")).toBeInTheDocument();
    expect(screen.getByText("412")).toBeInTheDocument(); // total words
    expect(screen.getByText("128.7")).toBeInTheDocument(); // WPM
    expect(screen.getByText("14")).toBeInTheDocument(); // filler words total
    expect(screen.getByText(/3m 12s/i)).toBeInTheDocument(); // 192000 ms = 3m 12s
  });

  it("polls GET /sessions/{id}/evaluation every 2s until completed", async () => {
    vi.useFakeTimers();

    let pollAttempts = 0;
    server.use(
      http.get("*/api/v1/sessions/:session_id/evaluation", () => {
        pollAttempts++;
        if (pollAttempts < 3) {
          return HttpResponse.json({
            ...evaluationExample,
            status: "running",
          });
        }
        return HttpResponse.json(completedEvaluationExample);
      }),
    );

    render(
      <FeedbackView
        sessionId="ses_9c1f40"
        onBackToScenarios={vi.fn()}
        pollIntervalMs={2000}
      />,
    );

    // Initially in evaluating state
    expect(
      screen.getByText(/ai coach is evaluating your performance/i),
    ).toBeInTheDocument();

    // Advance 2s (1st poll)
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });

    // Advance 2s (2nd poll)
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });

    // Advance 2s (3rd poll -> completed)
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });

    expect(pollAttempts).toBeGreaterThanOrEqual(3);

    vi.useRealTimers();

    await waitFor(() => {
      expect(screen.getByTestId("coach-feedback-panel")).toBeInTheDocument();
    });
  });

  it("loads the existing evaluation when a concurrent start request wins", async () => {
    let getAttempts = 0;
    server.use(
      http.get("*/api/v1/sessions/:session_id/evaluation", () => {
        getAttempts++;
        if (getAttempts === 1) {
          return HttpResponse.json(
            {
              error: {
                code: "EVALUATION_NOT_FOUND",
                message: "No evaluation exists.",
                details: null,
                request_id: "req_test",
              },
            },
            { status: 404 },
          );
        }
        return HttpResponse.json({ ...evaluationExample, status: "running" });
      }),
      http.post("*/api/v1/sessions/:session_id/evaluation", () =>
        HttpResponse.json(
          {
            error: {
              code: "EVALUATION_IN_PROGRESS",
              message: "An evaluation is already in progress.",
              details: null,
              request_id: "req_test",
            },
          },
          { status: 409 },
        ),
      ),
    );

    render(
      <FeedbackView
        sessionId="ses_9c1f40"
        onBackToScenarios={vi.fn()}
        pollIntervalMs={100}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/status: running/i)).toBeInTheDocument();
      expect(getAttempts).toBeGreaterThanOrEqual(2);
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("handles failed evaluation state and allows retry", async () => {
    let hasRetried = false;

    server.use(
      http.get("*/api/v1/sessions/:session_id/evaluation", () => {
        if (!hasRetried) {
          return HttpResponse.json({
            ...evaluationExample,
            status: "failed",
            error: {
              code: "EVALUATION_PARSE_FAILED",
              message: "Invalid coach output",
            },
          });
        }
        return HttpResponse.json(completedEvaluationExample);
      }),
      http.post("*/api/v1/sessions/:session_id/evaluation", () => {
        hasRetried = true;
        return HttpResponse.json(
          {
            ...evaluationExample,
            attempt: 2,
            status: "pending",
          },
          { status: 202 },
        );
      }),
    );

    render(
      <FeedbackView
        sessionId="ses_9c1f40"
        onBackToScenarios={vi.fn()}
        pollIntervalMs={100}
      />,
    );

    // Failed error alert is shown with friendly error message
    await waitFor(() => {
      expect(
        screen.getByText(/the coach evaluation output could not be parsed/i),
      ).toBeInTheDocument();
    });

    // Click Retry Evaluation
    const retryBtn = screen.getByRole("button", { name: /retry evaluation/i });
    fireEvent.click(retryBtn);

    // After retry and polling, should succeed and show completed panel
    await waitFor(() => {
      expect(screen.getByTestId("coach-feedback-panel")).toBeInTheDocument();
    });
  });
});
