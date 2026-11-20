import { request } from './client';
import type { Chat, ChatDetail, RunMode, SendMessageResult } from './types';

export function listChats(signal?: AbortSignal): Promise<Chat[]> {
  return request<Chat[]>('GET', '/chats', undefined, signal);
}

export function createChat(title: string): Promise<Chat> {
  return request<Chat>('POST', '/chats', { title });
}

/**
 * Reads a chat and its messages. The server may send `{chat, messages}` or the
 * chat fields with a `messages` list; both are accepted here.
 */
export async function getChat(id: string, signal?: AbortSignal): Promise<ChatDetail> {
  const body = await request<ChatDetail | (Chat & { messages: ChatDetail['messages'] })>(
    'GET',
    `/chats/${encodeURIComponent(id)}`,
    undefined,
    signal,
  );
  if ('chat' in body) return body;
  const { messages, ...chatFields } = body;
  return { chat: chatFields, messages };
}

export function renameChat(id: string, title: string): Promise<Chat> {
  return request<Chat>('PATCH', `/chats/${encodeURIComponent(id)}`, { title });
}

export function deleteChat(id: string): Promise<void> {
  return request<void>('DELETE', `/chats/${encodeURIComponent(id)}`);
}

export interface SendMessageInput {
  content: string;
  mode: RunMode;
  /** Omitted means "search every bubble". */
  bubble_ids?: string[];
}

export function sendMessage(chatId: string, input: SendMessageInput): Promise<SendMessageResult> {
  return request<SendMessageResult>('POST', `/chats/${encodeURIComponent(chatId)}/messages`, input);
}
