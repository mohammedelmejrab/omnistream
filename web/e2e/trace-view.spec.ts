import { expect, test } from '@playwright/test';
import { finishedRun, replayPosition, SCREENS } from './helpers';

test.describe('simple view and replay', () => {
  test('four stages read in words, and replay steps through the run', async ({ page, request }) => {
    const { runId } = await finishedRun(request, 'Who leads Acme?', 'agentic');
    await page.goto(`/app/trace/${runId}`);
    const stages = page.getByRole('list', { name: 'Trace stages' });
    await expect(stages.locator('.stage-title')).toHaveCount(4);
    await expect(stages.getByText('Done', { exact: false })).toHaveCount(4);
    await expect(page.getByRole('list', { name: 'Bubbles searched' }).first()).toContainText('news');
    await expect(page.getByRole('list', { name: 'Cited sources' })).toContainText('Item one');

    // Replay pinned to the end on open: the full result is visible without pressing anything.
    const end = await replayPosition(page);
    expect(end.cursor).toBe(end.total);

    // Replay restarts and plays; pause it, then step by hand.
    await page.getByRole('button', { name: 'Replay', exact: true }).click();
    await page.getByRole('button', { name: 'Pause' }).click();
    await expect(page.getByRole('button', { name: 'Play', exact: true })).toBeVisible();
    const at = await replayPosition(page);
    expect(at.total).toBe(end.total);
    await page.getByRole('button', { name: 'Step forward' }).click();
    await expect(page.locator('.replay-position')).toHaveText(`Step ${at.cursor + 1} of ${at.total}`);
    await page.getByRole('button', { name: 'Step back' }).click();
    await expect(page.locator('.replay-position')).toHaveText(`Step ${at.cursor} of ${at.total}`);

    await page.getByLabel('Speed').selectOption('0.5');
    await page.getByRole('button', { name: 'Play', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible();
    await page.getByRole('button', { name: 'Pause' }).click();
    await expect(page.getByRole('button', { name: 'Play', exact: true })).toBeVisible();
  });

  test('a stage can be opened from the timeline and the answer sits above the stages', async ({ page, request }) => {
    const { runId } = await finishedRun(request, 'Who leads Acme?');
    await page.goto(`/app/trace/${runId}`);
    const answer = page.getByRole('region', { name: 'Answer' });
    const stageList = page.getByRole('list', { name: 'Trace stages' });
    const a = await answer.boundingBox();
    const s = await stageList.boundingBox();
    expect(a && s && a.y < s.y).toBe(true);
    await expect(answer).toContainText('Alice leads Acme [1].');
  });
});

test.describe('advanced graph, keyboard path', () => {
  test('list arrows move, Enter opens the panel, Esc closes it and returns focus', async ({ page, request }) => {
    const { runId } = await finishedRun(request, 'Who leads Acme?', 'agentic');
    await page.goto(`/app/trace/${runId}?view=advanced`);
    const list = page.getByRole('listbox', { name: 'Steps and items in this run' });
    await expect(list).toBeVisible();
    const options = list.getByRole('option');
    await expect(options.first()).toBeVisible();
    const count = await options.count();
    expect(count).toBeGreaterThan(2);

    await options.first().focus();
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowDown');
    await expect(options.nth(2)).toBeFocused();
    await page.keyboard.press('End');
    await expect(options.nth(count - 1)).toBeFocused();
    await page.keyboard.press('Home');
    await expect(options.first()).toBeFocused();

    await page.keyboard.press('ArrowDown');
    const opened = options.nth(1);
    await expect(opened).toBeFocused();
    await page.keyboard.press('Enter');
    const panel = page.locator('.detail-panel');
    await expect(panel).toBeVisible();
    const focusInPanel = await page.evaluate(() => {
      const panelEl = document.querySelector('.detail-panel');
      return !!panelEl && panelEl.contains(document.activeElement);
    });
    expect(focusInPanel, 'focus moves into the detail panel').toBe(true);

    await page.keyboard.press('Escape');
    await expect(panel).toHaveCount(0);
    await expect(opened).toBeFocused();
  });

  test('zoom in, zoom out and fit are buttons and change the view without dragging', async ({ page, request }) => {
    const { runId } = await finishedRun(request, 'Who leads Acme?', 'agentic');
    await page.goto(`/app/trace/${runId}?view=advanced`);
    const canvas = page.getByTestId('graph-canvas');
    await expect(canvas).toHaveAttribute('data-zoom', /.+/);
    const fitted = Number(await canvas.getAttribute('data-zoom'));

    await page.getByRole('button', { name: 'Zoom in' }).click();
    const zoomed = Number(await canvas.getAttribute('data-zoom'));
    expect(zoomed).toBeGreaterThan(fitted);

    await page.getByRole('button', { name: 'Zoom out' }).click();
    await page.getByRole('button', { name: 'Zoom out' }).click();
    expect(Number(await canvas.getAttribute('data-zoom'))).toBeLessThan(fitted);

    await page.getByRole('button', { name: 'Fit', exact: true }).click();
    expect(Number(await canvas.getAttribute('data-zoom'))).toBeCloseTo(fitted, 2);
  });

  test('step rows are distinct and entity groups name their bubble', async ({ page, request }) => {
    const { runId } = await finishedRun(request, 'Who leads Acme?', 'agentic');
    await page.goto(`/app/trace/${runId}?view=advanced`);
    await expect(page.getByRole('listbox', { name: 'Steps and items in this run' }).getByRole('option').first()).toBeVisible();
    const rows = await page
      .getByRole('listbox', { name: 'Steps and items in this run' })
      .getByRole('option')
      .evaluateAll((els) => els.map((el) => (el as HTMLElement).innerText.split('\n')[0]));
    expect(new Set(rows).size, `duplicate rows in ${JSON.stringify(rows)}`).toBe(rows.length);
    expect(rows).toContain('Picked entities for news');
    expect(rows).toContain('Scored finance evidence');
    expect(rows.filter((r) => /entities and chunks/.test(r)).every((r) => /^(news|finance): /.test(r))).toBe(true);
  });

  test('timeline bars are proportional to duration with a 4px minimum', async ({ page, request }) => {
    const { runId } = await finishedRun(request, 'Who leads Acme?', 'agentic');
    await page.goto(`/app/trace/${runId}?view=advanced`);
    await expect(page.locator('.advanced-trace .timeline-bar').nth(5)).toBeVisible();
    const bars = await page.locator('.advanced-trace .timeline-bar').evaluateAll((els) =>
      els.map((el) => ({
        width: el.getBoundingClientRect().width,
        ms: Number((el.getAttribute('aria-label') ?? '').match(/([\d.]+) ms/)?.[1] ?? NaN),
      })),
    );
    expect(bars.length).toBeGreaterThan(5);
    for (const b of bars) expect(b.width, 'minimum width').toBeGreaterThanOrEqual(3.9);
    // Long steps (500 ms and up) share one scale, so width per millisecond agrees.
    const long = bars.filter((b) => b.ms >= 500);
    expect(long.length).toBeGreaterThan(1);
    const scale = long[0].width / long[0].ms;
    for (const b of long) expect(b.width / b.ms).toBeCloseTo(scale, 1);
  });

  test('node targets are at least 24 by 24 pixels', async ({ page, request }) => {
    const { runId } = await finishedRun(request, 'Who leads Acme?', 'agentic');
    await page.goto(`/app/trace/${runId}?view=advanced`);
    for (const name of ['Zoom in', 'Zoom out']) {
      const box = await page.getByRole('button', { name }).boundingBox();
      expect(box && box.width >= 24 && box.height >= 24, `${name} target size`).toBe(true);
    }
    const first = await page.getByRole('listbox', { name: 'Steps and items in this run' }).getByRole('option').first().boundingBox();
    expect(first && first.height >= 24).toBe(true);
  });
});

test.describe('reduced motion', () => {
  test.use({ reducedMotion: 'reduce' });

  test('Play becomes Show all steps and no pulse is drawn', async ({ page, request }) => {
    const { runId } = await finishedRun(request, 'Who leads Acme?', 'agentic');
    await page.goto(`/app/trace/${runId}?view=advanced`);
    const show = page.getByRole('button', { name: 'Show all steps' });
    await expect(show).toBeVisible();
    const end = await replayPosition(page);
    expect(end.cursor).toBe(end.total);
    // Steps can still be stepped through by hand.
    await page.getByRole('button', { name: 'Step back' }).click();
    await expect(page.locator('.replay-position')).toHaveText(`Step ${end.total - 1} of ${end.total}`);
    await show.click();
    await expect(page.locator('.replay-position')).toHaveText(`Step ${end.total} of ${end.total}`);
    const pulsing = await page.locator('[data-testid="graph-canvas"]').evaluate(() => document.querySelectorAll('.pulse').length);
    expect(pulsing).toBe(0);
  });
});

test('screenshots of the trace for review', async ({ page, request }) => {
  const { runId } = await finishedRun(request, 'Who leads Acme?', 'agentic');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/app/trace/${runId}`);
  await expect(page.getByRole('list', { name: 'Trace stages' })).toBeVisible();
  await page.screenshot({ path: `${SCREENS}trace-simple-1440.png`, fullPage: true });
  await page.goto(`/app/trace/${runId}?view=advanced`);
  await expect(page.getByTestId('graph-canvas')).toBeVisible();
  await page.screenshot({ path: `${SCREENS}trace-advanced-1440.png`, fullPage: true });
});
