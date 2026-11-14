import React, { useState } from "react";

interface TypedInputFallbackProps {
  isMicDenied: boolean;
  isDisabled: boolean;
  isSending: boolean;
  onSendTyped: (text: string) => void;
}

interface BrowserSpeechRecognitionEvent {
  results: {
    [index: number]: {
      [index: number]: {
        transcript: string;
      };
    };
  };
}

interface BrowserSpeechRecognitionInstance {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null;
  start: () => void;
}

export const TypedInputFallback: React.FC<TypedInputFallbackProps> = ({
  isMicDenied,
  isDisabled,
  isSending,
  onSendTyped,
}) => {
  const [text, setText] = useState<string>("");
  const [isListening, setIsListening] = useState<boolean>(false);

  const isSpeechRecognitionSupported =
    typeof window !== "undefined" &&
    Boolean(
      (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition ||
        (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition,
    );

  const handleWebSpeech = () => {
    if (isListening || isDisabled || isSending) return;
    const windowWithSpeech = window as unknown as {
      SpeechRecognition?: new () => BrowserSpeechRecognitionInstance;
      webkitSpeechRecognition?: new () => BrowserSpeechRecognitionInstance;
    };
    const SpeechRecognitionClass =
      windowWithSpeech.SpeechRecognition || windowWithSpeech.webkitSpeechRecognition;
    if (!SpeechRecognitionClass) return;

    try {
      const recognition = new SpeechRecognitionClass();
      recognition.lang = "en-US";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);
      recognition.onresult = (event: BrowserSpeechRecognitionEvent) => {
        const transcript = event?.results?.[0]?.[0]?.transcript;
        if (transcript) {
          setText((prev) => (prev ? `${prev} ${transcript}` : transcript));
        }
      };
      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim().length === 0 || isDisabled || isSending) return;
    onSendTyped(text.trim());
    setText("");
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
      {isMicDenied && (
        <div
          role="status"
          className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 flex items-start gap-2"
        >
          <svg
            className="h-4 w-4 flex-shrink-0 text-amber-600 mt-0.5"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z"
              clipRule="evenodd"
            />
          </svg>
          <div>
            <span className="font-semibold">Microphone unavailable: </span>
            Microphone access was denied or is not supported. You can practice by typing your responses below.
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-2">
        <label
          htmlFor="typed-response-input"
          className="block text-xs font-semibold uppercase tracking-wider text-slate-500"
        >
          {isMicDenied ? "Type Your Response" : "Or Type Response (Fallback)"}
        </label>
        <div className="relative">
          <textarea
            id="typed-response-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={isDisabled || isSending}
            placeholder={
              isDisabled
                ? "Microphone and typing are locked while interviewer responds..."
                : "Type your answer here and press Send..."
            }
            rows={2}
            maxLength={2000}
            className="w-full rounded-lg border border-slate-300 p-2.5 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-slate-100 disabled:text-slate-400"
          />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-slate-400">
            {text.length}/2000 characters
          </span>
          <div className="flex items-center gap-2">
            {isSpeechRecognitionSupported && (
              <button
                type="button"
                onClick={handleWebSpeech}
                disabled={isDisabled || isSending}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
                aria-label="Use browser speech recognition"
              >
                {isListening ? "Listening..." : "Dictate (Web Speech)"}
              </button>
            )}
            <button
              type="submit"
              onClick={handleSubmit}
              disabled={isDisabled || isSending || text.trim().length === 0}
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 focus:outline-none disabled:opacity-50"
            >
              {isSending ? "Sending..." : "Send Typed Answer"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
