import { afterEach, describe, expect, it, vi } from "vitest";

import { createSpeechSynthesisController } from "./speech";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SpeechSynthesisController", () => {
  it("queues panel turns and selects distinct gender-matched voices", () => {
    const maleVoice = {
      name: "Microsoft David",
      lang: "en-US",
    } as SpeechSynthesisVoice;
    const femaleVoice = {
      name: "Microsoft Zira",
      lang: "en-US",
    } as SpeechSynthesisVoice;
    const utterances: SpeechSynthesisUtterance[] = [];
    vi.spyOn(window.speechSynthesis, "getVoices")
      .mockReturnValue([maleVoice, femaleVoice]);
    vi.spyOn(window.speechSynthesis, "speak").mockImplementation((utterance) => {
      utterances.push(utterance);
    });
    const onEnd = vi.fn();

    createSpeechSynthesisController().speakSequence(
      [
        { text: "First panel turn", voiceGender: "male" },
        { text: "Second panel turn", voiceGender: "female" },
      ],
      onEnd,
    );

    expect(utterances).toHaveLength(1);
    expect(utterances[0]?.text).toBe("First panel turn");
    expect(utterances[0]?.voice).toBe(maleVoice);

    utterances[0]?.onend?.(new Event("end") as SpeechSynthesisEvent);

    expect(utterances).toHaveLength(2);
    expect(utterances[1]?.text).toBe("Second panel turn");
    expect(utterances[1]?.voice).toBe(femaleVoice);

    utterances[1]?.onend?.(new Event("end") as SpeechSynthesisEvent);
    expect(onEnd).toHaveBeenCalledOnce();
  });
});
