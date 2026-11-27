import { expect, test } from './fixtures';
import { adminSession } from './support';

test('datos del sitio: navegación, vista previa y restauración', async ({ page, context, baseURL }) => {
  const session = adminSession();
  const root = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  await context.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  const errors: Error[] = [];
  page.on('pageerror', error => errors.push(error));
  // The menu entry points at the list, which now opens the single form directly.
  await page.goto(`${root}core/sitesettings/`);
  await expect(page).toHaveURL(/core\/sitesettings\/1\/change/);
  const message = page.locator('[name="whatsapp_sold_es"]');
  const original = await message.inputValue();
  try {
    for (const name of ['Contacto y redes', 'Mensajes de WhatsApp', 'Pagos y reservas', 'Google (SEO)', 'Horario y zona']) {
      await page.locator('.set-nav').getByRole('link', { name, exact: true }).click();
      await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
    }
    await message.fill('Prueba de vista previa {name}');
    await expect(message.locator('..').locator('[data-preview]')).toContainText('Prueba de vista previa');
    await message.fill('Prueba {precio}');
    await expect(message.locator('..').locator('.set-live-error')).toContainText('Solo se permiten');
    await message.fill(original);
    // Desktop shows it in the header; phones in the sticky bottom bar.
    await page.getByRole('button', { name: 'Guardar cambios' }).filter({ visible: true }).first().click();
    await expect(page).toHaveURL(/core\/sitesettings\/1\/change/);
  } finally {
    page.once('dialog', dialog => dialog.accept());
    await page.goto(`${root}core/sitesettings/1/change/`);
    if (await message.inputValue() !== original) {
      await message.fill(original);
      // Desktop shows it in the header; phones in the sticky bottom bar.
    await page.getByRole('button', { name: 'Guardar cambios' }).filter({ visible: true }).first().click();
      await expect(page).toHaveURL(/core\/sitesettings\/1\/change/);
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});
