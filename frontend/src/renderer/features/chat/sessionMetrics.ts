import type { ChatMessage } from "./state";

export function latestSessionTokenTotal(
  activeSessionId: number | null,
  messagesBySession: Record<number, ChatMessage[] | undefined>,
) {
  if (!activeSessionId) return 0;
  const messages = messagesBySession[activeSessionId];
  if (!messages?.length) return 0;

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.isTyping) continue;
    const token = message.token_total ?? message.token_output;
    if (token != null) return token;
  }

  return 0;
}
