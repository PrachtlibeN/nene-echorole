import { describe, expect, it } from "vitest";

import { CONTRACT_ERROR_CODES, DEFAULT_FALLBACK_ERROR, ERROR_MESSAGES, getErrorMessage } from "./errors";

describe("API Error Code Handling (API_CONTRACTS §2.2)", () => {
  it("defines friendly messages for all 24 error codes", () => {
    expect(CONTRACT_ERROR_CODES.length).toBe(24);

    for (const code of CONTRACT_ERROR_CODES) {
      const message = ERROR_MESSAGES[code];
      expect(message).toBeDefined();
      expect(typeof message).toBe("string");
      expect(message.trim().length).toBeGreaterThan(10);
    }
  });

  describe("getErrorMessage()", () => {
    it.each(CONTRACT_ERROR_CODES)("returns friendly message for %s", (code) => {
      const message = getErrorMessage(code);
      expect(message).toBe(ERROR_MESSAGES[code]);
      expect(message).not.toBe(DEFAULT_FALLBACK_ERROR);
    });

    it("falls back to custom message when code is unknown", () => {
      const custom = "Something specific went wrong";
      expect(getErrorMessage("UNKNOWN_CODE", custom)).toBe(custom);
    });

    it("falls back to default message when code is unknown and no fallback is given", () => {
      expect(getErrorMessage("UNKNOWN_CODE")).toBe(DEFAULT_FALLBACK_ERROR);
      expect(getErrorMessage(null)).toBe(DEFAULT_FALLBACK_ERROR);
      expect(getErrorMessage(undefined)).toBe(DEFAULT_FALLBACK_ERROR);
    });

    it("prefers known code message over custom fallback", () => {
      expect(getErrorMessage("AUDIO_EMPTY_OR_SILENT", "custom text")).toBe(
        ERROR_MESSAGES.AUDIO_EMPTY_OR_SILENT,
      );
    });

    it.each([
      "LLM_BAD_OUTPUT",
      "LLM_UNAVAILABLE",
      "LLM_MODEL_NOT_FOUND",
    ] as const)(
      "uses the server diagnostic for %s",
      (code) => {
        const providerMessage =
          code === "LLM_BAD_OUTPUT"
            ? "OpenAI-compatible provider rejected the request."
            : "The OpenAI-compatible endpoint returned HTTP 404. Verify OPENAI_BASE_URL.";
        expect(getErrorMessage(code, providerMessage)).toBe(providerMessage);
      },
    );
  });
});
