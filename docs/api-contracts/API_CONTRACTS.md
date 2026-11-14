# Nene – API Contracts

| | |
|---|---|
| Status | **Approved contract; implemented through v0.4.0. See [current project status](../PROJECT_STATUS.md) for runtime/acceptance gaps.** |
| Contract version | **0.4.0** (bump on every contract change) |
| Base URL | `http://localhost:8000/api/v1` |
| Source of truth | This file → mirrored by `backend/app/schemas/` (Pydantic) → canonical JSON in `docs/api-contracts/examples/` → generated TS types in `frontend/src/api/` and MSW mocks |
| Change process | PR labelled `contract-change` (see SYSTEM_ARCHITECTURE §8). **Nobody adds, renames or removes fields outside this process.** |

---

## Change Log

| Version | Changes |
|---|---|
| 0.3.0 | **Clarifications (no endpoint added or removed):** idle-timeout (lazy abandonment) rules specified in new §6.9; `EvaluationOut.model` and `coach_conversation_id` nullability defined (`null` only while `pending`); evaluation of an `abandoned` session returns `SESSION_NOT_ENDED` with `details.status`. Health `contract_version` bumped. |
| 0.4.0 | Adds optional panel personas, speaker identity on turns, and `interviewer_turns` arrays while preserving `interviewer_turn` for compatibility. |
| 0.2.0 | **Evaluation:** rubric with explicit weights and band descriptions (§8.1); `CoachResult` (LLM output: criterion scores + evidence + qualitative text) separated from `EvaluationResult` (backend-composed, includes backend-computed `overall_score`, `weight_percent`, `weighted_points`); `rubric_version` added; `metrics` and `result` explicitly separate, Coach receives no metrics. **Speech:** English-only; `language` request part removed from `POST /speech/transcribe`; `/speech/status` reports `language:"en"`. **Scenarios:** `language` fixed to `"en"`, `language` query removed. **Health:** reports configured models per profile. **Errors:** added `SESSION_TOO_SHORT` (409) and `NOT_IMPLEMENTED` (501, Phase 0 stubs only). No model name appears in any contract. |
| 0.1.0 | Initial draft. |

---

## 1. Global Conventions

- JSON in/out (`Content-Type: application/json`) except `POST /speech/transcribe` (`multipart/form-data`).
- Field names: `snake_case`. Timestamps: ISO‑8601 UTC with `Z`. IDs: prefixed strings.
- Unknown request fields are **rejected** (`422 VALIDATION_ERROR`). Responses may gain optional fields only through a contract version bump.
- Every response carries `X-Request-ID`. Clients may send one.
- No authentication in MVP. CORS limited to `CORS_ORIGINS`.
- Nullable fields are always present (value `null`), never omitted.

### ID prefixes
`scn_` scenario · `ses_` session · `trn_` turn · `evl_` evaluation · `cnv_rp_` roleplay conversation · `cnv_ev_` evaluation conversation

---

## 2. Shared Error-Handling Convention

### 2.1 Envelope (all non-2xx responses)

```json
{
  "error": {
    "code": "SESSION_NOT_ACTIVE",
    "message": "Session ses_9c1f is not active (status: ended).",
    "details": { "session_id": "ses_9c1f", "status": "ended" },
    "request_id": "req_7d2a4b"
  }
}
```

| Field | Type | Rules |
|---|---|---|
| `code` | string | `UPPER_SNAKE_CASE` from the table below. Stable; clients branch on this |
| `message` | string | Human-readable English, safe to display. No stack traces, paths or prompts |
| `details` | object \| null | Machine-readable context. For validation errors: `{"fields":[{"loc":["body","text"],"msg":"…","type":"…"}]}` |
| `request_id` | string | Same as `X-Request-ID` |

### 2.2 Error codes

