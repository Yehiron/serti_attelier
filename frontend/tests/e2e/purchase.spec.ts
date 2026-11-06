import { expect, test, localOnly } from './fixtures';
import { addToCartAndCheckout, buyer, createPiece, fillCheckout, localRedirect, simulateWompi, stubWompi, waitForEmails } from './support';

test('manual payment reserves the unique piece and emails the instructions', async ({ page, request }) => {
  const piece = createPiece();
  const who = buyer('manual');
  await addToCartAndCheckout(page, piece.slug_es, piece.name);
  await fillCheckout(page, who, 'manual');
  // A double click must still create exactly one order (idempotency key).
  await page.getByRole('button', { name: /Confirmar pedido/ }).dblclick();
  await expect(page).toHaveURL(/\/es\/pedido\//);
  await expect(page.getByRole('heading', { level: 1, name: 'Tu pieza está reservada' })).toBeVisible();
  const status = await (await request.get(`/api/v1/catalog/pieces/status?skus=${piece.sku}`)).json();
  expect(status[piece.sku]).toBe('reserved');
  const subjects = await waitForEmails(who.email, 1);
  expect(subjects).toEqual([expect.stringMatching(/^SERTI · Pedido SRT-.* · Instrucciones de pago$/)]);
});

test('online payment: declined, retried and approved through Wompi', async ({ page, request, baseURL }) => {
  const piece = createPiece();
  const who = buyer('online');
  const wompi = await stubWompi(page);
  await addToCartAndCheckout(page, piece.slug_es, piece.name);
  await fillCheckout(page, who, 'online');
  await page.getByRole('button', { name: /Confirmar pedido/ }).click();
  await expect(page.getByRole('heading', { name: 'Wompi stub' })).toBeVisible();

  const first = wompi();
  expect(first.get('reference')).toMatch(/^SRT-\d{6}-01$/);
  expect(first.get('signature:integrity')).toMatch(/^[0-9a-f]{64}$/);
  expect(first.get('expiration-time')).toMatch(/Z$/);
  const orderUrl = localRedirect(first.get('redirect-url') ?? '', baseURL ?? '');

  simulateWompi(first.get('reference') ?? '', 'DECLINED');
  await page.goto(orderUrl);
  await expect(page.getByText(/Tu pago no se completó/)).toBeVisible();
  await page.getByRole('button', { name: 'Intentar de nuevo' }).click();
  await expect(page.getByRole('heading', { name: 'Wompi stub' })).toBeVisible();
  const second = wompi();
  expect(second.get('reference')).toMatch(/-02$/);

  simulateWompi(second.get('reference') ?? '', 'APPROVED');
  await page.goto(orderUrl);
  await expect(page.getByRole('heading', { level: 1, name: 'Esta pieza es solo tuya.' })).toBeVisible();
  const status = await (await request.get(`/api/v1/catalog/pieces/status?skus=${piece.sku}`)).json();
  expect(status[piece.sku]).toBe('sold');
  const subjects = await waitForEmails(who.email, 1);
  expect(subjects).toEqual([expect.stringMatching(/^SERTI · Pedido SRT-.* · Pago aprobado$/)]);

  // The sold piece stays visible and invites a custom piece (DC-09, DC-16).
  await page.goto(`/es/piezas/${piece.slug_es}`);
  await expect(page.getByText('Vendida — encontró su dueño').first()).toBeVisible();
  await expect(page.getByText(/Creemos una pieza única para ti/).first()).toBeVisible();
});

test('a piece reserved by someone else cannot be bought', async ({ page, browser, baseURL }) => {
  const piece = createPiece();
  await addToCartAndCheckout(page, piece.slug_es, piece.name);
  await fillCheckout(page, buyer('first'), 'manual');
  await page.getByRole('button', { name: /Confirmar pedido/ }).click();
  await expect(page).toHaveURL(/\/es\/pedido\//);

  const other = await browser.newContext();
  await localOnly(other, baseURL!);
  const second = await other.newPage();
  await second.goto(`/es/piezas/${piece.slug_es}`);
  await expect(second.getByText(/Alguien está completando la compra de esta pieza/).first()).toBeVisible();
  await expect(second.getByRole('button', { name: 'Agregar al carrito' })).toHaveCount(0);
  await other.close();
});
