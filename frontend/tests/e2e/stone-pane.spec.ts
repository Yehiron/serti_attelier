import { expect, test } from './fixtures';
import { adminSession, manage } from './support';

test('piedras: aviso y color de la gema', async ({ page, context, baseURL, isMobile }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const pk = manage('shell', '-c', `from apps.catalog.models import Stone; s=Stone.objects.create(name_es='E2E Piedra ${stamp}', slug_es='e2e-piedra-${stamp}'); print(s.pk)`).trim().split('\n').pop();
  const session = adminSession();
  await context.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const adminRoot = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  try {
    await page.goto(`${adminRoot}catalog/stone/?stone=${pk}`);
    await page.locator('#id_description_es').fill('Este es texto de prueba');
    await expect(page.locator('[data-test-warning]')).toBeVisible();
    await page.locator('[data-swatch="0"]').click();
    await page.screenshot({ path: test.info().outputPath(`piedras-${isMobile ? 'movil' : 'escritorio'}.png`), fullPage: true });
    await page.locator('.cat-actions button[type="submit"]').click();
    await expect(page).toHaveURL(new RegExp(`stone=${pk}`));
    const color = manage('shell', '-c', `from apps.catalog.models import Stone; print(Stone.objects.get(pk=${pk}).color)`).trim().split('\n').pop();
    expect(color).toBe('#1f7a55');
    expect(errors).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  } finally {
    manage('shell', '-c', `from apps.catalog.models import Stone; Stone.objects.filter(pk=${pk}).delete()`);
  }
});