| HTTP | Code | Raised by | Meaning |
|---|---|---|---|
| 400 | `BAD_REQUEST` | any | Malformed request not covered by validation |
| 404 | `SCENARIO_NOT_FOUND` | M4 | |
| 404 | `SESSION_NOT_FOUND` | M4/M6 | |
| 404 | `EVALUATION_NOT_FOUND` | M6 | No evaluation requested yet |
| 409 | `SESSION_INVALID_STATE` | M4 | Transition not allowed (e.g. start an ended session). `details.status`, `details.allowed` |
| 409 | `SESSION_NOT_ACTIVE` | M4 | Turn posted to a non-active session |
| 409 | `SESSION_NOT_ENDED` | M6 | Evaluation requested before session ended |
| 409 | `TURN_IN_PROGRESS` | M4 | Another turn is being processed for this session |
| 409 | `EVALUATION_IN_PROGRESS` | M6 | An evaluation attempt is already pending/running |
| 409 | `SESSION_TOO_SHORT` | M6 | Session has no candidate turns; nothing to evaluate |
| 413 | `AUDIO_TOO_LARGE` | M5 | Exceeds `MAX_AUDIO_MB` |
| 415 | `AUDIO_UNSUPPORTED_FORMAT` | M5 | Not decodable / unsupported content type |
| 422 | `VALIDATION_ERROR` | M1 | Pydantic validation failure |
| 422 | `AUDIO_TOO_LONG` | M5 | Exceeds `MAX_AUDIO_SECONDS` |
| 422 | `AUDIO_EMPTY_OR_SILENT` | M5 | No speech detected (not an error for the UI to hide; prompt user to retry) |
| 500 | `INTERNAL_ERROR` | M1 | Unhandled |
| 501 | `NOT_IMPLEMENTED` | any | **Phase 0 router stubs only.** Removed from each endpoint as its module ships; never returned by a released module |
| 502 | `LLM_BAD_OUTPUT` | M2 | Provider rejected a completion request or returned unusable output |
| 502 | `EVALUATION_PARSE_FAILED` | M6 | Coach output invalid after one retry (bad JSON, missing/duplicate criterion, score not an integer 0–10, unknown evidence turn id). Appears as `error.code` inside a `failed` evaluation (§8.3), not as an HTTP status on the poll endpoint |
| 503 | `LLM_UNAVAILABLE` | M2 | Configured LLM provider is unreachable, rejects authentication/access, or remains rate-limited after retries |
| 503 | `LLM_MODEL_NOT_FOUND` | M2 | Configured model is missing or inaccessible from the active provider; guidance is provider-specific (for Ollama, pull the configured model) |
| 503 | `STT_NOT_READY` | M5 | Whisper model still loading / failed to load |
| 503 | `STT_UNAVAILABLE` | M5 | Speech recognition engine (faster-whisper) not installed or unavailable |
| 504 | `LLM_TIMEOUT` | M2 | Configured LLM provider call exceeded timeout |

### 2.3 Rules

1. Modules raise `AppError(code, message, http_status, details=None)`; only `core/errors.py` serialises it.
2. **Atomicity:** a failed turn (any 5xx) persists nothing; the client may safely resend the same request.
3. Failures of the asynchronous evaluation are **not** HTTP errors on the poll endpoint; they appear as `status:"failed"` with `error` inside the evaluation object (§8.2).
4. Clients treat unknown `code` values as generic errors and display `message`.
5. Internal Python modules never return `None` for failure; they raise `AppError`.

---

## 3. Endpoint Index

| # | Method | Endpoint | Module | Phase |
|---|---|---|---|---|
| 1 | GET | `/health` | M1 | 0 |
| 2 | GET | `/scenarios` | M4 | 1 |
| 3 | GET | `/scenarios/{scenario_id}` | M4 | 1 |
| 4 | POST | `/sessions` | M4 | 1 |
| 5 | GET | `/sessions` | M4 | 1 |
| 6 | GET | `/sessions/{session_id}` | M4 | 1 |
| 7 | POST | `/sessions/{session_id}/start` | M4 (+M3) | 1 |
| 8 | POST | `/sessions/{session_id}/turns` | M4 (+M3) | 1 |
| 9 | GET | `/sessions/{session_id}/turns` | M4 | 1 |
| 10 | POST | `/sessions/{session_id}/end` | M4 | 1 |
| 11 | GET | `/speech/status` | M5 | 1 |
| 12 | POST | `/speech/transcribe` | M5 | 1 |
| 13 | POST | `/sessions/{session_id}/evaluation` | M6 | 2 |
| 14 | GET | `/sessions/{session_id}/evaluation` | M6 | 2 |

The Roleplay Agent, LLM Gateway and Evaluation Coach have **no public endpoints**; their contracts are internal Python interfaces (§9).

---

## 4. System

### 4.1 `GET /health`
**Request:** none.

