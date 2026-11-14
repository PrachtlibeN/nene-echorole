import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { setupServer } from "msw/node";

import evaluationCompletedJson from "../../../docs/api-contracts/examples/evaluation-completed.json";
import evaluationPendingJson from "../../../docs/api-contracts/examples/evaluation-pending.json";
import healthJson from "../../../docs/api-contracts/examples/health.json";
import scenarioJson from "../../../docs/api-contracts/examples/scenario.json";
import scenarioListJson from "../../../docs/api-contracts/examples/scenario-list.json";
import sessionCreatedJson from "../../../docs/api-contracts/examples/session-created.json";
import sessionEndedJson from "../../../docs/api-contracts/examples/session-ended.json";
import sessionJson from "../../../docs/api-contracts/examples/session.json";
import sessionListJson from "../../../docs/api-contracts/examples/session-list.json";
import sessionStartJson from "../../../docs/api-contracts/examples/session-start.json";
import speechStatusJson from "../../../docs/api-contracts/examples/speech-status.json";
import transcriptionJson from "../../../docs/api-contracts/examples/transcription.json";
import turnListJson from "../../../docs/api-contracts/examples/turn-list.json";
import turnSubmitJson from "../../../docs/api-contracts/examples/turn-submit.json";
import {
  completedEvaluationExample,
  createdSessionExample,
  endedSessionExample,
  evaluationExample,
  healthExample,
  scenarioExample,
  scenarioListExample,
  sessionExample,
  sessionListExample,
  speechStatusExample,
  startSessionExample,
  transcriptionExample,
  turnListExample,
  turnSubmitExample,
} from "./examples";
import { handlerCount, handlers } from "./handlers";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("API mocks", () => {
  it("covers all 14 contract endpoints", () => {
    expect(handlerCount).toBe(14);
  });

  it("uses the canonical JSON examples for mock responses", () => {
    expect(healthExample).toEqual(healthJson);
    expect(scenarioListExample).toEqual(scenarioListJson);
    expect(scenarioExample).toEqual(scenarioJson);
    expect(sessionExample).toEqual(sessionJson);
    expect(createdSessionExample).toEqual(sessionCreatedJson);
    expect(endedSessionExample).toEqual(sessionEndedJson);
    expect(sessionListExample).toEqual(sessionListJson);
    expect(startSessionExample).toEqual(sessionStartJson);
    expect(turnListExample).toEqual(turnListJson);
    expect(turnSubmitExample).toEqual(turnSubmitJson);
    expect(speechStatusExample).toEqual(speechStatusJson);
    expect(transcriptionExample).toEqual(transcriptionJson);
    expect(evaluationExample).toEqual(evaluationPendingJson);
    expect(completedEvaluationExample).toEqual(evaluationCompletedJson);
  });

  it("returns contract success status codes for each endpoint", async () => {
    const calls: Array<[string, string, number]> = [
      ["GET", "/api/v1/health", 200],
      ["GET", "/api/v1/scenarios", 200],
      ["GET", "/api/v1/scenarios/scn_a1b2c3", 200],
      ["POST", "/api/v1/sessions", 201],
      ["GET", "/api/v1/sessions", 200],
      ["GET", "/api/v1/sessions/ses_9c1f40", 200],
      ["POST", "/api/v1/sessions/ses_9c1f40/start", 200],
      ["POST", "/api/v1/sessions/ses_9c1f40/turns", 200],
      ["GET", "/api/v1/sessions/ses_9c1f40/turns", 200],
      ["POST", "/api/v1/sessions/ses_9c1f40/end", 200],
      ["GET", "/api/v1/speech/status", 200],
      ["POST", "/api/v1/speech/transcribe", 200],
      ["POST", "/api/v1/sessions/ses_9c1f40/evaluation", 202],
      ["GET", "/api/v1/sessions/ses_9c1f40/evaluation", 200],
    ];

    for (const [method, path, status] of calls) {
      const response = await fetch(`http://localhost${path}`, { method });
      expect(response.status, `${method} ${path}`).toBe(status);
      expect(response.headers.get("X-Request-ID")).toBe("req_mock");
    }
  });

  it("returns an error envelope for x-mock-error requests", async () => {
    const response = await fetch("http://localhost/api/v1/sessions", {
      headers: { "x-mock-error": "TURN_IN_PROGRESS" },
    });

    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({
      error: { code: "TURN_IN_PROGRESS", request_id: "req_mock" },
    });
  });
});
