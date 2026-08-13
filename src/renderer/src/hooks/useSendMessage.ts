import { useCallback, useRef, useState } from 'react';

export type ChatRole = 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  status?: 'sending' | 'sent' | 'failed';
  createdAt: number;
}

export interface UseSendMessageOptions {
  appendMessage: (message: ChatMessage) => void;
  sendMessageToBackend: (content: string) => Promise<void>;
  clearInput?: () => void;
  onFailed?: (messageId: string, error: unknown) => void;
  ensureConversationReady?: () => Promise<void> | void;
  onSettled?: () => void;
}

export function useSendMessage(options: UseSendMessageOptions) {
  const {
    appendMessage,
    sendMessageToBackend,
    clearInput,
    onFailed,
    ensureConversationReady,
    onSettled,
  } = options;

  const [isSending, setIsSending] = useState(false);
  const sendingRef = useRef(false);

  const sendMessage = useCallback(
    async (rawContent: string) => {
      const content = rawContent.trim();
      if (!content) return;

      // Prevent duplicate submissions while the first request is still being prepared.
      if (sendingRef.current) return;

      const tempId = `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;

      // Optimistically render the user bubble immediately so the UI stays responsive.
      sendingRef.current = true;
      setIsSending(true);
      clearInput?.();

      appendMessage({
        id: tempId,
        role: 'user',
        content,
        status: 'sending',
        createdAt: Date.now(),
      });

      // Prepare the conversation in the background, but never block the optimistic UI update.
      const readyPromise = ensureConversationReady?.();

      try {
        await Promise.resolve(readyPromise);
        await sendMessageToBackend(content);
      } catch (error) {
        onFailed?.(tempId, error);
      } finally {
        sendingRef.current = false;
        setIsSending(false);
        onSettled?.();
      }
    },
    [appendMessage, clearInput, ensureConversationReady, onFailed, onSettled, sendMessageToBackend]
  );

  return { sendMessage, isSending };
}