**Response 200**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "contract_version": "0.4.0",
  "components": {
    "database": { "status": "ok" },
    "llm": {
      "status": "ok",
      "models": { "roleplay": "example-model:8b", "evaluation": "example-model:8b" },
      "detail": null
    },
    "stt": { "status": "loading", "model": "small", "detail": null }
  }
}
```
`status` ∈ `ok | degraded`. Component `status` ∈ `ok | loading | unavailable`. Always returns 200 (never fails because a dependency is down). `llm.models` shows the models resolved from environment configuration for each profile; these are not hard-coded by the application. `llm.status` is `unavailable` with an explanatory `detail` when the selected provider is unreachable or a configured model is not available from that provider. The Roleplay Agent and Coach are never told these names.

---

## 5. Scenarios (M4)

### 5.1 Shared schemas

```jsonc
// ScenarioSummary
{
  "id": "scn_a1b2c3",
  "slug": "job-interview-behavioral",
  "title": "Behavioral Job Interview",
  "description": "Answer tough behavioral questions from a skeptical hiring manager.",
  "language": "en",                // always "en" in the MVP
  "difficulty": 2,                 // 1..3
  "max_turns": 8,
  "estimated_minutes": 10,
  "personas": [
    {
      "id": "engineering-manager",
      "name": "Alex",
      "role_title": "Engineering Manager",
      "focus_area": "Technical & Execution",
      "voice_gender": "male",
      "persona_prompt": "Probe technical decisions, ownership, and measurable execution."
    },
    {
      "id": "people-partner",
      "name": "Sarah",
      "role_title": "People Partner",
      "focus_area": "Leadership & Conflict",
      "voice_gender": "female",
      "persona_prompt": "Explore collaboration, leadership, and conflict resolution."
    }
  ]
}

// ScenarioOut  = ScenarioSummary + definition
{
  "...ScenarioSummary": "...",
  "definition": {
    "persona": {
      "name": "Dana Whitfield",
      "role": "Senior Engineering Manager",
      "style": "Direct, time-pressed, probes vague answers",
      "pressure_level": 3          // 1..3
    },
    "task": {
      "goal": "Convince the interviewer you can lead a project under tight deadlines.",
      "success_criteria": [
        "Gives at least one concrete example using STAR structure",
        "Quantifies the result",
        "Stays composed when challenged"
      ]
    },
    "evaluation_focus": ["structure", "relevance", "composure"],  // criteria the Coach elaborates on in feedback; does NOT change rubric weights
    "personas": [ /* same two Persona objects as ScenarioSummary.personas */ ]
  }
}
```

### 5.2 `GET /scenarios`
**Request:** none.

**Response 200**
```json
{ "items": [ /* ScenarioSummary[] */ ], "total": 3 }
```

### 5.3 `GET /scenarios/{scenario_id}`
**Response 200:** `ScenarioOut`. **Errors:** 404 `SCENARIO_NOT_FOUND`.

---

## 6. Sessions & Turns (M4)

### 6.1 Shared schemas

```jsonc
// SessionOut
{
  "id": "ses_9c1f40",
  "scenario_id": "scn_a1b2c3",
  "status": "active",              // created | active | ended | abandoned
  "end_reason": null,              // user_ended | max_turns | agent_concluded | timeout | null
  "turn_count": 2,                 // candidate turns so far
  "max_turns": 8,
  "roleplay_conversation_id": "cnv_rp_51ab90",
  "created_at": "2026-11-13T10:15:00Z",
  "started_at": "2026-11-13T10:15:04Z",
  "ended_at": null
}

// SpeechMeta  (client-provided, copied from /speech/transcribe response)
{
  "duration_ms": 8420,
  "avg_confidence": 0.91,          // 0..1 or null
  "word_count": 23,
  "language": "en"                 // always "en" in the MVP
}

