import { expect, test } from './fixtures';
import { adminSession, manage } from './support';

test('categorías: lista y detalle con vista previa del banner en vivo', async ({ page, context, baseURL, isMobile }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const pk = manage('shell', '-c', `from apps.catalog.models import Category; c=Category.objects.create(name_es='E2E Categoría ${stamp}', slug_es='e2e-categoria-${stamp}', name_en='E2E Category', slug_en='e2e-category-${stamp}'); print(c.pk)`).trim().split('\n').pop();
  const session = adminSession();
  await context.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const adminRoot = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  try {
    await page.goto(`${adminRoot}catalog/category/?category=${pk}`);
    const detail = page.locator('.cat-detail');
    await expect(detail).toBeVisible();
    if (!isMobile) await expect(page.locator('.cat-tree')).toBeVisible();
    const text = `Descripción de prueba ${stamp}`;
    await page.locator('#id_description_es').fill(text);
    // The banner preview follows what is typed, before saving.
    await expect(page.locator('[data-preview-description]')).toHaveText(text);
    await page.screenshot({ path: test.info().outputPath(`categorias-${isMobile ? 'movil' : 'escritorio'}.png`), fullPage: true });
    await page.locator('.cat-actions button[type="submit"], .cat-actions [name="_save"]').last().click();
    await expect(page).toHaveURL(new RegExp(`category=${pk}`));
    const saved = manage('shell', '-c', `from apps.catalog.models import Category; print(Category.objects.get(pk=${pk}).description_es)`).trim().split('\n').pop();
    expect(saved).toBe(text);
    expect(errors).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  } finally {
    manage('shell', '-c', `from apps.catalog.models import Category; Category.objects.filter(pk=${pk}).delete()`);
  }
});
