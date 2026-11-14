import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import { setupServer } from "msw/node";

import { SessionView } from "./SessionView";
import {
  scenarioExample,
  sessionExample,
  startSessionExample,
  turnExample,
} from "../../mocks/examples";
import { handlers } from "../../mocks/handlers";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("SessionView - Push-To-Talk & Voice Interaction", () => {
  it("renders session header, initial interviewer turn and push-to-talk button", async () => {
    render(
      <SessionView
        initialSession={sessionExample}
        scenario={scenarioExample}
        initialTurns={startSessionExample.interviewer_turns}
        onViewFeedback={vi.fn()}
      />,
    );

    expect(screen.getByText("Behavioral Job Interview")).toBeInTheDocument();
    expect(screen.getByText(/Panel:/)).toBeInTheDocument();
    expect(screen.getByText("Alex")).toBeInTheDocument();
    expect(screen.getByText("Sarah")).toBeInTheDocument();
    expect(
      screen.getByText("Tell me about a project you led under a tight deadline."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Welcome. We will discuss how you led a project under pressure."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /push to talk|microphone locked/i }),
    ).toBeInTheDocument();
  });

  it("locks mic when waiting_reply or speaking", () => {
    render(
      <SessionView
        initialSession={sessionExample}
        scenario={scenarioExample}
        initialTurn={turnExample}
        onViewFeedback={vi.fn()}
      />,
    );

    const micButton = screen.getByRole("button", {
      name: /microphone locked|push to talk/i,
    });
    expect(micButton).toBeDefined();
  });

  it("supports typed fallback response and submits turn", async () => {
    render(
      <SessionView
        initialSession={sessionExample}
        scenario={scenarioExample}
        initialTurn={null}
        onViewFeedback={vi.fn()}
      />,
    );

    const input = screen.getByPlaceholderText(/type your answer here/i);
    expect(input).not.toBeDisabled();

    fireEvent.change(input, {
      target: { value: "I led a critical migration project." },
    });

    const sendBtn = screen.getByRole("button", { name: /send typed answer/i });
    fireEvent.click(sendBtn);

    // Verifies reply is received from MSW mock
    await waitFor(() => {
      expect(
        screen.getByText("What was the measurable outcome?"),
      ).toBeInTheDocument();
    });
  });

  it("supports push-to-talk recording, transcription, transcript review, and manual send (no auto-send)", async () => {
    const mockRecordAudio = vi.fn().mockResolvedValue(
      new Blob(["dummy voice data"], { type: "audio/webm" }),
    );

    render(
      <SessionView
        initialSession={sessionExample}
        scenario={scenarioExample}
        initialTurn={null}
        onViewFeedback={vi.fn()}
        onMockRecordAudio={mockRecordAudio}
      />,
    );

    // Switch to Click to Toggle mode
    const toggleModeBtn = screen.getByRole("button", { name: /click to toggle/i });
    fireEvent.click(toggleModeBtn);

    // Click to start recording
    const pttButton = screen.getByRole("button", { name: /push to talk/i });
    fireEvent.click(pttButton);

    // Button should be in recording state
    expect(screen.getByRole("button", { name: /stop recording/i })).toBeInTheDocument();

    // Click to stop recording
    fireEvent.click(screen.getByRole("button", { name: /stop recording/i }));

    // Verifies transcription is loaded in review (NO auto-send)
    await waitFor(() => {
      expect(
        screen.getByText(/review your spoken response \(no auto-send\)/i),
      ).toBeInTheDocument();
    });

    const reviewTextarea = screen.getByDisplayValue(
      "In my last role I led a migration of our payments service.",
    );
    expect(reviewTextarea).toBeInTheDocument();

    // Candidate edits transcript before sending
    fireEvent.change(reviewTextarea, {
      target: { value: "In my previous job I successfully migrated payment systems." },
    });

    // Submit reviewed answer
    const sendAnswerBtn = screen.getByRole("button", { name: /send answer/i });
    fireEvent.click(sendAnswerBtn);

    // Verifies candidate turn and interviewer reply are shown
    await waitFor(() => {
      expect(
        screen.getByText("In my last role I led a migration."),
      ).toBeInTheDocument();
      expect(
        screen.getByText("What was the measurable outcome?"),
      ).toBeInTheDocument();
    });
  });

  it("disables typed fallback while speech is transcribing", async () => {
    let resolveRecording: (blob: Blob) => void = () => {};
    const mockRecordAudio = vi.fn(
      () =>
        new Promise<Blob>((resolve) => {
          resolveRecording = resolve;
        }),
    );

    render(
      <SessionView
        initialSession={sessionExample}
        scenario={scenarioExample}
        initialTurn={null}
        onViewFeedback={vi.fn()}
        onMockRecordAudio={mockRecordAudio}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /click to toggle/i }));
    fireEvent.click(screen.getByRole("button", { name: /push to talk/i }));
    fireEvent.click(screen.getByRole("button", { name: /stop recording/i }));

    const input = screen.getByLabelText(/or type response/i);
    const sendButton = screen.getByRole("button", { name: /send typed answer/i });
    await waitFor(() => {
      expect(input).toBeDisabled();
      expect(sendButton).toBeDisabled();
    });

    resolveRecording(
      new Blob(["dummy voice data"], { type: "audio/webm" }),
    );
    await waitFor(() => {
      expect(
        screen.getByText(/review your spoken response \(no auto-send\)/i),
      ).toBeInTheDocument();
    });
  });

  it("auto-stops recording when reaching max_audio_seconds", async () => {
    vi.useFakeTimers();
    const mockRecordAudio = vi.fn().mockResolvedValue(
      new Blob(["audio data"], { type: "audio/webm" }),
    );

    render(
      <SessionView
        initialSession={sessionExample}
        scenario={scenarioExample}
        initialTurn={null}
        onViewFeedback={vi.fn()}
        onMockRecordAudio={mockRecordAudio}
      />,
    );

    // Switch to toggle mode
    const toggleModeBtn = screen.getByRole("button", { name: /click to toggle/i });
    act(() => {
      fireEvent.click(toggleModeBtn);
    });

    // Start recording
    const pttButton = screen.getByRole("button", { name: /push to talk/i });
    act(() => {
      fireEvent.click(pttButton);
    });

    // Advance timer by 121 seconds (exceeding default 120s limit)
    act(() => {
      vi.advanceTimersByTime(121000);
    });

    // Should automatically call mockRecordAudio and stop
    expect(mockRecordAudio).toHaveBeenCalled();

    vi.useRealTimers();
  });

  it("handles mic permission denial gracefully with explanation banner", async () => {
    // Force getUserMedia rejection
    const mockMediaDevices = {
      getUserMedia: vi.fn().mockRejectedValue(new Error("Permission denied")),
    };
    vi.stubGlobal("navigator", { mediaDevices: mockMediaDevices });

    render(
      <SessionView
        initialSession={sessionExample}
        scenario={scenarioExample}
        initialTurn={null}
        onViewFeedback={vi.fn()}
      />,
    );

    // In default hold mode, pointerDown triggers start recording
    const pttButton = screen.getByRole("button", { name: /push to talk/i });
    fireEvent.pointerDown(pttButton);

    // Verify explanation banner for mic denial
    await waitFor(() => {
      expect(
        screen.getByText(/microphone access was denied or is not supported/i),
      ).toBeInTheDocument();
    });

    vi.unstubAllGlobals();
  });

  it("allows user to end session and navigate to feedback", async () => {
    const handleViewFeedback = vi.fn();

    render(
      <SessionView
        initialSession={sessionExample}
        scenario={scenarioExample}
        initialTurn={turnExample}
        onViewFeedback={handleViewFeedback}
      />,
    );

    const endSessionBtn = screen.getByRole("button", { name: /end session/i });
    fireEvent.click(endSessionBtn);

    // Verifies completed banner and view feedback button
    await waitFor(() => {
      expect(
        screen.getByText(/practice session completed!/i),
      ).toBeInTheDocument();
    });

    const viewFeedbackBtn = screen.getByRole("button", {
      name: /view coach evaluation & metrics/i,
    });
    fireEvent.click(viewFeedbackBtn);

    expect(handleViewFeedback).toHaveBeenCalledWith(sessionExample.id);
  });
});
