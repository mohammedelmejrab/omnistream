import { expect, test } from '@playwright/test';
import { askFromHome } from './helpers';

// One end-to-end pass: ask, watch the trace live, then replay the stored run.
test('send a question, watch the live trace, then replay it', async ({ page }) => {
  await askFromHome(page, 'Who leads Acme?');

  // The chat's answer block links to the trace from the moment the run starts.
  await page.getByRole('link', { name: 'View trace' }).first().click();
  await expect(page).toHaveURL(/\/app\/trace\//);
  await expect(page.getByRole('heading', { level: 1, name: 'Trace' })).toBeVisible();
  await expect(page.locator('.run-status')).toHaveText('Running');

  // Stages are announced in words while the run is live.
  const live = page.locator('[role="status"][aria-live="polite"]');
  await expect(live).toContainText(/Searching|Writing answer|Understanding/, { timeout: 15_000 });

  // The run finishes: the answer appears and all four stages read Done.
  await expect(page.getByText('Alice leads Acme [1].')).toBeVisible({ timeout: 20_000 });
  const stages = page.getByRole('list', { name: 'Trace stages' });
  await expect(stages.getByText('Done', { exact: false })).toHaveCount(4);

  // Replay the stored run from the start.
  await page.getByRole('button', { name: 'Replay', exact: true }).click();
  const position = page.locator('.replay-position');
  await expect(position).toHaveText(/Step 0 of \d+/);
  await page.getByLabel('Speed').selectOption('4');
  await page.getByRole('button', { name: 'Play' }).click();
  const total = Number((await position.textContent())?.match(/of (\d+)/)?.[1] ?? '0');
  expect(total).toBeGreaterThan(0);
  await expect(position).toHaveText(`Step ${total} of ${total}`, { timeout: 15_000 });
});
