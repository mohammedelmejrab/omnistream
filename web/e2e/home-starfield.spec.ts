import { expect, test, type Page } from '@playwright/test';
import { SCREENS } from './helpers';

const STAR_KEY = 'omnistream.backgroundEffects';

/** A cheap fingerprint of what the canvas shows right now. */
async function canvasSnapshot(page: Page): Promise<string> {
  return page.locator('canvas.star-canvas').evaluate((c) => (c as HTMLCanvasElement).toDataURL());
}

/** Pointer position beside the heading words: the warp's home-screen target. */
async function pointerBesideHeading(page: Page): Promise<{ x: number; y: number }> {
  const box = await headingBox(page);
  return { x: box.x + box.width / 2 + 250, y: box.y + box.height / 2 };
}

/** A clip around the pointer, for a close look at the warp. */
function zoomClip(at: { x: number; y: number }) {
  return { x: at.x - 130, y: at.y - 110, width: 260, height: 220 };
}

/** Box of the home heading, for placing the pointer near the text. */
async function headingBox(page: Page) {
  const box = await page.locator('h1.home-heading').boundingBox();
  if (!box) throw new Error('home heading not visible');
  return box;
}

test.describe('home starfield', () => {
  test('is a decorative, non-focusable canvas that fills the viewport', async ({ page }) => {
    await page.goto('/app/');
    const layer = page.getByTestId('star-background');
    await expect(layer).toHaveAttribute('aria-hidden', 'true');
    const canvas = page.locator('canvas.star-canvas');
    await expect(canvas).toHaveAttribute('aria-hidden', 'true');
    await expect(canvas).not.toHaveAttribute('tabindex');
    const size = await page.viewportSize();
    const box = await canvas.boundingBox();
    expect(box?.width).toBe(size?.width);
    expect(box?.height).toBe(size?.height);
  });

  test('is drawn with motion while enabled (twinkle and shots change the canvas)', async ({ page }) => {
    await page.goto('/app/');
    const first = await canvasSnapshot(page);
    await page.waitForTimeout(600);
    expect(await canvasSnapshot(page)).not.toBe(first);
  });

  test('is absent when the Settings toggle is off', async ({ page }) => {
    await page.addInitScript((key) => window.localStorage.setItem(key, 'false'), STAR_KEY);
    await page.goto('/app/');
    await expect(page.getByRole('heading', { name: 'Where should we start?' })).toBeVisible();
    await expect(page.getByTestId('star-background')).toHaveCount(0);
  });

  test('pointer beside the heading warps the field: full and zoomed screenshots', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/app/');
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${SCREENS}stars-home-1440.png` });

    const at = await pointerBesideHeading(page);
    await page.mouse.move(at.x, at.y, { steps: 8 });
    await page.waitForTimeout(300); // inside the 1.5 s hold
    await page.screenshot({ path: `${SCREENS}stars-home-1440-pointer.png` });
    await page.screenshot({ path: `${SCREENS}stars-home-1440-pointer-zoom.png`, clip: zoomClip(at) });
  });

  test('keeps the same look at 1024x768 with and without the pointer', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto('/app/');
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${SCREENS}stars-home-1024.png` });

    const at = await pointerBesideHeading(page);
    await page.mouse.move(at.x, at.y, { steps: 8 });
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${SCREENS}stars-home-1024-pointer.png` });
  });
});

test.describe('home starfield under reduced motion', () => {
  test.use({ reducedMotion: 'reduce' });

  test('still animates: the device motion setting does not stop it', async ({ page }) => {
    await page.goto('/app/');
    await expect(page.locator('canvas.star-canvas')).toHaveCount(1);
    const first = await canvasSnapshot(page);
    expect(first.length).toBeGreaterThan(1000); // stars were drawn
    await page.waitForTimeout(1500);
    expect(await canvasSnapshot(page)).not.toBe(first);
  });

  test('a pointer swirls the field', async ({ page }) => {
    await page.goto('/app/');
    const box = await headingBox(page);
    await page.mouse.move(box.x + box.width + 70, box.y + box.height / 2, { steps: 4 });
    await page.waitForTimeout(300);
    const first = await canvasSnapshot(page);
    await page.waitForTimeout(700);
    expect(await canvasSnapshot(page)).not.toBe(first);
  });
});
