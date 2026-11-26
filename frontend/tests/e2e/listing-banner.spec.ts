import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './fixtures';

test.use({ reducedMotion: 'reduce' });

test('category banner filters by stone and fits mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/es/joyeria/anillos');
  const main = page.locator('main:visible');
  const banner = main.locator('.listing-banner');
  await expect(banner.getByRole('heading', { level: 1, name: 'Anillos' })).toBeVisible();
  await expect(banner.locator('img')).toBeVisible();
  await expect(banner.locator('.listing-banner__count')).toBeVisible();
  const stone = banner.locator('.listing-banner__chips a[href*="stone="]').first();
  await expect(stone).toBeVisible();
  const label = await stone.textContent();
  await stone.click();
  await expect(page).toHaveURL(/stone=/);
  await expect(page.locator('main:visible .listing-banner__chips').getByRole('link', { name: label! })).toHaveAttribute('aria-current', 'true');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const axe = await new AxeBuilder({ page }).include('.listing-banner').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(axe.violations.map(v => v.id)).toEqual([]);
});

test('a collection banner never leaves an empty description gap', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/es/colecciones/novedades-y-destacados');
  const banner = page.locator('main:visible .listing-banner');
  await expect(banner.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(banner.locator('.listing-banner__description:empty')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
