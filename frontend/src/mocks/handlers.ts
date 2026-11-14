import { http, HttpResponse, type JsonBodyType } from "msw";

import type { components } from "../api/schema";
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

type Schemas = components["schemas"];

const errorStatuses: Record<string, number> = {
  BAD_REQUEST: 400,
  SCENARIO_NOT_FOUND: 404,
  SESSION_NOT_FOUND: 404,
  EVALUATION_NOT_FOUND: 404,
  SESSION_INVALID_STATE: 409,
  SESSION_NOT_ACTIVE: 409,
  SESSION_NOT_ENDED: 409,
  TURN_IN_PROGRESS: 409,
  EVALUATION_IN_PROGRESS: 409,
  SESSION_TOO_SHORT: 409,
  AUDIO_TOO_LARGE: 413,
  AUDIO_UNSUPPORTED_FORMAT: 415,
  VALIDATION_ERROR: 422,
  AUDIO_TOO_LONG: 422,
  AUDIO_EMPTY_OR_SILENT: 422,
  INTERNAL_ERROR: 500,
  NOT_IMPLEMENTED: 501,
  LLM_BAD_OUTPUT: 502,
  EVALUATION_PARSE_FAILED: 502,
  LLM_UNAVAILABLE: 503,
  LLM_MODEL_NOT_FOUND: 503,
  STT_NOT_READY: 503,
  LLM_TIMEOUT: 504,
};

function json<T extends JsonBodyType>(
  data: T,
  request: Request,
  status = 200,
): HttpResponse<JsonBodyType> {
  const requestId = request.headers.get("X-Request-ID") ?? "req_mock";
  const errorCode = request.headers.get("x-mock-error");
  if (errorCode) {
    return HttpResponse.json(
      {
        error: {
          code: errorCode,
          message: `Mock error: ${errorCode}`,
          details: null,
          request_id: requestId,
        },
      },
      {
        status: errorStatuses[errorCode] ?? 400,
        headers: { "X-Request-ID": requestId },
      },
    );
  }
  return HttpResponse.json(data, {
    status,
    headers: { "X-Request-ID": requestId },
  });
}

export const handlers = [
  http.get("*/api/v1/health", ({ request }) => json<Schemas["HealthOut"]>(healthExample, request)),
  http.get("*/api/v1/scenarios", ({ request }) =>
    json<Schemas["ScenarioListOut"]>(scenarioListExample, request),
  ),
  http.get("*/api/v1/scenarios/:scenario_id", ({ request }) =>
    json<Schemas["ScenarioOut"]>(scenarioExample, request),
  ),
  http.post("*/api/v1/sessions", ({ request }) =>
    json<Schemas["SessionOut"]>(createdSessionExample, request, 201),
  ),
  http.get("*/api/v1/sessions", ({ request }) =>
    json<Schemas["SessionListOut"]>(sessionListExample, request),
  ),
  http.get("*/api/v1/sessions/:session_id", ({ request }) =>
    json<Schemas["SessionOut"]>(sessionExample, request),
  ),
  http.post("*/api/v1/sessions/:session_id/start", ({ request }) =>
    json<Schemas["StartSessionOut"]>(startSessionExample, request),
  ),
  http.post("*/api/v1/sessions/:session_id/turns", ({ request }) =>
    json<Schemas["TurnSubmitOut"]>(turnSubmitExample, request),
  ),
  http.get("*/api/v1/sessions/:session_id/turns", ({ request }) =>
    json<Schemas["TurnListOut"]>(turnListExample, request),
  ),
  http.post("*/api/v1/sessions/:session_id/end", ({ request }) =>
    json<Schemas["SessionOut"]>(endedSessionExample, request),
  ),
  http.get("*/api/v1/speech/status", ({ request }) =>
    json<Schemas["SpeechStatusOut"]>(speechStatusExample, request),
  ),
  http.post("*/api/v1/speech/transcribe", ({ request }) =>
    json<Schemas["TranscriptionOut"]>(transcriptionExample, request),
  ),
  http.post("*/api/v1/sessions/:session_id/evaluation", ({ request }) =>
    json<Schemas["EvaluationOut"]>(evaluationExample, request, 202),
  ),
  http.get("*/api/v1/sessions/:session_id/evaluation", ({ request }) =>
    json<Schemas["EvaluationOut"]>(completedEvaluationExample, request),
  ),
];

export const handlerCount = handlers.length;