// TurnOut
{
  "id": "trn_77e0c1",
  "session_id": "ses_9c1f40",
  "idx": 1,
  "speaker": "candidate",          // interviewer | candidate
  "text": "In my last role I led a migration…",
  "source": "speech",              // typed | speech | generated
  "speech_meta": { /* SpeechMeta */ },   // null unless source = speech
  "speaker_id": null,              // panel persona id; null for legacy interviewer/candidate turns
  "speaker_name": null,             // panel persona name; null for legacy interviewer/candidate turns
  "created_at": "2026-11-13T10:15:40Z"
}
```

### 6.2 `POST /sessions`
Creates a session and its roleplay conversation. Does not call the LLM.

**Request**
```json
{ "scenario_id": "scn_a1b2c3" }
```
**Response 201:** `SessionOut` (`status:"created"`, `started_at:null`).
**Errors:** 404 `SCENARIO_NOT_FOUND`, 422 `VALIDATION_ERROR`.

### 6.3 `GET /sessions`
**Query:** `status` (optional), `limit` (1–100, default 20), `offset` (default 0).

**Response 200**
```json
{ "items": [ /* SessionOut[] */ ], "total": 1, "limit": 20, "offset": 0 }
```

### 6.4 `GET /sessions/{session_id}`
**Response 200:** `SessionOut`. **Errors:** 404 `SESSION_NOT_FOUND`.

### 6.5 `POST /sessions/{session_id}/start`
Moves `created → active` and generates the interviewer's opening line via the Roleplay Agent.

**Request:** empty body `{}`.

**Response 200**
```json
{
  "session": { /* SessionOut, status:"active" */ },
  "interviewer_turn": { /* TurnOut: the final opening turn */ },
  "interviewer_turns": [
    { /* TurnOut, idx 0, first panel persona */ },
    { /* TurnOut, idx 1, second panel persona and first question */ }
  ]
}
```
`interviewer_turns` contains the one or two new opening turns. `interviewer_turn` remains the final item for clients using the original contract.
**Errors:** 404 `SESSION_NOT_FOUND`; 409 `SESSION_INVALID_STATE`; 503/504/502 LLM errors (session stays `created`).

### 6.6 `POST /sessions/{session_id}/turns`
Submit the candidate's utterance (text from typing or from STT); receive the interviewer's reply.

**Request**
```json
{
  "text": "In my last role I led a migration of our payments service…",
  "source": "speech",
  "speech_meta": { "duration_ms": 8420, "avg_confidence": 0.91, "word_count": 23, "language": "en" }
}
```
| Field | Type | Rules |
|---|---|---|
| `text` | string | required, trimmed, 1–2000 chars |
| `source` | `"typed"` \| `"speech"` | required |
| `speech_meta` | SpeechMeta \| null | required iff `source="speech"`, must be `null` otherwise |

**Response 200**
```json
{
  "candidate_turn": { /* TurnOut */ },
  "interviewer_turn": { /* TurnOut: final interviewer response */ },
  "interviewer_turns": [ /* one or two generated TurnOut items in transcript order */ ],
  "session": { /* SessionOut (may now be status:"ended") */ }
}
```
Rules:
- `interviewer_turns` lists every interviewer line generated for this candidate response. The compatibility field `interviewer_turn` equals its last item.
- If this turn reaches `max_turns` **or** the Roleplay Agent returns `should_end=true`, the interviewer turn is a closing remark and `session.status="ended"` with `end_reason` `max_turns` | `agent_concluded`.
- Atomic: on any error nothing is persisted.

**Errors:** 404 `SESSION_NOT_FOUND`; 409 `SESSION_NOT_ACTIVE`, `TURN_IN_PROGRESS`; 422 `VALIDATION_ERROR`; 502/503/504 LLM errors.

### 6.7 `GET /sessions/{session_id}/turns`
**Response 200**
```json
{ "session_id": "ses_9c1f40", "items": [ /* TurnOut[] ordered by idx */ ] }
```
**Errors:** 404 `SESSION_NOT_FOUND`.

### 6.8 `POST /sessions/{session_id}/end`
Ends an active session. Idempotent for already-`ended` sessions (returns current state).

**Request**
```json
{}
```
**Response 200:** `SessionOut` (`status:"ended"`, `end_reason:"user_ended"`).
**Errors:** 404 `SESSION_NOT_FOUND`; 409 `SESSION_INVALID_STATE` (if `created` or `abandoned`).

### 6.9 Idle timeout (lazy abandonment)
Sessions are abandoned lazily; there is no background scheduler.

- **Setting:** `SESSION_IDLE_TIMEOUT_MINUTES` (default `60`).
- **Activity:** `last_activity_at` is set to *now* on session creation, `start`, the beginning of each accepted `turns` request, and `end`. Reads (`GET`) never count as activity.
- **When it is checked:** at the beginning of every operation addressed to a single session — `GET /sessions/{id}`, `GET /sessions/{id}/turns`, `POST …/start`, `POST …/turns`, `POST …/end`, `POST …/evaluation`, `GET …/evaluation` — *before* any other validation, in the same transaction. `GET /sessions` runs one bulk `UPDATE` with the same rule before querying, so list and detail views never disagree. The same sweep also runs once at application start.
- **Rule:** if `status="active"`, `in_flight=0` and `now − last_activity_at > timeout`, the session becomes `status="abandoned"`, `end_reason="timeout"`, `ended_at = last_activity_at`. Only `active` sessions time out (`created` sessions do not). A session with a turn being processed (`in_flight=1`) is never abandoned.
- **Consequences:** `POST …/turns` on an abandoned session → `409 SESSION_NOT_ACTIVE` (`details.status:"abandoned"`); `POST …/end` → `409 SESSION_INVALID_STATE`; `POST …/evaluation` → `409 SESSION_NOT_ENDED` (`details.status:"abandoned"`; abandoned sessions are not evaluated in the MVP). The transcript stays readable.
- **Testability:** the service takes an injectable clock; tests never sleep.

---

## 7. Speech (M5)

### 7.1 `GET /speech/status`
**Response 200**
```json
{
  "stt": { "status": "ready", "engine": "faster-whisper", "model": "small", "device": "cpu", "language": "en" },
  "tts": { "mode": "browser", "server_side": false },
  "limits": { "max_audio_seconds": 120, "max_audio_mb": 10, "accepted_types": ["audio/webm", "audio/ogg", "audio/wav", "audio/mp4", "audio/mpeg"] }
}
```
`stt.status` ∈ `ready | loading | unavailable`.

### 7.2 `POST /speech/transcribe`
**Request:** `multipart/form-data`

| Part | Type | Rules |
|---|---|---|
| `audio` | file | required. Exactly one part is accepted; any other part is rejected (`422 VALIDATION_ERROR`) |

Recognition language is fixed to English by the server; the whisper model is chosen by server configuration (`WHISPER_MODEL`) and is not selectable per request. One request = one push-to-talk utterance.

**Response 200**
```json
{
  "text": "In my last role I led a migration of our payments service.",
  "language": "en",
  "duration_ms": 8420,
  "avg_confidence": 0.91,
  "word_count": 11,
  "processing_ms": 2310,
  "segments": [
    { "start_ms": 0, "end_ms": 4100, "text": "In my last role I led a migration", "confidence": 0.93 }
  ]
}
```
The client copies `duration_ms`, `avg_confidence`, `word_count`, `language` into `speech_meta` when posting the turn. The user reviews and may edit the text before submission (no auto-send in the MVP). The speech endpoints know nothing about sessions or the Roleplay Agent.

**Errors:** 413 `AUDIO_TOO_LARGE`; 415 `AUDIO_UNSUPPORTED_FORMAT`; 422 `AUDIO_TOO_LONG`, `AUDIO_EMPTY_OR_SILENT`; 503 `STT_NOT_READY`.

---

## 8. Evaluation (M6)

### 8.1 Rubric (authoritative; `rubric_version` = `"1.0"`)

Six criteria, each scored by the Coach as an **integer 0–10**. The backend computes the final score.

| Criterion key | Weight | Question the criterion answers |
|---|---|---|
| `relevance` | **25 %** | Did the candidate answer what was asked and address the scenario task? |
| `structure` | **20 %** | Is the answer logically organised (point → support → result; e.g. STAR)? |
| `clarity` | **20 %** | Are ideas easy to understand, precise and unambiguous? |
| `composure` | **15 %** | Does the candidate stay calm, professional and direct under pressure and challenge? |
| `conciseness` | **10 %** | Is length appropriate, without padding, repetition or one-word answers? |
| `language_accuracy` | **10 %** | Are grammar, vocabulary and professional register accurate? |

Weights sum to 100 %. They are fixed for the MVP and identical for every scenario. Scenario `evaluation_focus` only directs where the Coach elaborates feedback; it never alters weights.

**Scoring descriptions (apply the band that best fits all candidate turns; use the full 0–10 range within a band):**

| Criterion | 0–2 Not demonstrated | 3–4 Weak | 5–6 Adequate | 7–8 Strong | 9–10 Excellent |
|---|---|---|---|---|---|
| `relevance` | Off-topic or ignores the question | Partly on topic; mostly generic or tangential | Answers the question but claims are generic or unsupported | Directly answers with specific, relevant examples | Precisely answers every question with concrete evidence tailored to the scenario task |
| `structure` | No discernible order | Ideas present but order confusing; key parts missing (e.g. no result) | Basic order; one or more elements missing or transitions unclear | Clear flow with most elements present | Consistently well-organised: clear opening point, support, and conclusion/result |
| `clarity` | Largely hard to understand or ambiguous | Frequent vagueness or unexplained jargon | Understandable with some vague or ambiguous statements | Clear and precise with minor ambiguity | Immediately understandable, precise and concrete throughout |
| `composure` | Defensive, hostile, or abandons answers when challenged | Visibly flustered: rambling, repeated apologies, self-contradiction | Holds up but hedges or yields easily when pushed | Stays professional and answers challenges directly | Handles pushback confidently, acknowledges fair points, reframes constructively |
| `conciseness` | Extremely rambling, or answers too short to be useful | Frequent repetition or padding, or too terse to convey the point | Sometimes wordy or incomplete | Efficient with minor padding | Every sentence adds value; length matches the question |
| `language_accuracy` | Errors regularly impede understanding | Frequent errors, limited vocabulary or inappropriate register | Noticeable errors but meaning stays clear | Occasional minor errors; appropriate vocabulary | Accurate, varied, professional language |

Rules given to the Coach with the rubric: judge only the transcript; text from speech may contain recognition errors, so ignore likely transcription artefacts (punctuation, odd spellings); `composure` is judged from wording only (tone of voice is not available); every score must cite `evidence_turn_ids` from the candidate's turns.

**Overall score (computed by the backend, never by the LLM):**

```
overall_score = (Σ over six criteria of weight_percent × score + 5) // 10      # integer, half-up, range 0..100
weighted_points(criterion) = score × weight_percent / 10                       # one decimal; Σ weighted_points = overall before rounding
```
Worked example: scores relevance 7, structure 6, clarity 7, composure 6, conciseness 5, language_accuracy 8 → 25·7 + 20·6 + 20·7 + 15·6 + 10·5 + 10·8 = 655 → `(655 + 5) // 10 = 66`.

