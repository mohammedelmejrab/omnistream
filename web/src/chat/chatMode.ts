import { isRunMode, DEFAULT_MODE } from './modes';
import type { RunMode } from '@/api/types';
import { readPreference, writePreference } from '@/hooks/usePreference';

// Spec 6 and 7: the mode is remembered per chat and is the default for new
// chats in this browser. [Your call] recorded in the handoff.
const DEFAULT_KEY = 'omnistream.defaultMode';

export function chatModeKey(chatId: string): string {
  return `omnistream.chatMode.${chatId}`;
}

export function readChatMode(chatId: string, fallback?: RunMode): RunMode {
  const stored = readPreference<unknown>(chatModeKey(chatId), null);
  if (isRunMode(stored)) return stored;
  return fallback ?? readDefaultMode();
}

export function writeChatMode(chatId: string, mode: RunMode): void {
  writePreference(chatModeKey(chatId), mode);
  writePreference(DEFAULT_KEY, mode);
}

export function readDefaultMode(): RunMode {
  const stored = readPreference<unknown>(DEFAULT_KEY, null);
  return isRunMode(stored) ? stored : DEFAULT_MODE;
}

export function writeDefaultMode(mode: RunMode): void {
  writePreference(DEFAULT_KEY, mode);
}
