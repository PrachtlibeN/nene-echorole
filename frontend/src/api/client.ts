import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

export type ErrorEnvelope = Schemas["ErrorEnvelope"];
export type APIError = Schemas["APIError"];

export type ScenarioSummary = Schemas["ScenarioSummary"];
export type ScenarioOut = Schemas["ScenarioOut"];
export type ScenarioListOut = Schemas["ScenarioListOut"];

export type SessionCreateIn = Schemas["SessionCreateIn"];
export type SessionOut = Schemas["SessionOut"];
export type SessionListOut = Schemas["SessionListOut"];
export type StartSessionOut = Schemas["StartSessionOut"];

export type TurnCreateIn = Schemas["TurnCreateIn"];
export type TurnOut = Schemas["TurnOut"];
export type TurnListOut = Schemas["TurnListOut"];
export type TurnSubmitOut = Schemas["TurnSubmitOut"];
export type SpeechMeta = Schemas["SpeechMeta"];

export type SpeechStatusOut = Schemas["SpeechStatusOut"];
export type TranscriptionOut = Schemas["TranscriptionOut"];

export type EvaluationOut = Schemas["EvaluationOut"];
export type DeliveryMetrics = Schemas["DeliveryMetrics"];
export type EvaluationResult = Schemas["EvaluationResult-Output"];
export type CriterionScore = Schemas["CriterionScore"];
export type Strength = Schemas["Strength"];
export type Improvement = Schemas["Improvement"];
export type NextTask = Schemas["NextTask"];
export type HealthOut = Schemas["HealthOut"];

type JsonBody<Response> = Response extends {
  content: { "application/json": infer Body };
}
  ? Body
  : never;

type ResponseFor<Responses, Status extends PropertyKey> = Status extends keyof Responses
  ? JsonBody<Responses[Status]>
  : never;

type OperationBody<Operation> = Operation extends { responses: infer Responses }
  ? ResponseFor<Responses, "200" | "201" | "202">
  : never;

type ApiPath = keyof paths;
type ApiMethod<Path extends ApiPath> = Extract<keyof paths[Path], "get" | "post">;

const API_PREFIX = "/api/v1";
const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"
).replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly envelope: ErrorEnvelope | null;
  readonly code: string | null;

  constructor(
    message: string,
    status: number,
    envelope: ErrorEnvelope | null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.envelope = envelope;
    this.code = envelope?.error?.code ?? null;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = typeof FormData !== "undefined" && init?.body instanceof FormData;
  const headers: Record<string, string> = {};
  const suffix = path.startsWith(API_PREFIX) ? path.slice(API_PREFIX.length) : path;
  const url = `${API_BASE_URL}${suffix}`;

  if (!isFormData) {
    headers["Content-Type"] = "application/json";
  }

  if (init?.headers) {
    const customHeaders = new Headers(init.headers);
    customHeaders.forEach((value, key) => {
      headers[key] = value;
    });
  }

  const response = await fetch(url, {
    ...init,
    headers: isFormData ? init?.headers : headers,
  });

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const envelope =
      typeof body === "object" && body !== null && "error" in body
        ? (body as ErrorEnvelope)
        : null;
    const message =
      envelope?.error?.message ?? `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, envelope);
  }

  return (await response.json()) as T;
}

export async function apiFetch<
  Path extends ApiPath,
  Method extends ApiMethod<Path>,
>(
  path: Path,
  method: Method,
  init?: RequestInit,
): Promise<OperationBody<paths[Path][Method]>> {
  return request<OperationBody<paths[Path][Method]>>(path as string, {
    ...init,
    method: method.toUpperCase(),
  });
}

export const api = {
  getHealth(): Promise<HealthOut> {
    return request<HealthOut>("/api/v1/health");
  },

  listScenarios(): Promise<ScenarioListOut> {
    return request<ScenarioListOut>("/api/v1/scenarios");
  },

  getScenario(scenarioId: string): Promise<ScenarioOut> {
    return request<ScenarioOut>(`/api/v1/scenarios/${encodeURIComponent(scenarioId)}`);
  },

  createSession(scenarioId: string): Promise<SessionOut> {
    const payload: SessionCreateIn = { scenario_id: scenarioId };
    return request<SessionOut>("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  listSessions(params?: {
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<SessionListOut> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
    if (params?.offset !== undefined) searchParams.set("offset", String(params.offset));
    const qs = searchParams.toString();
    return request<SessionListOut>(`/api/v1/sessions${qs ? `?${qs}` : ""}`);
  },

  getSession(sessionId: string): Promise<SessionOut> {
    return request<SessionOut>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
  },

  startSession(sessionId: string): Promise<StartSessionOut> {
    return request<StartSessionOut>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/start`,
      {
        method: "POST",
        body: JSON.stringify({}),
      },
    );
  },

  submitTurn(sessionId: string, payload: TurnCreateIn): Promise<TurnSubmitOut> {
    return request<TurnSubmitOut>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/turns`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  },

  listTurns(sessionId: string): Promise<TurnListOut> {
    return request<TurnListOut>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/turns`,
    );
  },

  endSession(sessionId: string): Promise<SessionOut> {
    return request<SessionOut>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/end`,
      {
        method: "POST",
        body: JSON.stringify({}),
      },
    );
  },

  getSpeechStatus(): Promise<SpeechStatusOut> {
    return request<SpeechStatusOut>("/api/v1/speech/status");
  },

  transcribeAudio(audioBlob: Blob): Promise<TranscriptionOut> {
    const formData = new FormData();
    formData.append("audio", audioBlob, "recording.webm");
    return request<TranscriptionOut>("/api/v1/speech/transcribe", {
      method: "POST",
      body: formData,
    });
  },

  startEvaluation(sessionId: string): Promise<EvaluationOut> {
    return request<EvaluationOut>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/evaluation`,
      {
        method: "POST",
        body: JSON.stringify({}),
      },
    );
  },

  getEvaluation(sessionId: string, attempt?: number): Promise<EvaluationOut> {
    const qs = attempt !== undefined ? `?attempt=${attempt}` : "";
    return request<EvaluationOut>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/evaluation${qs}`,
    );
  },
};