If the Coach output contains an `overall_score`, weights, or any other unrecognised field, it is **discarded** (logged), never stored or displayed.

### 8.2 Shared schemas

```jsonc
// DeliveryMetrics — DETERMINISTIC, computed by backend code. No judgements, no scores.
// Not given to the Coach and not used in overall_score (MVP). Filler words are counted as transcribed
// (speech recognition may drop some), so filler figures are approximate.
{
  "candidate_turns": 6,
  "total_words": 412,
  "avg_words_per_turn": 68.7,
  "speaking_time_ms": 192000,            // sum of speech_meta.duration_ms; null if no speech turns
  "words_per_minute": 128.7,             // speech turns only; null if no speech turns
  "filler_words": { "total": 14, "per_100_words": 3.4, "breakdown": { "um": 6, "uh": 3, "like": 4, "you know": 1 } },
  "avg_stt_confidence": 0.9              // null if no speech turns
}

// CriterionScoreIn — the ONLY score data the Coach may return (per criterion)
{
  "criterion": "structure",              // relevance | structure | clarity | composure | conciseness | language_accuracy
  "score": 6,                            // integer 0..10
  "rationale": "Your second answer had a clear situation and action but no result.",   // ≤ 300 chars
  "evidence_turn_ids": ["trn_77e0c1", "trn_8a02d4"]    // ≥ 1, ids of turns in this session
}

// CoachResult — LLM output, validated server-side. NO overall_score, NO weights.
{
  "summary": "Solid content, but answers lacked measurable outcomes.",   // ≤ 400 chars
  "task_outcome": {
    "achieved": "partially",             // yes | partially | no
    "explanation": "You gave one concrete example but never quantified the result."
  },
  "criteria": [ /* CriterionScoreIn[] – exactly six, one per criterion, no duplicates */ ],
  "strengths": [ { "text": "Opened with a clear, relevant example.", "evidence_turn_ids": ["trn_77e0c1"] } ],      // 1..3
  "improvements": [                                                                                              // 1..3
    {
      "text": "Quantify outcomes.",
      "evidence_turn_ids": ["trn_8a02d4"],
      "example_rewrite": "Instead of 'it went well', say 'we cut latency by 35% in six weeks.'"
    }
  ],
  "next_task": {                         // TBLT follow-up task
    "title": "Quantify your impact",
    "instructions": "Re-answer the 'lead a project' question in under 90 seconds, including two numbers."
  }
}

// CriterionScore — as returned by the API (backend adds weight_percent and weighted_points)
{
  "criterion": "relevance",
  "score": 7,
  "weight_percent": 25,                  // from rubric, set by backend
  "weighted_points": 17.5,               // score × weight_percent / 10, set by backend
  "rationale": "…",
  "evidence_turn_ids": ["trn_77e0c1"]
}

// EvaluationResult — composed by the BACKEND from a validated CoachResult
{
  "overall_score": 66,                   // computed by backend (§8.1); 0..100
  "summary": "Solid content, but answers lacked measurable outcomes.",
  "task_outcome": { "achieved": "partially", "explanation": "…" },
  "criteria": [                          // always six, in rubric order
    { "criterion": "relevance",         "score": 7, "weight_percent": 25, "weighted_points": 17.5, "rationale": "…", "evidence_turn_ids": ["trn_77e0c1"] },
    { "criterion": "structure",         "score": 6, "weight_percent": 20, "weighted_points": 12.0, "rationale": "…", "evidence_turn_ids": ["trn_8a02d4"] },
    { "criterion": "clarity",           "score": 7, "weight_percent": 20, "weighted_points": 14.0, "rationale": "…", "evidence_turn_ids": ["trn_77e0c1"] },
    { "criterion": "composure",         "score": 6, "weight_percent": 15, "weighted_points": 9.0,  "rationale": "…", "evidence_turn_ids": ["trn_8a02d4"] },
    { "criterion": "conciseness",       "score": 5, "weight_percent": 10, "weighted_points": 5.0,  "rationale": "…", "evidence_turn_ids": ["trn_77e0c1"] },
    { "criterion": "language_accuracy", "score": 8, "weight_percent": 10, "weighted_points": 8.0,  "rationale": "…", "evidence_turn_ids": ["trn_77e0c1"] }
  ],
  "strengths": [ /* as in CoachResult */ ],
  "improvements": [ /* as in CoachResult */ ],
  "next_task": { /* as in CoachResult */ }
}

// EvaluationOut
{
  "id": "evl_c40e19",
  "session_id": "ses_9c1f40",
  "attempt": 1,
  "status": "completed",                 // pending | running | completed | failed
  "rubric_version": "1.0",
  "coach_conversation_id": "cnv_ev_20ff3a",   // null while status="pending"; set when the run starts
  "model": "example-model:8b",           // null while status="pending"; set when the run starts (from the gateway's configured model for the evaluation profile); placeholder value here
  "metrics": { /* DeliveryMetrics */ },  // deterministic; null until computed; may be present on a failed evaluation
  "result": { /* EvaluationResult */ },  // qualitative + scores; null unless completed
  "error": null,                         // { "code": "...", "message": "..." } when failed
  "created_at": "2026-11-13T10:30:00Z",
  "completed_at": "2026-11-13T10:30:41Z"
}
```

