import { useEffect } from 'react';

// Lets the Recent rail and /app/chats refresh after a chat is created,
// renamed, deleted or receives a message, without a shared store.
const EVENT = 'omnistream:chats-changed';

export function notifyChatsChanged(): void {
  window.dispatchEvent(new Event(EVENT));
}

export function useChatsChanged(onChange: () => void): void {
  useEffect(() => {
    window.addEventListener(EVENT, onChange);
    return () => window.removeEventListener(EVENT, onChange);
  }, [onChange]);
}
