import { fileURLToPath } from 'node:url';
import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const SCREENS = fileURLToPath(new URL('./screens/', import.meta.url));

/** Sends a question from the home page and waits for the chat page to open. */
export async function askFromHome(page: Page, question: string): Promise<void> {
  await page.goto('/app/');
  await page.getByLabel('Your question').fill(question);
  await page.getByRole('button', { name: 'Send question' }).click();
  await page.waitForURL(/\/app\/chat\//);
}

/** Creates a chat and a run through the API, and waits until the run has finished. */
export async function finishedRun(
  request: APIRequestContext,
  question: string,
  mode: 'normal' | 'agentic' = 'normal',
): Promise<{ runId: string; chatId: string; answer: string }> {
  const chat = await (await request.post('/api/chats', { data: { title: question } })).json();
  const sent = await (
    await request.post(`/api/chats/${chat.id}/messages`, {
      data: { content: question, mode, bubble_ids: ['news', 'finance'] },
    })
  ).json();
  const runId: string = sent.run_id;
  for (let i = 0; i < 60; i++) {
    const run = await (await request.get(`/api/runs/${runId}`)).json();
    if (run.status !== 'running') return { runId, chatId: chat.id, answer: run.answer ?? '' };
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`run ${runId} did not finish`);
}

/** Fails the test when the page scrolls sideways. */
export async function expectNoHorizontalScroll(page: Page, label = 'page'): Promise<void> {
  const overflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(overflow.scroll, `${label} must not scroll sideways`).toBeLessThanOrEqual(overflow.client);
}

/** Current replay cursor and total, read from the position text ("Step 3 of 7"). */
export async function replayPosition(page: Page): Promise<{ cursor: number; total: number }> {
  const text = (await page.locator('.replay-position').textContent()) ?? '';
  const m = text.match(/Step (\d+) of (\d+)/);
  if (!m) throw new Error(`no replay position in "${text}"`);
  return { cursor: Number(m[1]), total: Number(m[2]) };
}
