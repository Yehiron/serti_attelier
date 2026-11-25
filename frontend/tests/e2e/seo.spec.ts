import { test, expect } from '@playwright/test';

test.use({ userAgent: 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)' });
test('rutas ausentes responden 404 antes del streaming', async ({ request }) => {
  for (const path of ['/es/no-existe', '/es/piezas/no-existe', '/es/joyeria/no-existe']) expect((await request.get(path)).status(), path).toBe(404);
});
test('búsqueda y carrito no son indexables', async ({ page }) => {
  for (const path of ['/es/buscar', '/es/carrito']) { await page.goto(path); await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/); }
});
test('portada y fichas publican datos estructurados', async ({ page }) => {
  await page.goto('/es');
  const schemas = async () => page.locator('script[type="application/ld+json"]').allTextContents().then(values => values.flatMap(value => { const parsed = JSON.parse(value); return Array.isArray(parsed) ? parsed : [parsed]; }));
  const home = await schemas();
  const store = home.find(x => Array.isArray(x['@type']) ? x['@type'].includes('JewelryStore') : x['@type'] === 'JewelryStore');
  expect(store).toBeTruthy(); expect(store.address.streetAddress).toBeUndefined();
  await page.goto('/es/joyeria');
  const listing = await schemas(); expect(listing.some(x => x['@type'] === 'BreadcrumbList')).toBeTruthy();
  const link = page.locator('a[href^="/es/piezas/"]').first(); await expect(link).toBeVisible();
  // Load the piece as a crawler would (full document), not via client-side navigation.
  await page.goto((await link.getAttribute('href'))!);
  const detail = await schemas(); expect(detail.some(x => x['@type'] === 'BreadcrumbList')).toBeTruthy();
  expect(detail.find(x => x['@type'] === 'Product')?.offers.availability).toMatch(/InStock|PreOrder|SoldOut|OutOfStock/);
});
test('metadatos son únicos entre páginas públicas', async ({ page }) => {
  const paths = ['/es', '/es/joyeria'];
  await page.goto('/es/joyeria');
  for (const prefix of ['/es/joyeria/', '/es/piedras/', '/es/colecciones/', '/es/piezas/']) {
    const link = page.locator(`a[href^="${prefix}"]`).first();
    await expect(link, `Falta un enlace para ${prefix}`).toHaveCount(1);
    paths.push((await link.getAttribute('href'))!);
  }
  const titles = new Set<string>(); const descriptions = new Set<string>();
  for (const path of paths) {
    await page.goto(path);
    await expect(page.locator('head > title')).toHaveCount(1);
    const title = await page.title(); const description = await page.locator('meta[name="description"]').getAttribute('content');
    expect(title).toBeTruthy(); expect(description).toBeTruthy();
    titles.add(title); descriptions.add(description!);
  }
  expect(titles.size).toBe(paths.length); expect(descriptions.size).toBe(paths.length);
});
test('Personaliza publica FAQPage y la tienda no expone coordenadas', async ({ page }) => {
  await page.goto('/es/personaliza');
  const schemas = await page.locator('script[type="application/ld+json"]').allTextContents();
  const objects = schemas.flatMap(value => { const parsed = JSON.parse(value); return Array.isArray(parsed) ? parsed : [parsed]; });
  expect(objects.some(x => x['@type'] === 'FAQPage')).toBeTruthy();
  const store = objects.find(x => Array.isArray(x['@type']) ? x['@type'].includes('JewelryStore') : x['@type'] === 'JewelryStore');
  expect(store?.geo).toBeUndefined(); expect(store?.address?.streetAddress).toBeUndefined();
});
