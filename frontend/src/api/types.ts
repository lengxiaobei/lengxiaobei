export type ApiEnvelope<T> = {
  status?: string;
  error?: string;
  result?: T;
  items?: T[];
};

export type ConversationResult = {
  text: string;
  plan?: unknown;
  observation?: unknown;
  recall?: unknown[];
};
