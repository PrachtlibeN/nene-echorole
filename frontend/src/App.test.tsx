import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { setupServer } from "msw/node";

import App from "./App";
import { api } from "./api/client";
import { handlers } from "./mocks/handlers";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
});
afterAll(() => server.close());

describe("EchoRole App Integration", () => {
  it("navigates through the entire flow: scenarios -> session -> feedback", async () => {
    const submitTurn = vi.spyOn(api, "submitTurn");
    render(<App />);

    // Step 1: Scenarios screen loaded
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Roleplay Practice Scenarios" }),
      ).toBeInTheDocument();
      expect(screen.getByText("Behavioral Job Interview")).toBeInTheDocument();
    });

    // Start practice session
    const startBtn = screen.getByRole("button", { name: /start session/i });
    fireEvent.click(startBtn);

    // Step 2: Session screen loaded
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /end session/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByText("Tell me about a project you led under a tight deadline."),
      ).toBeInTheDocument();
    });

    // Wait until speech finishes and typed input is enabled
    const typedInput = screen.getByLabelText(/or type response/i);
    await waitFor(() => {
      expect(typedInput).not.toBeDisabled();
    });

    // Candidate types response and sends
    fireEvent.change(typedInput, {
      target: { value: "I led a cross-functional payment system migration." },
    });
    const sendAnswerButton = screen.getByRole("button", {
      name: /send typed answer/i,
    });
    expect(typedInput).toHaveValue("I led a cross-functional payment system migration.");
    expect(sendAnswerButton).toBeEnabled();
    fireEvent.click(sendAnswerButton);

    // Verify interviewer reply received
    await waitFor(() => {
      expect(submitTurn).toHaveBeenCalledOnce();
      expect(
        screen.getByText("What was the measurable outcome?"),
      ).toBeInTheDocument();
    });

    // End session
    fireEvent.click(screen.getByRole("button", { name: /end session/i }));

    await waitFor(() => {
      expect(screen.getByText(/practice session completed!/i)).toBeInTheDocument();
    });

    // Click view feedback
    const viewFeedbackBtn = screen.getByRole("button", {
      name: /view coach evaluation & metrics/i,
    });
    fireEvent.click(viewFeedbackBtn);

    // Step 3: Feedback screen loaded
    await waitFor(() => {
      expect(screen.getByTestId("coach-feedback-panel")).toBeInTheDocument();
      expect(screen.getByTestId("delivery-metrics-panel")).toBeInTheDocument();
    });

    // Verifies raw scores from API with zero UI arithmetic
    expect(screen.getByTestId("overall-score-display")).toHaveTextContent("66");
    expect(screen.getByTestId("weighted-points-relevance")).toHaveTextContent("17.5 pts");

    // Click return to scenarios
    fireEvent.click(screen.getByRole("button", { name: /return to scenarios/i }));

    // Back to scenarios
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Roleplay Practice Scenarios" }),
      ).toBeInTheDocument();
    });
  });
});
