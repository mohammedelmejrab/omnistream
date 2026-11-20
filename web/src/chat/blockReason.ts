import type { Bubble, ProviderSettings } from '@/api/types';
import type { BlockReason } from './Composer';

/**
 * Reasons sending is disabled outside the input itself (spec 6 and 13).
 * While settings or bubbles are still loading nothing is blocked; the server
 * still validates the request.
 */
export function composeBlockReason(input: {
  online: boolean;
  provider: ProviderSettings | undefined;
  bubbles: readonly Bubble[] | undefined;
}): BlockReason | null {
  if (!input.online) {
    return { text: "You're offline. Sending is disabled until the connection returns." };
  }
  if (input.provider && !input.provider.key_set && input.provider.key_source === null) {
    return { text: 'No provider key is set, so questions cannot be answered yet.', to: '/app/settings', linkLabel: 'Add a key in Settings' };
  }
  if (input.bubbles && input.bubbles.length === 0) {
    return { text: 'There is nothing to search yet.', to: '/app/sources', linkLabel: 'Add a source' };
  }
  return null;
}

/** Title for a new chat, from its first question. */
export function titleFromQuestion(text: string): string {
  const oneLine = text.replace(/\s+/g, ' ').trim();
  return oneLine.length > 60 ? `${oneLine.slice(0, 57)}...` : oneLine || 'New chat';
}
