import { expect, test } from '@playwright/test';
import { createPiece } from './support';

test('home in Spanish and the language switch keeps the equivalent page', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/es$/);
  await expect(page.locator('h1')).toBeVisible();
  const piece = createPiece();
  await page.goto(`/es/piezas/${piece.slug_es}`);
  await page.getByRole('link', { name: 'Idioma' }).first().click();
  await expect(page).toHaveURL(new RegExp(`/en/pieces/${piece.slug_en}$`));
});

test('wrong-language URLs redirect to the canonical one', async ({ page }) => {
  await page.goto('/en/piezas/anything');
  await expect(page).toHaveURL(/\/en\/pieces\/anything$/);
});

test('catalog filters by stone and keeps them in the URL', async ({ page }) => {
  await page.goto('/es/joyeria');
  // The listing streams in after the shell; decide desktop/mobile only once it is there.
  await expect(page.locator('main.listing-page')).toBeVisible();
  // Filters live in a sidebar on desktop and in a bottom sheet on mobile.
  const trigger = page.locator('.mobile-filter-trigger');
  if (await trigger.isVisible()) {
    // A tap before hydration is lost; retry until the sheet is open.
    await expect(async () => {
      await trigger.click();
      await expect(page.locator('dialog.filter-dialog[open]')).toBeVisible({ timeout: 1000 });
    }).toPass({ timeout: 15_000 });
  }
  await page.locator('input[name="stone"][value="esmeralda"]:visible').first().check();
  await page.locator('button[type="submit"]:visible', { hasText: /Aplicar/ }).first().click();
  await expect(page).toHaveURL(/stone=esmeralda/);
  await expect(page.locator('.piece-card').first()).toBeVisible();
});

test('the wishlist survives a reload and shows the live state', async ({ page }) => {
  const piece = createPiece();
  await page.goto(`/es/piezas/${piece.slug_es}`);
  await page.getByRole('button', { name: /Guardar en deseos/ }).first().click();
  await page.goto('/es/deseos');
  await page.reload();
  await expect(page.getByText(piece.name)).toBeVisible();
  await expect(page.getByText('Disponible').first()).toBeVisible();
});
