import { expect, test } from './fixtures';
import { adminSession, createPiece, manage } from './support';

test('colecciones: agregar, ordenar y guardar', async ({ page, context, baseURL, isMobile }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const first = createPiece(), second = createPiece();
  const pk = manage('shell', '-c', `from apps.catalog.models import Collection; c=Collection.objects.create(name_es='E2E Colección ${stamp}', slug_es='e2e-coleccion-${stamp}'); print(c.pk)`).trim().split('\n').pop();
  const session = adminSession();
  await context.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const root = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  await page.goto(`${root}catalog/collection/?collection=${pk}`);
  for (const item of [first, second]) {
    await page.locator('[data-search]').fill(item.sku);
    await page.locator('.collection-item button').click();
  }
  const cards = page.locator('.collection-card');
  await cards.nth(1).focus();
  await page.keyboard.press('ArrowLeft');
  await page.getByRole('button', { name: 'Guardar colección' }).click();
  await expect(page.locator('[data-message]')).toHaveText('Colección guardada.');
  await page.reload();
  await expect(cards.nth(0)).toContainText(second.name);
  await expect(cards.nth(1)).toContainText(first.name);
  await page.screenshot({ path: test.info().outputPath(`colecciones-${isMobile ? 'movil' : 'escritorio'}.png`), fullPage: true });
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