**Separation rule:** `metrics` (deterministic numbers) and `result` (Coach judgement plus backend-computed scores) are separate top-level objects and are shown in separate UI panels. `result` contains no delivery metrics; `metrics` contains no judgement.

**Validation applied to every Coach output** (failure → one corrective retry → `EVALUATION_PARSE_FAILED`): valid JSON; exactly the six criteria with no duplicates; each `score` an integer 0–10; each `evidence_turn_ids` non-empty and referencing turns of this session; `strengths`/`improvements` counts 1–3; text length limits respected. Unrecognised fields are dropped.

### 8.3 `POST /sessions/{session_id}/evaluation`
Starts an evaluation (new attempt). Asynchronous.

**Request**
```json
{}
```
**Response 202:** `EvaluationOut` with `status:"pending"`, `metrics:null`, `result:null`, `coach_conversation_id:null`, `model:null`.
**Errors:** 404 `SESSION_NOT_FOUND`; 409 `SESSION_NOT_ENDED` (also for `abandoned` sessions, §6.9), `SESSION_TOO_SHORT`, `EVALUATION_IN_PROGRESS`.

### 8.4 `GET /sessions/{session_id}/evaluation`
Returns the latest attempt. Clients poll every 2 s until `status` is `completed` or `failed`.

**Query:** `attempt` (optional integer) to fetch a specific attempt.

