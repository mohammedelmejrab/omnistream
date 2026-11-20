import { describe, expect, it } from 'vitest';
import { mockApi, iso } from '@/test/api-mock';
import { getChat } from './chats';

const chat = { id: 'c1', title: 'EU energy', mode: 'normal', created_at: iso(), updated_at: iso() };

describe('getChat', () => {
  it('reads the { chat, messages } shape', async () => {
    mockApi(({ path }) => (path === '/chats/c1' ? { json: { chat, messages: [] } } : { status: 500 }));
    await expect(getChat('c1')).resolves.toEqual({ chat, messages: [] });
  });

  it('reads the flat shape the server returns (the chat with a messages list)', async () => {
    const messages = [{ id: 'm1', chat_id: 'c1', role: 'user', content: 'Q', run_id: 'r1', mode: 'normal', created_at: iso() }];
    mockApi(({ path }) => (path === '/chats/c1' ? { json: { ...chat, messages } } : { status: 500 }));
    await expect(getChat('c1')).resolves.toEqual({ chat, messages });
  });
});
