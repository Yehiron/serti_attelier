import { expect, test } from './fixtures';
import { adminSession } from './support';

test('panel del día en móvil', async ({ page, context, baseURL }) => {
  const session = adminSession();
  await context.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dashboard/');
  for (const label of ['Ventas hoy', 'Este mes', 'Piezas en la tienda', 'Mensajes sin responder']) {
    await expect(page.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(page.getByRole('heading', { name: /Pendientes para hoy/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Ventas por mes' })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('panel-del-dia-movil.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});