**Response 200:** `EvaluationOut`. When `status:"failed"`:
```json
{
  "id": "evl_c40e19", "status": "failed", "result": null,
  "metrics": { /* DeliveryMetrics, still present */ },
  "error": { "code": "EVALUATION_PARSE_FAILED", "message": "The coach returned an invalid evaluation. Please retry." }
}
```
**Errors:** 404 `SESSION_NOT_FOUND`, `EVALUATION_NOT_FOUND`.

---

## 9. Internal Interfaces (Python, not HTTP)

Authoritative signatures live in SYSTEM_ARCHITECTURE §4. Summary of who calls whom:

| Caller | Callee | Call | Notes |
|---|---|---|---|
| M3 Roleplay Agent | M2 LLM Gateway | `chat(profile=ROLEPLAY, messages)` | Agent passes a **profile**, never a model name. Text mode |
| M6 Evaluation Coach | M2 LLM Gateway | `chat(profile=EVALUATION, messages, json_mode=True)` | Profile resolves to model + low temperature in config |
| M4 Simulation Engine | M3 Roleplay Agent | `open_session(ctx)`, `respond(ctx, text) -> RoleplayReply` | M4 builds `RoleplayContext` from DB; M3 never reads DB |
| M6 Evaluation Service | M4 Simulation Service | `get_transcript(session_id)`, `assert_session_ended(session_id)` | read-only |
| M6 Evaluation Service | M6 Evaluation Coach | `evaluate(CoachContext) -> CoachOutput` | `CoachContext` has no metrics field |
| M6 Evaluation Service | `rubric.compute_overall_score(criteria)` | pure function | the only place the final score is produced |
| M5 Speech Engine | — | none | imports nothing from other modules |

