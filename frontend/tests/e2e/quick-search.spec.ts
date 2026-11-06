import { test, expect } from './fixtures';

test('buscador sin desbordamiento, salto de ancho ni desplazamiento del fondo', async ({ page }) => {
  await page.goto('/es');
  const trigger = page.locator('.utilities a[aria-haspopup="dialog"]');
  await expect(trigger).toBeVisible();
  const before = await page.locator('main').evaluate(el => el.getBoundingClientRect().width);
  const dialog = page.locator('dialog.search-dialog');
  await expect(async () => {
    await trigger.click();
    await expect(dialog).toBeVisible({ timeout: 1000 });
  }).toPass();
  await expect(dialog.locator('input')).toBeFocused();
  await expect.poll(() => dialog.evaluate(el => el.scrollHeight <= el.clientHeight)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.locator('main').evaluate(el => el.getBoundingClientRect().width)).toBe(before);
  const top = await page.evaluate(() => scrollY);
  await page.mouse.wheel(0, 700);
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(top);
  await page.route('**/api/v1/catalog/pieces?*', route => route.fulfill({ json: {
    results: Array.from({ length: 6 }, (_, i) => ({ sku: `BUS-${i}`, slug: `bus-${i}`, name: `Anillo ${i}`, image: null, price: { amount_cents: 100000 }, sale_price: null })),
  } }));
  await dialog.locator('input').fill('anillo');
  await expect(dialog.locator('.search-suggestions li')).toHaveCount(6);
  await expect.poll(() => dialog.evaluate(el => el.scrollHeight <= el.clientHeight)).toBe(true);
  expect(await page.locator('main').evaluate(el => el.getBoundingClientRect().width)).toBe(before);
  // In a filled type="search" field the first Escape clears the text (native behavior); the next one closes.
  await expect(async () => {
    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible({ timeout: 1000 });
  }).toPass();
  await expect(trigger).toBeFocused();
  expect(await page.locator('main').evaluate(el => el.getBoundingClientRect().width)).toBe(before);
});
