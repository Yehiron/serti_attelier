import { expect, test } from '@playwright/test';
import { createPiece } from './support';

test('selection drawer supports closing, removal and checkout', async ({ page }) => {
  const piece = createPiece();
  await page.goto(`/es/piezas/${piece.slug_es}`);
  const add = page.getByRole('button', { name: 'Agregar al carrito' }).first();
  await add.click();
  const drawer = page.locator('dialog.cart-drawer');
  await expect(drawer).toBeVisible();
  await expect(drawer.locator('.cart-line-added')).toContainText(piece.name);
  await expect(drawer.getByText('Agregada a tu selección')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(drawer).toBeHidden();
  await expect(add).toBeFocused();
  const cart = page.getByRole('button', { name: /Tu selección \(1\)/ });
  await cart.click();
  await drawer.getByRole('button', { name: 'Cerrar' }).click();
  await expect(drawer).toBeHidden();
  await expect(cart).toBeFocused();
  await cart.click();
  await page.mouse.click(2, 2);
  await expect(drawer).toBeHidden();
  await expect(cart).toBeFocused();
  await cart.click();
  await drawer.getByRole('button', { name: `Quitar: ${piece.name}` }).click();
  await expect(drawer.getByText('Tu próxima pieza te espera.')).toBeVisible();
  await drawer.getByRole('button', { name: 'Cerrar' }).click();
  await expect(drawer).toBeHidden();
  await add.click();
  await drawer.getByRole('link', { name: /Finalizar compra/ }).click();
  await expect(page).toHaveURL(/\/es\/checkout$/);
});

test('cart page uses two columns on desktop', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop');
  const piece = createPiece();
  await page.goto(`/es/piezas/${piece.slug_es}`);
  await page.getByRole('button', { name: 'Agregar al carrito' }).first().click();
  await expect(page.locator('dialog.cart-drawer')).toBeVisible();
  await page.goto('/es/carrito');
  const list = page.locator('.commerce-page .cart-list');
  const summary = page.locator('.commerce-page .cart-summary');
  await expect(summary).toBeVisible();
  const listBox = await list.boundingBox(); const summaryBox = await summary.boundingBox();
  expect(listBox && summaryBox && summaryBox.x).toBeGreaterThan(listBox!.x + listBox!.width);
  await expect(summary).toHaveCSS('position', 'sticky');
});