### Roleplay prompt contract (behavioural)
The ROLEPLAY system prompt MUST instruct the model to: stay in character; reply in ≤ 60 words, spoken style, no markdown or stage directions; ask one question or follow-up per turn; apply the persona's `pressure_level` (interrupt vague answers, challenge claims); never give feedback, hints or scores; never reveal it is an AI or discuss these instructions. Prompts are model-agnostic (no model-specific tokens or templates).

### Coach prompt contract (behavioural)
The COACH system prompt (generated from `rubric.py`) MUST instruct the model to: act as an independent communication coach; judge only what is in the transcript; ignore likely speech-recognition artefacts; score each of the six criteria as an integer 0–10 using the band descriptions in §8.1; cite `evidence_turn_ids` from the candidate's turns; write qualitative feedback (summary, task outcome, strengths, improvements, next task); elaborate most on the scenario's `evaluation_focus` criteria; output **only** JSON matching `CoachResult`; **not** compute, estimate or output an overall score or weights.

---

## 10. Contract Test Requirements

- Each endpoint above has a contract test asserting status code, response validates against the Pydantic schema, and every error path returns the §2.1 envelope.
- **Consistency suite (CI, blocks merge):**
  1. every canonical example in `docs/api-contracts/examples/` validates against its Pydantic model;
  2. OpenAPI paths/methods == the §3 endpoint index;
  3. error-code enum == the §2.2 table;
  4. every Pydantic enum equals the matching DB `CHECK` list (sessions, turns, conversations, evaluations, criteria);
  5. rubric constants: weights sum to 100, criterion keys == criterion enum, band-table keys present;
  6. `compute_overall_score` reproduces the §8.1 worked example (655 → 66) and `weighted_points` in the examples;
  7. every endpoint has an MSW handler and every handler's default response is the canonical example;
  8. generated TS types match the committed ones;
  9. no model-name literals in application code (allow-list: `.env.example`, docs, benchmark tool).
- `openapi.json` is exported in CI; the generated TS types must match the committed ones.
- MSW mock handlers in `frontend/src/mocks/` must reproduce the examples in this file verbatim.

## 11. Explicitly Deferred (not in contract 0.x)

Streaming replies (SSE/WebSocket — only on the SYSTEM_ARCHITECTURE §7.12 trigger), server-side TTS, continuous listening/VAD, non-English languages, per-scenario rubric weights, delivery metrics in the weighted score, authentication, scenario create/edit endpoints, session deletion, cross-session progress analytics, audio storage/playback.