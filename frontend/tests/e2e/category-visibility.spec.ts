import { test, expect } from './fixtures';
import { createPiece, manage } from './support';

test('categoría activa recién creada aparece vacía y muestra su pieza publicada', async ({ page }) => {
  // Warm the page before creating the category: this also catches a shared stale menu.
  await page.goto('/es');
  await expect(page.locator('.utilities')).toBeVisible();
  const stamp = Date.now();
  const slug = `gorras-e2e-${stamp}`;
  const name = `Gorras prueba ${stamp}`;
  manage('shell', '-c', `from apps.catalog.models import Category; from apps.catalog.services import save_taxonomy; save_taxonomy(Category(name_es=${JSON.stringify(name)}, slug_es=${JSON.stringify(slug)}))`);
  try {
    // Read the empty category without letting link prefetch warm its piece list.
    const freshHome = await page.request.get('/es');
    expect(await freshHome.text()).toContain(name);
    const piece = createPiece();
    manage('shell', '-c', `from apps.catalog.models import Category, Piece; Piece.objects.filter(sku=${JSON.stringify(piece.sku)}).update(category=Category.objects.get(slug_es=${JSON.stringify(slug)}))`);
    await page.reload();
    // The header streams in after the shell; decide desktop/mobile only once it is there.
    await expect(page.locator('.site-header .utilities')).toBeVisible();
    const mobile = page.locator('.menu-trigger');
    let nav = page.locator('.desktop-nav');
    if (await mobile.isVisible()) {
      await expect(async () => {
        await mobile.click();
        await expect(page.locator('.menu-dialog')).toBeVisible({ timeout: 1000 });
      }).toPass({ timeout: 15_000 });
      nav = page.locator('.menu-dialog');
    }
    await nav.locator('summary', { hasText: 'Joyería' }).click();
    await expect(nav.getByRole('link', { name, exact: true })).toBeVisible();
    await nav.getByRole('link', { name, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/es/joyeria/${slug}$`));
    await expect(page.locator(`a[href="/es/piezas/${piece.slug_es}"]`).first()).toBeVisible();
    await page.goto('/es');
    await expect(page.locator(`.category-grid a[href="/es/joyeria/${slug}"]`)).toBeVisible();
  } finally {
    manage('shell', '-c', `from apps.catalog.models import Category, Piece; Piece.objects.filter(category__slug_es=${JSON.stringify(slug)}).update(category=None); Category.objects.filter(slug_es=${JSON.stringify(slug)}).delete()`);
  }
});
