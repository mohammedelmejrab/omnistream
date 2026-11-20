import { expect, test } from '@playwright/test';
import { askFromHome, expectNoHorizontalScroll, finishedRun, SCREENS } from './helpers';

const WIDTHS = [360, 640, 768, 1024, 1280, 1440];

test('no route scrolls sideways at narrow widths or at 200% zoom (640 CSS px)', async ({ page, request }) => {
  const { runId } = await finishedRun(request, 'Who leads Acme?', 'agentic');
  const routes = [
    '/app/',
    '/app/chats',
    '/app/sources',
    '/app/graph',
    '/app/settings',
    `/app/trace/${runId}`,
    `/app/trace/${runId}?view=advanced`,
  ];
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of routes) {
      await page.goto(route);
      await expect(page.locator('h1').first()).toBeVisible();
      await expectNoHorizontalScroll(page, `${route} at ${width}px`);
    }
  }
});

test('detail panel sits beside the graph at 1280px and up, and overlays it below without covering the focused node', async ({
  page,
  request,
}) => {
  const { runId } = await finishedRun(request, 'Who leads Acme?', 'agentic');
  const canvas = page.getByTestId('graph-canvas');
  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/app/trace/${runId}?view=advanced`);
    const options = page.getByRole('listbox', { name: 'Steps and items in this run' }).getByRole('option');
    await options.nth(1).focus();
    await page.keyboard.press('Enter');

    const panel = page.locator('.detail-panel');
    await expect(panel).toBeVisible();
    const p = await panel.boundingBox();
    const c = await canvas.boundingBox();
    expect(p && c, 'panel and canvas are laid out').toBeTruthy();
    if (!p || !c) continue;

    // The focused node, in page coordinates.
    await expect(canvas).toHaveAttribute('data-active-x', /.+/);
    const nodeX = c.x + Number(await canvas.getAttribute('data-active-x'));
    const nodeY = c.y + Number(await canvas.getAttribute('data-active-y'));
    const covered = nodeX >= p.x && nodeX <= p.x + p.width && nodeY >= p.y && nodeY <= p.y + p.height;
    expect(covered, `focused node is not under the panel at ${width}px`).toBe(false);

    const beside = p.x >= c.x + c.width - 1;
    if (width >= 1280) {
      expect(beside, `panel beside the graph at ${width}px`).toBe(true);
    } else {
      expect(beside, `panel overlays the graph at ${width}px`).toBe(false);
      expect(p.x < c.x + c.width && p.x + p.width > c.x, 'overlay covers part of the graph').toBe(true);
    }
    await page.keyboard.press('Escape');
    await expect(panel).toHaveCount(0);
  }
});

test('route change sets the document title and moves focus to the heading', async ({ page, request }) => {
  const { runId } = await finishedRun(request, 'Who leads Acme?');
  await askFromHome(page, 'Who leads Acme again?');
  await page.goto(`/app/trace/${runId}`);
  await expect(page).toHaveTitle(/Trace/);
  await page.getByRole('link', { name: 'Back to chat' }).click();
  await expect(page).toHaveURL(/\/app\/chat\//);
  await expect(page).not.toHaveTitle(/Trace/);
  await expect(page.locator('h1').first()).toBeFocused();
});

test('screenshots of home and the trace at laptop and narrow widths', async ({ page, request }) => {
  const { runId } = await finishedRun(request, 'Who leads Acme?', 'agentic');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/app/');
  await expect(page.getByLabel('Your question')).toBeVisible();
  await page.screenshot({ path: `${SCREENS}home-1440.png`, fullPage: true });

  await page.goto(`/app/trace/${runId}?view=advanced`);
  await page.getByRole('listbox', { name: 'Steps and items in this run' }).getByRole('option').nth(1).focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.detail-panel')).toBeVisible();
  await page.screenshot({ path: `${SCREENS}trace-advanced-panel-1440.png`, fullPage: true });

  await page.setViewportSize({ width: 1024, height: 900 });
  await page.screenshot({ path: `${SCREENS}trace-advanced-panel-overlay-1024.png`, fullPage: true });

  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto(`/app/trace/${runId}`);
  await expect(page.getByRole('list', { name: 'Trace stages' })).toBeVisible();
  await page.screenshot({ path: `${SCREENS}trace-simple-360.png`, fullPage: true });
});
