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
  await drawer.getByRole('button', { name: /Finalizar compra/ }).click();
  await expect(drawer.getByRole('heading', { name: 'Tus datos' })).toBeVisible();
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

test('compra Wompi completa dentro del panel', async ({ page }) => {
  const { buyer, fillCheckout, simulateWompi, stubWompi } = await import('./support');
  const piece = createPiece(); const wompi = await stubWompi(page);
  await page.route(/\/payment-sync(\?|$)/, route => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
  await page.goto(`/es/piezas/${piece.slug_es}`); const original = page.url();
  await page.getByRole('button', { name: 'Agregar al carrito' }).first().click();
  const drawer = page.locator('dialog.cart-drawer');
  await drawer.getByRole('button', { name: /Finalizar compra/ }).click();
  await fillCheckout(page, buyer('panel'), 'online');
  await drawer.getByRole('button', { name: /Confirmar pedido/ }).click();
  await expect(page.getByRole('button', { name: 'Wompi stub' })).toBeVisible();
  await expect.poll(() => wompi().get('reference')).toBeTruthy();
  simulateWompi(wompi().get('reference')!, 'APPROVED');
  // While Wompi's window is open the page must scroll (its window is taller than a phone).
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.body).overflowY)).not.toBe('hidden');
  await page.getByRole('button', { name: 'Wompi stub' }).click();
  await expect(drawer.getByText('Te enviamos la confirmación a tu correo', { exact: false })).toBeVisible();
  expect(page.url()).toBe(original);
});

test('cerrar el widget deja disponible el pago', async ({ page }) => {
  const { buyer, fillCheckout, stubWompi } = await import('./support');
  const piece = createPiece(); await stubWompi(page);
  await page.goto(`/es/piezas/${piece.slug_es}`);
  await page.getByRole('button', { name: 'Agregar al carrito' }).first().click();
  const drawer = page.locator('dialog.cart-drawer');
  await drawer.getByRole('button', { name: /Finalizar compra/ }).click();
  await fillCheckout(page, buyer('cerrado'), 'online');
  await drawer.getByRole('button', { name: /Confirmar pedido/ }).click();
  await expect(page.getByRole('button', { name: 'Wompi stub' })).toBeVisible();
  await page.getByRole('button', { name: 'Cerrar Wompi' }).click();
  // The panel returns to the top layer (modal) and the page is locked again.
  await expect.poll(() => drawer.evaluate(node => node.matches(':modal'))).toBe(true);
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.body).overflowY)).toBe('hidden');
  await expect(drawer.getByRole('button', { name: 'Pagar con Wompi' })).toBeEnabled();
  await expect(drawer.getByRole('link', { name: /Ver mi pedido/ })).toBeVisible();
});

test('pago manual muestra instrucciones dentro del panel', async ({ page }) => {
  const { buyer, fillCheckout } = await import('./support'); const piece = createPiece();
  await page.goto(`/es/piezas/${piece.slug_es}`); const original = page.url();
  await page.getByRole('button', { name: 'Agregar al carrito' }).first().click();
  const drawer = page.locator('dialog.cart-drawer');
  await drawer.getByRole('button', { name: /Finalizar compra/ }).click();
  await fillCheckout(page, buyer('manual-panel'), 'manual');
  await drawer.getByRole('button', { name: /Confirmar pedido/ }).click();
  await expect(drawer.locator('.drawer-flow > p').first()).toBeVisible();
  await expect(drawer.locator('.whitespace-pre-line')).not.toBeEmpty();
  await expect(drawer.getByRole('link', { name: /Ver mi pedido/ })).toBeVisible();
  expect(page.url()).toBe(original);
});


test('los pasos validan y conservan los datos', async ({ page }) => {
  const piece = createPiece();
  await page.goto(`/es/piezas/${piece.slug_es}`);
  await page.getByRole('button', { name: 'Agregar al carrito' }).first().click();
  const drawer = page.locator('dialog.cart-drawer');
  await drawer.getByRole('button', { name: /Finalizar compra/ }).click();
  await drawer.getByRole('button', { name: 'Siguiente' }).click();
  await expect(drawer.locator('.error-summary')).toBeFocused();
  await drawer.getByLabel('Nombre completo').fill('Cliente de Prueba');
  await drawer.getByLabel('Correo electrónico').fill('cliente@example.com');
  await drawer.getByLabel('Celular').fill('300 123 4567');
  await drawer.getByRole('button', { name: 'Siguiente' }).click();
  await drawer.getByLabel('Departamento').selectOption('05');
  await drawer.getByLabel('Municipio').locator('option[value="05001"]').waitFor({ state: 'attached' });
  await drawer.getByLabel('Municipio').selectOption('05001');
  await drawer.getByLabel('Dirección').fill('Calle 10');
  await drawer.getByRole('button', { name: 'Siguiente' }).click();
  await drawer.getByRole('button', { name: /Atrás/ }).click();
  await expect(drawer.getByLabel('Dirección')).toHaveValue('Calle 10');
  await drawer.getByRole('button', { name: /Atrás/ }).click();
  await expect(drawer.getByLabel('Nombre completo')).toHaveValue('Cliente de Prueba');
});
