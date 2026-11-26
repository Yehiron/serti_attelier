import { expect, test } from '@playwright/test';

for (const [path, heading, home] of [
  ['/es/piezas/no-existe', 'Esta joya encontró otro destino', 'Volver al inicio'],
  ['/en/pieces/nope', 'This piece has found another home', 'Return home'],
  ['/es/no-existe', 'Esta página no está en el atelier', 'Volver al inicio'],
] as const) {
  test(`${path} devuelve 404 con diseño`, async ({ page }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBe(404);
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
    await expect(page.getByRole('link', { name: home })).toBeVisible();
  });
}

test('una pieza ausente en deseos no enlaza a su ficha', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('serti_wishlist', JSON.stringify([{ sku: 'INEXISTENTE-E2E', slugs: { es: 'inexistente-e2e', en: 'missing-e2e' }, name: 'Joya ausente', image: null, price: { amount_cents: 10000, currency: 'COP' }, addedAt: 1 }])));
  await page.goto('/es/deseos');
  await expect(page.getByText('Ya no está disponible')).toBeVisible();
  await expect(page.locator('a[href="/es/piezas/inexistente-e2e"]')).toHaveCount(0);
});
