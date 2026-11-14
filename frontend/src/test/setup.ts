import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
});

// Mock window.HTMLElement.prototype.scrollIntoView
if (typeof window !== "undefined" && window.HTMLElement) {
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
}

// Mock window.speechSynthesis
if (typeof window !== "undefined") {
  class MockUtterance {
    text: string;
    lang = "en-US";
    rate = 1.0;
    pitch = 1.0;
    volume = 1.0;
    voice = null;
    onend: ((e?: unknown) => void) | null = null;
    onerror: ((e?: unknown) => void) | null = null;
    onstart: ((e?: unknown) => void) | null = null;
    constructor(text: string) {
      this.text = text;
    }
  }

  window.SpeechSynthesisUtterance = MockUtterance as unknown as typeof SpeechSynthesisUtterance;

  const mockSynthesis = {
    speaking: false,
    paused: false,
    pending: false,
    onvoiceschanged: null,
    speak: vi.fn((utterance: SpeechSynthesisUtterance) => {
      setTimeout(() => {
        if (utterance && typeof utterance.onend === "function") {
          utterance.onend(new Event("end") as SpeechSynthesisEvent);
        }
      }, 0);
    }),
    cancel: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    getVoices: vi.fn(() => []),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(() => true),
  };

  Object.defineProperty(window, "speechSynthesis", {
    writable: true,
    configurable: true,
    value: mockSynthesis,
  });
}
