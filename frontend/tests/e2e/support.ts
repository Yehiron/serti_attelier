import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { expect, type Page } from '@playwright/test';

const repo = resolve(__dirname, '../../..');
const compose = ['compose', '-f', 'infra/docker-compose.dev.yml', 'exec', '-T', 'backend', 'python', 'manage.py'];

export function manage(...args: string[]): string {
  return execFileSync('docker', [...compose, ...args], { cwd: repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
}

export type Piece = { sku: string; slug_es: string; slug_en: string; name: string };

/** A fresh, published, available unique piece for this test only. */
export function createPiece({ hover = false } = {}): Piece {
  const lines = manage('e2e_piece', ...(hover ? ['--hover'] : [])).trim().split('\n');
  return JSON.parse(lines[lines.length - 1]) as Piece;
}

/** Sign and deliver a Wompi webhook exactly like Wompi would (dev simulator). */
export function simulateWompi(reference: string, status: 'APPROVED' | 'DECLINED' | 'PENDING'): void {
  manage('simulate_wompi_event', '--reference', reference, '--status', status);
}

export type Buyer = { name: string; email: string; phone: string; address: string };

export const buyer = (tag: string): Buyer => ({
  name: 'Cliente de Prueba',
  email: `e2e.${tag}.${Date.now()}@example.com`,
  phone: '300 123 4567',
  address: 'Calle 10 # 43-12',
});

/** Fill the one-page checkout (contact, Antioquia/Medellín, consents). */
export async function fillCheckout(page: Page, who: Buyer, channel: 'online' | 'manual'): Promise<void> {
  await page.getByLabel('Nombre completo').fill(who.name);
  await page.getByLabel('Correo electrónico').fill(who.email);
  await page.getByLabel('Celular').fill(who.phone);
  const drawer = page.locator('dialog.cart-drawer');
  const stepped = await drawer.isVisible();
  if (stepped) await drawer.getByRole('button', { name: 'Siguiente' }).click();
  await page.getByLabel('Departamento').selectOption('05');
  const municipality = page.getByLabel('Municipio');
  await municipality.locator('option[value="05001"]').waitFor({ state: 'attached' });
  await municipality.selectOption('05001');
  await page.getByLabel('Dirección').fill(who.address);
  if (stepped) await drawer.getByRole('button', { name: 'Siguiente' }).click();
  await page.getByLabel(channel === 'manual' ? /Pagar por otro medio/ : /Pago en línea/).check();
  await page.getByLabel(/Acepto los términos/).check();
  await page.getByLabel(/Acepto la política de privacidad/).check();
}

/** Subjects of the emails Mailpit received for an address (waits for the Celery worker). */
export async function waitForEmails(address: string, count: number, timeoutMs = 20_000): Promise<string[]> {
  const script = [
    'import json,sys,urllib.parse,urllib.request',
    `q=urllib.parse.quote('to:"${address}"')`,
    "d=json.load(urllib.request.urlopen('http://mailpit:8025/api/v1/search?query='+q))",
    "print(json.dumps([m['Subject'] for m in d.get('messages',[])]))",
  ].join(';');
  const deadline = Date.now() + timeoutMs;
  let subjects: string[] = [];
  while (Date.now() < deadline) {
    const out = execFileSync('docker', ['compose', '-f', 'infra/docker-compose.dev.yml', 'exec', '-T', 'backend', 'python', '-c', script], { cwd: repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
    subjects = JSON.parse(out.trim().split('\n').pop() ?? '[]') as string[];
    if (subjects.length >= count) return subjects;
    await new Promise((resolveWait) => setTimeout(resolveWait, 1000));
  }
  return subjects;
}

/** Wompi checkout is external: tests stub it and read the signed fields it would receive. */
export async function stubWompi(page: Page): Promise<() => URLSearchParams> {
  let last = new URLSearchParams();
  await page.exposeBinding('captureWompi', (_source, config: Record<string, unknown>) => {
    const mapping: Record<string, string> = { publicKey: 'public-key', amountInCents: 'amount-in-cents', redirectUrl: 'redirect-url', expirationTime: 'expiration-time' };
    last = new URLSearchParams();
    for (const [key, value] of Object.entries(config)) if (typeof value === 'string' || typeof value === 'number') last.set(mapping[key] ?? key, String(value));
    last.set('signature:integrity', String((config.signature as { integrity: string }).integrity));
  });
  await page.route('https://checkout.wompi.co/**', async (route) => {
    if (new URL(route.request().url()).pathname === '/widget.js') {
      await route.fulfill({ contentType: 'application/javascript', body: `window.WidgetCheckout = class { constructor(config) { if (config.shippingAddress && !config.shippingAddress.phoneNumber) throw Error('shipping-address:phone-number'); window.captureWompi(config); window.wompiConfig = config; } open(cb) { /* Mirrors the real widget DOM: closing keeps .waybox-modal and adds waybox-modal-final-close, without calling cb. */ const modal = document.createElement('div'); modal.className = 'waybox-modal waybox-display-block'; modal.style.cssText = 'position:fixed;top:40px;left:0;right:0;z-index:2147483647;background:#fff;padding:16px;display:flex;gap:12px'; const close = () => modal.classList.add('waybox-modal-final-close'); const pay = document.createElement('button'); pay.textContent = 'Wompi stub'; pay.onclick = () => { cb({transaction: {id: window.wompiTransactionId || 'stub-transaction'}}); close(); }; const dismiss = document.createElement('button'); dismiss.textContent = 'Cerrar Wompi'; dismiss.onclick = close; modal.append(pay, dismiss); document.body.appendChild(modal); } };` });
      return;
    }
    last = new URL(route.request().url()).searchParams;
    // Same rule as the real sandbox: a shipping address needs its own phone number.
    const missingPhone = [...last.keys()].some((key) => key.startsWith('shipping-address:')) && !last.get('shipping-address:phone-number');
    const body = missingPhone ? '<!doctype html><title>Wompi (stub)</title><h1>Errores</h1><p>shipping-address:phone-number</p>' : '<!doctype html><title>Wompi (stub)</title><h1>Wompi stub</h1>';
    await route.fulfill({ status: 200, contentType: 'text/html', body });
  });
  return () => last;
}

/** Wompi redirects to PUBLIC_SITE_URL; map it onto the base URL under test. */
export function localRedirect(redirectUrl: string, baseURL: string): string {
  const target = new URL(redirectUrl);
  return new URL(target.pathname + target.search, baseURL).toString();
}

export function adminSession(role: 'Propietario' | 'Contenido' | 'Operaciones' = 'Propietario'): { name: string; value: string; admin_url: string } {
  return JSON.parse(manage('e2e_admin_session', '--role', role).trim().split('\n').pop() ?? '{}');
}

export function advanceOrder(reference: string, target: 'preparing' | 'shipped'): void {
  manage('e2e_order_status', '--reference', reference, '--target', target);
}

export async function addToCartAndCheckout(page: import('@playwright/test').Page, slug: string, name: string) {
  await page.goto(`/es/piezas/${slug}`);
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible();
  await page.getByRole('button', { name: 'Agregar al carrito' }).first().click();
  const drawer = page.locator('dialog.cart-drawer');
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText(name)).toBeVisible();
  await page.goto('/es/carrito');
  await page.getByRole('link', { name: /Finalizar compra/ }).click();
  await expect(page).toHaveURL(/\/es\/checkout$/);
}
