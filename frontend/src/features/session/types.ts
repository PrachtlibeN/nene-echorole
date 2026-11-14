export type PushToTalkState =
  | "idle"
  | "recording"
  | "transcribing"
  | "review"
  | "sending"
  | "waiting_reply"
  | "speaking";

export type InteractionMode = "hold" | "toggle";
