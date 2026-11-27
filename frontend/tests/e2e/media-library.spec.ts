import { test, expect } from './fixtures';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { adminSession } from './support';

test('biblioteca: describir, filtrar y archivar una foto', async ({ page, context }) => {
  const session = adminSession();
  const root = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  const description = `Portada de prueba ${Date.now()}`;
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.addCookies([{ name: 'sessionid', value: session.value, url: 'http://localhost:8090' }]);
  await page.goto(`${root}biblioteca/`);
  const [upload] = await Promise.all([
    page.waitForResponse(response => response.url().endsWith('/biblioteca/api/') && response.request().method() === 'POST'),
    page.getByLabel('Subir nuevas fotos').setInputFiles({ name: 'foto.png', mimeType: 'image/png', buffer: Buffer.concat([readFileSync(resolve(__dirname, 'fixtures/cms-carousel-mobile.png')), Buffer.from(description)]) }),
  ]);
  const id = (await upload.json()).items[0].asset.id;
  await expect.poll(async () => (await (await context.request.get(`${root}biblioteca/api/${id}/`)).json()).state, { timeout: 60_000 }).toBe('ready');
  await expect(page.getByRole('status')).not.toContainText('Preparando versiones', { timeout: 60_000 });
  const detail = page.getByRole('complementary', { name: 'Detalle de la foto' });
  await expect(detail.getByLabel('Texto alternativo (ES)')).toBeVisible();
  await expect(page.locator('.cms-library-card').filter({ hasText: 'Sin descripción' }).first()).toBeVisible();
  await detail.getByLabel('Texto alternativo (ES)').fill(description);
  await detail.getByLabel('Texto alternativo (EN)').fill(description);
  await Promise.all([page.waitForResponse(r => r.url().endsWith(`/biblioteca/api/${id}/`) && r.request().method() === 'POST'), detail.getByRole('button', { name: 'Guardar foto y recortes' }).click()]);
  await page.getByRole('searchbox').fill(description);
  await expect(page.locator('.cms-library-card').filter({ hasText: description })).toBeVisible();
  await page.getByRole('button', { name: /^Sin usar \d/ }).click();
  await expect(page.locator('.cms-library-card').filter({ hasText: description })).toBeVisible();
  await detail.getByRole('button', { name: 'Archivar foto' }).click();
  await Promise.all([page.waitForResponse(r => r.url().endsWith(`/biblioteca/api/${id}/`) && r.request().method() === 'POST'), detail.getByRole('button', { name: 'Sí, continuar' }).click()]);
  await page.getByRole('button', { name: /^Archivadas \d/ }).click();
  await expect(page.locator('.cms-library-card').filter({ hasText: description })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
