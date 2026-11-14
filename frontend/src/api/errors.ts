/**
 * Friendly error messages for all API error codes specified in API_CONTRACTS §2.2.
 */

export const CONTRACT_ERROR_CODES = [
  "BAD_REQUEST",
  "SCENARIO_NOT_FOUND",
  "SESSION_NOT_FOUND",
  "EVALUATION_NOT_FOUND",
  "SESSION_INVALID_STATE",
  "SESSION_NOT_ACTIVE",
  "SESSION_NOT_ENDED",
  "TURN_IN_PROGRESS",
  "EVALUATION_IN_PROGRESS",
  "SESSION_TOO_SHORT",
  "AUDIO_TOO_LARGE",
  "AUDIO_UNSUPPORTED_FORMAT",
  "VALIDATION_ERROR",
  "AUDIO_TOO_LONG",
  "AUDIO_EMPTY_OR_SILENT",
  "INTERNAL_ERROR",
  "NOT_IMPLEMENTED",
  "LLM_BAD_OUTPUT",
  "EVALUATION_PARSE_FAILED",
  "LLM_UNAVAILABLE",
  "LLM_MODEL_NOT_FOUND",
  "STT_NOT_READY",
  "STT_UNAVAILABLE",
  "LLM_TIMEOUT",
] as const;

export type ContractErrorCode = (typeof CONTRACT_ERROR_CODES)[number];

export const ERROR_MESSAGES: Record<ContractErrorCode, string> = {
  BAD_REQUEST:
    "The request was malformed or invalid. Please check your input and try again.",
  SCENARIO_NOT_FOUND:
    "The selected scenario could not be found. It may have been removed.",
  SESSION_NOT_FOUND:
    "The requested practice session does not exist.",
  EVALUATION_NOT_FOUND:
    "No evaluation has been requested for this session yet.",
  SESSION_INVALID_STATE:
    "This action cannot be performed in the current session state.",
  SESSION_NOT_ACTIVE:
    "This practice session is no longer active. Turns can only be submitted during an active session.",
  SESSION_NOT_ENDED:
    "The session must be ended before requesting an evaluation.",
  TURN_IN_PROGRESS:
    "Another turn is currently being processed. Please wait for the reply.",
  EVALUATION_IN_PROGRESS:
    "An evaluation is already in progress for this session. Please wait.",
  SESSION_TOO_SHORT:
    "The session has no candidate responses to evaluate. Complete at least one turn before requesting feedback.",
  AUDIO_TOO_LARGE:
    "The recorded audio exceeds the maximum file size limit (10MB). Please try a shorter response.",
  AUDIO_UNSUPPORTED_FORMAT:
    "The audio format is not supported by the speech recognition engine.",
  VALIDATION_ERROR:
    "Validation failed on submitted data. Please verify your input and try again.",
  AUDIO_TOO_LONG:
    "The audio recording exceeds the maximum duration limit. Please speak more concisely.",
  AUDIO_EMPTY_OR_SILENT:
    "No speech was detected in your recording. Please check your microphone, speak clearly, and retry.",
  INTERNAL_ERROR:
    "An internal server error occurred. Please try again later.",
  NOT_IMPLEMENTED:
    "This feature is not implemented yet.",
  LLM_BAD_OUTPUT:
    "The AI roleplay assistant returned an unexpected response format. Please retry.",
  EVALUATION_PARSE_FAILED:
    "The coach evaluation output could not be parsed. Please click Retry to generate feedback again.",
  LLM_UNAVAILABLE:
    "The configured AI provider is unreachable. Check its URL, credentials, and network connection.",
  LLM_MODEL_NOT_FOUND:
    "The configured model was not found by the active AI provider. Check the provider and model settings.",
  STT_NOT_READY:
    "The speech recognition engine is still loading. Please wait a moment and try again.",
  STT_UNAVAILABLE:
    "Speech recognition is currently unavailable on the server. Please use text input or your browser's speech recognition.",
  LLM_TIMEOUT:
    "The AI assistant request timed out. Please try your request again.",
};

export const DEFAULT_FALLBACK_ERROR =
  "An unexpected error occurred. Please try again.";

/**
 * Returns a friendly, human-readable error message for any API error code.
 */
export function getErrorMessage(
  code?: string | null,
  fallbackMessage?: string | null,
): string {
  if (
    (
      code === "LLM_BAD_OUTPUT" ||
      code === "LLM_UNAVAILABLE" ||
      code === "LLM_MODEL_NOT_FOUND"
    ) &&
    fallbackMessage?.trim()
  ) {
    return fallbackMessage;
  }
  if (code && code in ERROR_MESSAGES) {
    return ERROR_MESSAGES[code as ContractErrorCode];
  }
  if (fallbackMessage && fallbackMessage.trim().length > 0) {
    return fallbackMessage;
  }
  return DEFAULT_FALLBACK_ERROR;
}
