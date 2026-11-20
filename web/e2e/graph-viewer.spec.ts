import { expect, test } from '@playwright/test';
import { finishedRun, expectNoHorizontalScroll, SCREENS } from './helpers';

test.describe('global graph viewer (/app/graph)', () => {
  test('keeps a gutter, fits the graph in view, and Fit leaves it whole', async ({ page, request }) => {
    await finishedRun(request, 'Who leads Acme?', 'agentic');
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/app/graph');
    const canvas = page.getByTestId('graph-canvas');
    await expect(canvas).toBeVisible();
    await expect(canvas).toHaveAttribute('data-zoom', /.+/);

    const title = await page.getByRole('heading', { name: 'Graph', level: 1 }).boundingBox();
    expect(title && title.x >= 16, 'page keeps a side gutter').toBe(true);

    // The focused node sits inside the canvas, not clipped by its edges.
    const box = await canvas.boundingBox();
    const x = Number(await canvas.getAttribute('data-active-x'));
    const y = Number(await canvas.getAttribute('data-active-y'));
    expect(box && x > 0 && x < box.width && y > 0 && y < box.height).toBe(true);

    const fitted = Number(await canvas.getAttribute('data-zoom'));
    await page.getByRole('button', { name: 'Fit', exact: true }).click();
    // Within a hundredth: the first fit and a button fit can differ by a rounding of the width.
    await expect
      .poll(async () => Number(await canvas.getAttribute('data-zoom')))
      .toBeCloseTo(fitted, 1);
    await page.screenshot({ path: `${SCREENS}graph-viewer-1440.png` });
  });

  test('no sideways scroll at a phone width', async ({ page, request }) => {
    await finishedRun(request, 'Who leads Acme?', 'agentic');
    await page.setViewportSize({ width: 360, height: 800 });
    await page.goto('/app/graph');
    await expect(page.getByTestId('graph-canvas')).toBeVisible();
    await expectNoHorizontalScroll(page, '/app/graph');
    await page.screenshot({ path: `${SCREENS}graph-viewer-360.png`, fullPage: true });
  });
});
