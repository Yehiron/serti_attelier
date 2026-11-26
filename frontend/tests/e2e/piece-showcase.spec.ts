import { expect, test } from './fixtures';
import { adminSession, createPiece } from './support';

test('vitrina, filtros, selección y vista recordada', async ({ page, context, baseURL }) => {
  const piece = createPiece();
  const session = adminSession();
  await context.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const adminRoot = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${adminRoot}catalog/piece/?q=${piece.sku}`);
  const card = page.locator('.showcase-card').first();
  await expect(card).toBeVisible();
  await card.locator('.showcase-actions a[aria-label="Editar"]').click();
  await expect(page.locator('dialog.pe-dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('dialog.pe-dialog')).toBeHidden();
  await card.locator('.showcase-check').check();
  await expect(page.locator('#result_list input[name="_selected_action"]').first()).toBeChecked();
  await page.screenshot({ path: test.info().outputPath('vitrina-movil.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByRole('link', { name: /Vendidas/ }).click();
  await expect(page).toHaveURL(/sale_state__exact=sold/);
  await page.getByRole('button', { name: '☰ Lista' }).click();
  await page.reload();
  await expect(page.getByRole('button', { name: '☰ Lista' })).toHaveAttribute('aria-pressed', 'true');
  expect(errors).toEqual([]);
});
