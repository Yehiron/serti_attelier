import AxeBuilder from '@axe-core/playwright';
import { expect, test, localOnly, type Page } from './fixtures';
import { addToCartAndCheckout, adminSession, advanceOrder, buyer, createPiece, fillCheckout, localRedirect, manage, simulateWompi, stubWompi, waitForEmails } from './support';

async function accessible(page: Page, selector?: string) {
  let builder = new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']);
  if (selector) builder = builder.include(selector);
  const result = await builder.analyze();
  expect(result.violations.filter(v => v.impact === 'serious' || v.impact === 'critical')
    .map(v => `${v.id}: ${v.help} → ${v.nodes.map(n => `${n.target.join(' ')} (${n.any[0]?.message ?? ''})`).join(' | ')}`)).toEqual([]);
}

test('pending PSE updates without reloading, tracking timeline and accessible panel notice', async ({ page, browser, baseURL }) => {
  test.setTimeout(120_000);
  const session = adminSession();
  const adminContext = await browser.newContext();
  await localOnly(adminContext, baseURL!);
  await adminContext.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  const admin = await adminContext.newPage();
  // A new account has no historical receipts. Wait for initialization before creating the payment.
  const initialized = admin.waitForResponse(r => r.url().includes('/notifications/unread/') && r.status() === 200);
  await admin.goto(new URL(session.admin_url, baseURL).toString());
  await initialized;
  const prepareMetric = admin.locator('[data-metric-value]').nth(1);
  let prepareBefore = Number(await prepareMetric.textContent());
  let adminNavigations = 0;
  admin.on('request', r => { if (r.isNavigationRequest() && r.frame() === admin.mainFrame()) adminNavigations++; });
  await expect(admin.locator('[data-notice-count]')).toHaveText('0');

  await page.bringToFront();
  const piece = createPiece();
  const who = buyer('pse');
  const wompi = await stubWompi(page);
  await addToCartAndCheckout(page, piece.slug_es, piece.name);
  await fillCheckout(page, who, 'online');
  await page.getByRole('button', { name: /Confirmar pedido/ }).click();
  await expect(page.getByRole('button', { name: 'Wompi stub' })).toBeVisible();
  const fields = wompi();
  const reference = fields.get('reference')!;
  const orderUrl = localRedirect(fields.get('redirect-url')!, baseURL!);
  simulateWompi(reference, 'PENDING');
  await page.goto(orderUrl);
  await expect(page.getByText(/Estamos confirmando tu pago/)).toBeVisible();
  await accessible(page);
  // Load the newly created pending row before approving: this also works with
  // an otherwise empty dev database. There must be no reload after approval.
  await admin.bringToFront();
  const pendingInitialized = admin.waitForResponse(r => r.url().includes('/notifications/unread/') && r.status() === 200);
  await admin.goto(new URL(session.admin_url, baseURL).toString());
  await pendingInitialized;
  prepareBefore = Number(await prepareMetric.textContent());
  adminNavigations = 0;
  await page.bringToFront();
  // Count full document navigations: router.refresh polling may fetch RSC, never reloads the document.
  let navigations = 0;
  page.on('request', r => { if (r.isNavigationRequest() && r.frame() === page.mainFrame()) navigations++; });
  simulateWompi(reference, 'APPROVED');
  await expect(page.getByRole('heading', { level: 1, name: 'Esta pieza es solo tuya.' })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('Pago aprobado', { exact: true })).toBeVisible();
  expect(navigations).toBe(0);

  // Production polling is 45 s; each assertion waits no more than 50 s.
  await admin.bringToFront();
  await expect(admin.locator('[data-notice-count]')).toHaveText('1', { timeout: 50_000 });
  await expect(admin.locator('[data-notice-toast]')).toContainText('Nuevo pedido pagado');
  await expect(prepareMetric).toHaveText(String(prepareBefore + 1), { timeout: 5000 });
  await expect(admin.locator('[data-new-orders]')).toContainText('Hay pedidos nuevos');
  expect(adminNavigations).toBe(0);
  if (test.info().project.name === 'mobile') {
    expect(await admin.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const row = admin.locator('#result_list tbody tr').first();
    expect((await row.boundingBox())!.height).toBeLessThan(220);
    await expect(row.getByRole('link', { name: /Ver pedido/ })).toBeVisible();
  }
  await admin.getByRole('button', { name: 'Avisos de pedidos', exact: true }).click();
  const orderLink = admin.locator('[data-notice-list] a');
  await expect(orderLink).toHaveCount(1);
  await orderLink.click();
  const card = admin.locator('[data-card-content]');
  await expect(card).toBeVisible();
  await accessible(admin, '[data-card-content]');

  await page.bringToFront();
  manage('e2e_tracking_reads', '--reference', reference, '--reset');
  const validResponse = await page.goto(orderUrl);
  expect(validResponse?.status()).toBe(200);
  expect(Object.keys(validResponse!.headers()).some(key => key.includes('serti-order-probe'))).toBe(false);
  expect(Number(manage('e2e_tracking_reads', '--reference', reference).trim().split('\n').pop())).toBe(1);
  advanceOrder(reference, 'preparing');
  await page.reload();
  await expect(page.getByText('En preparación', { exact: true }).first()).toBeVisible();
  advanceOrder(reference, 'shipped');
  await page.reload();
  await expect(page.getByText('Enviado', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Transportadora E2E', { exact: false })).toBeVisible();
  await expect(page.getByText('E2E-123', { exact: false })).toBeVisible();
  const subjects = await waitForEmails(who.email, 2);
  expect(subjects).toHaveLength(2);
  expect(subjects).toContainEqual(expect.stringMatching(/ · Pago aprobado$/));
  await adminContext.close();
});

test('nonexistent tracking link returns an actual HTTP 404', async ({ page }) => {
  const response = await page.goto('/es/pedido/e2e-inexistente');
  expect(response?.status()).toBe(404);
  expect(response?.headers()['cache-control']).toContain('no-store');
  expect(response?.headers()['referrer-policy']).toBe('no-referrer');
  expect(response?.headers()['x-robots-tag']).toContain('noindex');
  await expect(page.locator('body')).not.toContainText('Cliente de Prueba');
  await expect(page.locator('header.site-header')).toBeVisible();
  await expect(page.locator('footer.site-footer')).toBeVisible();
  await expect(page.getByRole('img', { name: 'SERTI Jewelry Atelier' })).toBeVisible();
  await accessible(page);
});
