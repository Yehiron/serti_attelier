import { expect, test } from './fixtures';
import { adminSession, manage } from './support';

test('materiales: crear y editar tono', async ({ page, context, baseURL, isMobile }) => {
  const stamp = Date.now();
  const session = adminSession();
  await context.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const root = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  try {
    await page.goto(`${root}catalog/material/?material=new`);
    await page.locator('[name=name_es]').fill(`E2E Material ${stamp}`);
    await page.locator('[name=name_en]').fill(`E2E Material ${stamp}`);
    await page.locator('summary').filter({ hasText: 'Dirección web' }).click();
    await page.locator('[name=slug_es]').fill(`e2e-material-${stamp}`);
    await page.locator('[name=slug_en]').fill(`e2e-material-${stamp}`);
    await page.locator('.mat-form button[type=submit]').click();
    const card = page.locator('.mat-card').filter({ hasText: `E2E Material ${stamp}` });
    await card.getByText('Editar').click();
    await page.locator('[data-color="#e3a98e"]').click();
    await page.locator('.mat-form button[type=submit]').click();
    await page.reload();
    await card.getByText('Editar').click();
    await expect(page.locator('[name=color]')).toHaveValue('#e3a98e');
    expect(errors).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath(`materiales-${isMobile ? 'movil' : 'escritorio'}.png`), fullPage: true });
  } finally {
    manage('shell', '-c', `from apps.catalog.models import Material; Material.objects.filter(slug_es='e2e-material-${stamp}', pieces__isnull=True).delete()`);
  }
});
