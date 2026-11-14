import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { api, ApiError } from "./client";
import { handlers } from "../mocks/handlers";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("API Client", () => {
  it("fetches scenarios list and single scenario", async () => {
    const list = await api.listScenarios();
    expect(list.items.length).toBeGreaterThan(0);

    const scenario = await api.getScenario(list.items[0].id);
    expect(scenario.id).toBe(list.items[0].id);
    expect(scenario.definition.persona.name).toBe("Dana Whitfield");
  });

  it("uses the local backend API base URL by default", async () => {
    let requestUrl = "";
    server.use(
      http.get("http://localhost:8000/api/v1/scenarios", ({ request }) => {
        requestUrl = request.url;
        return HttpResponse.json({ items: [], total: 0 });
      }),
    );

    await api.listScenarios();

    expect(requestUrl).toBe("http://localhost:8000/api/v1/scenarios");
  });

  it("creates and starts a session", async () => {
    const session = await api.createSession("scn_a1b2c3");
    expect(session.id).toBeDefined();

    const started = await api.startSession(session.id);
    expect(started.session.status).toBe("active");
    expect(started.interviewer_turn.speaker).toBe("interviewer");
  });

  it("submits a turn and lists turns", async () => {
    const submitResult = await api.submitTurn("ses_9c1f40", {
      text: "I led a migration project.",
      source: "typed",
      speech_meta: null,
    });
    expect(submitResult.candidate_turn.text).toBeDefined();
    expect(submitResult.interviewer_turn.speaker).toBe("interviewer");

    const turns = await api.listTurns("ses_9c1f40");
    expect(turns.items.length).toBeGreaterThan(0);
  });

  it("ends session", async () => {
    const ended = await api.endSession("ses_9c1f40");
    expect(ended.status).toBe("ended");
  });

  it("gets speech status and transcribes audio", async () => {
    const status = await api.getSpeechStatus();
    expect(status.limits.max_audio_seconds).toBe(120);

    const blob = new Blob(["fake audio"], { type: "audio/webm" });
    const transcription = await api.transcribeAudio(blob);
    expect(transcription.text).toBeDefined();
    expect(transcription.duration_ms).toBeGreaterThan(0);
  });

  it("starts and gets evaluation", async () => {
    const started = await api.startEvaluation("ses_9c1f40");
    expect(started.status).toBe("pending");

    const evaluation = await api.getEvaluation("ses_9c1f40");
    expect(evaluation.status).toBe("completed");
    expect(evaluation.result?.overall_score).toBe(66);
    expect(evaluation.metrics?.candidate_turns).toBe(6);
  });

  it("throws ApiError with error envelope on error response", async () => {
    server.use(
      http.get("*/api/v1/sessions/invalid_session", () => {
        return HttpResponse.json(
          {
            error: {
              code: "SESSION_NOT_FOUND",
              message: "Session invalid_session not found",
              details: null,
              request_id: "req_test",
            },
          },
          { status: 404 },
        );
      }),
    );

    await expect(api.getSession("invalid_session")).rejects.toThrow(ApiError);

    try {
      await api.getSession("invalid_session");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.code).toBe("SESSION_NOT_FOUND");
      expect(apiErr.envelope?.error.request_id).toBe("req_test");
    }
  });
});
