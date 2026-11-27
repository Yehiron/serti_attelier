import { test, expect } from './fixtures';
import { adminSession, manage } from './support';

test('la auditoría muestra una línea de tiempo legible', async ({ page, context, baseURL }) => {
  const session = adminSession();
  await context.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  // The audit log is immutable: never insert fake rows. Trigger a real audited action on a
  // throwaway material (e2e_cleanup deletes «e2e-material-<n>»; its audit rows stay, marked as tests).
  const stamp = Date.now();
  manage('shell', '-c', `from apps.catalog import services; from apps.catalog.models import Material; services.save_taxonomy(Material(name_es='E2E material ${stamp}', slug_es='e2e-material-${stamp}'), actor=None)`);
  const errors: Error[] = [];
  page.on('pageerror', error => errors.push(error));
  const root = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  await page.goto(`${root}audit/auditlog/`);
  await expect(page.getByRole('heading', { name: 'Auditoría', exact: true })).toBeVisible();
  const descriptions = await page.locator('.aud-description').allTextContents();
  expect(descriptions.length).toBeGreaterThan(0);
  expect(descriptions.every(text => !/^[a-z]+\.[a-z_]+$/.test(text.trim()))).toBeTruthy();
  await page.getByRole('navigation', { name: 'Módulo' }).getByRole('link', { name: 'Catálogo' }).click();
  await page.getByRole('navigation', { name: 'Periodo' }).getByRole('link', { name: 'Hoy' }).click();
  await page.locator('.aud-details summary').first().click();
  await expect(page.locator('.aud-details[open]').first()).toBeVisible();
  await expect(page.getByText(`E2E material ${stamp}`)).toHaveCount(0); // hidden by default
  // The switch is a link: wait for the new page before checking its state.
  await Promise.all([page.waitForURL(/pruebas=mostrar/), page.getByRole('switch', { name: 'Ocultar pruebas automáticas' }).click()]);
  await expect(page.getByRole('switch', { name: 'Ocultar pruebas automáticas' })).toHaveAttribute('aria-checked', 'false');
  await expect(page.getByText(`E2E material ${stamp}`).first()).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});
