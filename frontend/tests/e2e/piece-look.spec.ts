import { test, expect } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { createPiece } from './support';

test.use({ reducedMotion: 'reduce' });
test('lookbook shows piece, certificate, atelier and related section', async ({ page }) => {
  const piece = createPiece({ hover: true });
  await page.goto(`/es/piezas/${piece.slug_es}`);
  await expect(page.locator('main:visible')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: piece.name })).toBeVisible();
  await expect(page.locator('.piece-look-price:visible')).toBeVisible();
  await expect(page.locator('.piece-look-spec')).toContainText('Código');
  await expect(page.locator('.piece-look-spec')).toContainText(piece.sku);
  await expect(page.locator('.piece-look-atelier')).toContainText('Hecho a mano');
  await expect(page.getByRole('heading', { name: 'Te puede enamorar' })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter(v => v.impact === 'serious' || v.impact === 'critical')).toEqual([]);
});
test('mobile purchase bar fits without horizontal page scrolling', async ({ page }) => {
  const piece = createPiece({ hover: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/es/piezas/${piece.slug_es}`);
  await expect(page.locator('main:visible')).toBeVisible();
  await expect(page.locator('.sticky-piece-cta .button')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
