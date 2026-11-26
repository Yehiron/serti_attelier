import { test, expect } from './fixtures';

for (const viewport of [{ width: 1280, height: 900 }, { width: 375, height: 800 }]) {
  test(`envío de contacto ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.route('**/api/v1/contact', route => route.fulfill({ status: 201, json: { received: true } }));
    await page.goto('/es/contacto?pieza=ABC-1');
    await expect(page.getByText('sobre la pieza ABC-1')).toBeVisible();
    await page.getByLabel('Nombre completo').fill('Ana Pérez');
    await page.getByRole('textbox', { name: 'Correo', exact: true }).fill('ana@example.com');
    await page.getByLabel('Mensaje', { exact: true }).fill('Me gustaría saber más sobre esta pieza.');
    await page.getByLabel(/Acepto la política/).check();
    const link = page.getByRole('link', { name: /Continuar por WhatsApp/ });
    await expect(link).toHaveAttribute('href', /Quiero%20hablar%20sobre.*sobre%20la%20pieza%20ABC-1/);
    await page.getByRole('button', { name: 'Enviar mensaje' }).click();
    await expect(page.locator('.wax-seal')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Tu carta llegó al atelier' })).toBeFocused();
  });
}
test('validación enfoca el resumen', async ({ page }) => {
  await page.goto('/es/contacto');
  let requests = 0;
  page.on('request', request => { if (request.url().includes('/api/v1/contact') && request.method() === 'POST') requests++; });
  await page.getByRole('button', { name: 'Enviar mensaje' }).click();
  await expect(page.locator('.contact-summary')).toBeFocused();
  await expect(page.getByRole('link', { name: 'Tu nombre: escríbelo para saber cómo llamarte.' })).toBeVisible();
  await expect(page.getByLabel('Nombre completo')).toHaveAttribute('aria-invalid', 'true');
  expect(requests).toBe(0);
});


test('movimiento reducido muestra el agradecimiento inmediatamente', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/api/v1/contact', route => route.fulfill({ status: 201, json: { received: true } }));
  await page.goto('/es/contacto?pieza=ABC-1');
  await page.getByLabel('Nombre completo').fill('Ana Pérez');
  await page.getByRole('textbox', { name: 'Correo', exact: true }).fill('ana@example.com');
  await page.getByLabel('Mensaje', { exact: true }).fill('Quisiera conocer más sobre sus piezas.');
  await page.getByLabel(/Acepto la política/).check();
  await page.getByRole('button', { name: 'Enviar mensaje' }).click();
  await expect(page.locator('.wax-seal')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Tu carta llegó al atelier' })).toBeFocused({ timeout: 1000 });
});

for (const status of [500, 429]) {
  test(`un error ${status} no sella la carta`, async ({ page }) => {
    await page.route('**/api/v1/contact', route => route.fulfill({ status, json: {} }));
    await page.goto('/es/contacto?pieza=ABC-1');
    await page.getByLabel('Nombre completo').fill('Ana Pérez');
    await page.getByRole('textbox', { name: 'Correo', exact: true }).fill('ana@example.com');
    await page.getByLabel('Mensaje', { exact: true }).fill('Quisiera conocer más sobre sus piezas.');
    await page.getByLabel(/Acepto la política/).check();
    await page.getByRole('button', { name: 'Enviar mensaje' }).click();
    await expect(page.locator('.contact-summary')).toBeFocused();
    await expect(page.locator('.contact-summary')).toContainText(status === 429 ? 'Recibimos varios mensajes seguidos' : 'No pudimos enviar tu mensaje');
    await expect(page.locator('.wax-seal')).toHaveCount(0);
  });
}
