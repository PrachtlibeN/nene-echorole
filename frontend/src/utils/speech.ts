/**
 * Safe wrapper for browser SpeechSynthesis API.
 */

export interface SpeechSynthesisController {
  speak: (text: string, onEnd?: () => void, onError?: () => void) => void;
  speakSequence: (
    items: SpeechSequenceItem[],
    onEnd?: () => void,
    onError?: () => void,
  ) => void;
  stop: () => void;
  isSpeaking: () => boolean;
  isSupported: () => boolean;
}

export interface SpeechSequenceItem {
  text: string;
  voiceGender?: "male" | "female";
}

export function createSpeechSynthesisController(): SpeechSynthesisController {
  const isSupported = (): boolean => {
    return (
      typeof window !== "undefined" &&
      "speechSynthesis" in window &&
      typeof window.SpeechSynthesisUtterance !== "undefined"
    );
  };

  const stop = (): void => {
    if (isSupported()) {
      try {
        window.speechSynthesis.cancel();
      } catch {
        // ignore errors on cancel
      }
    }
  };

  const isSpeaking = (): boolean => {
    if (!isSupported()) return false;
    return window.speechSynthesis.speaking;
  };

  const speak = (
    text: string,
    onEnd?: () => void,
    onError?: () => void,
  ): void => {
    speakSequence([{ text }], onEnd, onError);
  };

  const voiceForGender = (
    gender: SpeechSequenceItem["voiceGender"],
  ): SpeechSynthesisVoice | undefined => {
    if (!isSupported() || !gender) return undefined;
    const voices = window.speechSynthesis.getVoices();
    const englishVoices = voices.filter((voice) =>
      voice.lang.toLowerCase().startsWith("en"),
    );
    if (englishVoices.length === 0) return undefined;

    const maleHint = /\b(male|man|david|mark|daniel|james|alex)\b/i;
    const femaleHint = /\b(female|woman|zira|susan|samantha|karen|aria)\b/i;
    const maleVoice = englishVoices.find((voice) => maleHint.test(voice.name));
    const femaleVoice = englishVoices.find((voice) => femaleHint.test(voice.name));

    if (gender === "male") {
      return (
        maleVoice ??
        englishVoices.find((voice) => voice !== femaleVoice) ??
        englishVoices[0]
      );
    }

    return (
      femaleVoice ??
      englishVoices.find((voice) => voice !== maleVoice) ??
      englishVoices[1] ??
      englishVoices[0]
    );
  };

  const speakSequence = (
    items: SpeechSequenceItem[],
    onEnd?: () => void,
    onError?: () => void,
  ): void => {
    const sequence = items.filter((item) => item.text.trim().length > 0);
    if (!isSupported()) {
      onEnd?.();
      return;
    }
    if (sequence.length === 0) {
      onEnd?.();
      return;
    }

    try {
      window.speechSynthesis.cancel();
      let index = 0;
      const speakNext = (): void => {
        const item = sequence[index];
        if (!item) {
          onEnd?.();
          return;
        }

        const utterance = new window.SpeechSynthesisUtterance(item.text);
        utterance.lang = "en-US";
        utterance.rate = 1.0;
        const voice = voiceForGender(item.voiceGender);
        if (voice) utterance.voice = voice;

        utterance.onend = () => {
          index += 1;
          speakNext();
        };
        utterance.onerror = () => {
          if (onError) {
            onError();
          } else {
            onEnd?.();
          }
        };

        window.speechSynthesis.speak(utterance);
      };

      speakNext();
    } catch {
      if (onError) onError();
      else onEnd?.();
    }
  };

  return {
    speak,
    speakSequence,
    stop,
    isSpeaking,
    isSupported,
  };
}
