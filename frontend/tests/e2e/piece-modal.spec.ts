import { expect, test } from './fixtures';
import { adminSession, createPiece, manage } from './support';

test('editar una pieza en la ventana flotante y guardar sin salir de la lista', async ({ page, context, baseURL, isMobile }) => {
  test.setTimeout(120_000);
  const piece = createPiece();
  const session = adminSession();
  await context.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const adminRoot = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');

  await page.goto(`${adminRoot}catalog/piece/?q=${piece.sku}`);
  await page.locator('a[aria-label="Editar"]').first().click();
  const dialog = page.locator('dialog.pe-dialog');
  await expect(dialog).toBeVisible();
  const frame = page.frameLocator('dialog.pe-dialog iframe');
  const editor = frame.locator('[data-pe-editor]');
  await expect(editor).toBeVisible();
  // Inside the window there is no second dashboard header.
  await expect(frame.locator('#header, header#header, .unfold-header')).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath(`editor-${isMobile ? 'movil' : 'escritorio'}.png`) });

  const short = frame.locator('textarea[name="short_description_es"], textarea[name="short_description"]').first();
  const text = `Descripción editada en la ventana ${Date.now()}`;
  await short.fill(text);
  await expect(frame.locator('[data-pe-dirty]')).toHaveText('Cambios sin guardar');
  await frame.locator('button[name="_save"]').click();
  await expect(dialog).toBeHidden({ timeout: 20_000 });
  await expect(page).toHaveURL(/catalog\/piece\//);

  const saved = manage('shell', '-c', `from apps.catalog.models import Piece; print(Piece.objects.get(sku='${piece.sku}').short_description_es)`).trim().split('\n').pop();
  expect(saved).toBe(text);
  expect(errors).toEqual([]);
});
