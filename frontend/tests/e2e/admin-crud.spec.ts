import { expect, test, type Page } from './fixtures';
import { addToCartAndCheckout, adminSession, buyer, createPiece, fillCheckout, localRedirect, manage, simulateWompi, stubWompi } from './support';

test.describe.configure({ mode: 'serial' });
test.setTimeout(120_000);

let root: string;
let errors: string[];
test.beforeEach(async ({ page, context, baseURL }) => {
  const session = adminSession();
  root = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  await context.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  errors = [];
  page.on('pageerror', error => errors.push(error.message));
});
test.afterEach(async () => { expect(errors).toEqual([]); });

const stamp = () => `${Date.now()}${Math.floor(Math.random() * 1000).toString().padStart(3, '0')}`;
const result = (description: string) => test.info().annotations.push({ type: 'resultado', description });
const pk = (script: string) => manage('shell', '-c', script).trim().split('\n').pop()!;
function taxonomy(model: 'Category' | 'Stone' | 'Collection' | 'Material', tag: string) {
  const prefix = { Category: 'categoria', Stone: 'piedra', Collection: 'coleccion', Material: 'material' }[model];
  const slug = `e2e-${prefix}-${tag}`;
  const id = pk(`from apps.catalog.models import ${model}; x=${model}.objects.create(name_es='E2E ${prefix} ${tag}', slug_es='${slug}'); print(x.pk)`);
  return { id, slug, name: `E2E ${prefix} ${tag}` };
}
function cleanTaxonomy(model: 'Category' | 'Stone', id: string) {
  // Only detach fixtures created by this test; leave unrelated pieces untouched.
  const detach = model === 'Category'
    ? `Piece.objects.filter(category_id=${id},sku__startswith='E2E-').update(category=None)`
    : `Piece.stones.through.objects.filter(stone_id=${id},piece__sku__startswith='E2E-').delete()`;
  manage('shell', '-c', `from apps.catalog.models import ${model}, Piece; ${detach}; ${model}.objects.filter(pk=${id}).delete()`);
}
async function savePane(page: Page) { await page.locator('.cat-actions button[type=submit]').click(); }
async function deleteEmpty(page: Page) {
  await page.getByRole('link', { name: 'Eliminar…' }).click();
  await page.locator('input[type=submit], button[type=submit]').filter({ visible: true }).last().click();
}
async function openPiece(page: Page, sku: string) {
  await page.goto(`${root}catalog/piece/?q=${encodeURIComponent(sku)}`);
  await expect(page.locator('.showcase-card')).toHaveCount(1);
  return page.locator('.showcase-card').first();
}
async function editor(page: Page, sku: string) {
  const card = await openPiece(page, sku);
  await card.locator('.showcase-actions a[aria-label="Editar"]').click();
  await expect(page.locator('dialog.pe-dialog')).toBeVisible();
  return page.frameLocator('dialog.pe-dialog iframe');
}
async function deletePiece(page: Page, sku: string) {
  const card = await openPiece(page, sku);
  await card.locator('summary[aria-label="Más acciones"]').click();
  await card.getByRole('link', { name: 'Eliminar…' }).click();
  await page.locator('#ca-pdel-sku').fill(sku);
  await page.locator('button[name=action][value=delete]').click();
}
async function reorder(page: Page, app: string, item: string, ids: string[]) {
  const status = await page.evaluate(async ({ app, item, ids }) => {
    const element = document.querySelector<HTMLElement>(app)!;
    const all = Array.from(document.querySelectorAll<HTMLElement>(item)).map(x => Number(x.dataset.id));
    const selected = ids.map(Number);
    const ordered = [...selected, ...all.filter(x => !selected.includes(x))];
    const body = new FormData(); body.append('ids', JSON.stringify(ordered));
    const csrf = document.querySelector<HTMLInputElement>('[name=csrfmiddlewaretoken]')!.value;
    return (await fetch(element.dataset.reorderUrl!, { method: 'POST', headers: { 'X-CSRFToken': csrf }, body })).status;
  }, { app, item, ids });
  expect(status).toBe(200);
  await page.reload();
}

test.describe('Categorías', () => {
  test.skip(({ isMobile }) => isMobile);
  test('crear con descripciones en ambos idiomas', async ({ page }) => {
    const tag = stamp(), slug = `e2e-categoria-${tag}`;
    try {
      await page.goto(`${root}catalog/category/?category=new`);
      await page.locator('#id_name_es').fill(`E2E Categoría ${tag}`);
      await page.locator('#id_description_es').fill('Descripción en español');
      await page.locator('[data-lang=en]').click();
      await page.locator('#id_name_en').fill(`E2E Category ${tag}`);
      await page.locator('#id_description_en').fill('English description');
      await page.locator('summary').filter({ hasText: 'Google y dirección web' }).click();
      await page.locator('#id_slug_en').fill(`e2e-category-${tag}`);
      await page.locator('[data-lang=es]').click();
      await page.locator('#id_slug_es').fill(slug);
      await savePane(page);
      await expect(page.locator('.cat-row').filter({ hasText: `E2E Categoría ${tag}` })).toBeVisible();
      result('La categoría creada aparece en el administrador con textos ES y EN.');
    } finally { manage('shell', '-c', `from apps.catalog.models import Category; Category.objects.filter(slug_es='${slug}',pieces__isnull=True).delete()`); }
  });
  test('editar descripción y conservarla al recargar', async ({ page }) => {
    const c = taxonomy('Category', stamp());
    try { await page.goto(`${root}catalog/category/?category=${c.id}`); await page.locator('#id_description_es').fill('Descripción persistente'); await savePane(page); await page.reload(); await expect(page.locator('#id_description_es')).toHaveValue('Descripción persistente'); result('La descripción editada persiste.'); } finally { cleanTaxonomy('Category', c.id); }
  });
  test('reordenar categorías y conservar el orden', async ({ page }) => {
    const a = taxonomy('Category', stamp()), b = taxonomy('Category', stamp());
    try { await page.goto(`${root}catalog/category/?category=${a.id}`); await reorder(page, '.cat-app', '.cat-row[data-parent=""]', [b.id, a.id]); const ids = await page.locator('.cat-row[data-parent=""]').evaluateAll(rows => rows.map(row => (row as HTMLElement).dataset.id)); expect(ids.indexOf(b.id)).toBeLessThan(ids.indexOf(a.id)); result('El orden de categorías persiste tras recargar.'); } finally { cleanTaxonomy('Category', a.id); cleanTaxonomy('Category', b.id); }
  });
  test('eliminar categoría vacía', async ({ page }) => {
    const c = taxonomy('Category', stamp());
    try { await page.goto(`${root}catalog/category/?category=${c.id}`); await deleteEmpty(page); await expect(page.locator(`.cat-row[data-id="${c.id}"]`)).toHaveCount(0); result('La categoría vacía desaparece.'); } finally { cleanTaxonomy('Category', c.id); }
  });
  test('rechazar categoría sin nombre', async ({ page }) => {
    await page.goto(`${root}catalog/category/?category=new`); await savePane(page); await expect(page.locator('.cat-detail .errorlist').first()).toBeVisible(); result('El formulario exige un nombre.');
  });
  test('bloquear borrado con piezas y resolver moviéndolas', async ({ page }) => {
    const a = taxonomy('Category', stamp()), b = taxonomy('Category', stamp()), piece = createPiece();
    try {
      manage('shell', '-c', `from apps.catalog.models import Piece; Piece.objects.filter(sku='${piece.sku}').update(category_id=${a.id})`);
      await page.goto(`${root}catalog/category/?category=${a.id}`); await page.getByRole('link', { name: 'Eliminar…' }).click();
      await expect(page.locator('.ca-guide-row')).toContainText(piece.sku); await expect(page.locator('[data-guide-submit]')).toBeDisabled();
      await page.locator('[data-guide-decision]').selectOption(`move:${b.id}`); await page.locator('[data-guide-submit]').click();
      await expect(page.locator(`.cat-row[data-id="${a.id}"]`)).toHaveCount(0);
      expect(pk(`from apps.catalog.models import Piece; print(Piece.objects.get(sku='${piece.sku}').category_id)`)).toBe(b.id);
      result('La guía exige reasignar la pieza y elimina la categoría.');
    } finally { cleanTaxonomy('Category', a.id); cleanTaxonomy('Category', b.id); }
  });
});

test.describe('Piedras', () => {
  test.skip(({ isMobile }) => isMobile);
  test('crear con color, editar descripción y eliminar', async ({ page }) => {
    const tag = stamp(), slug = `e2e-piedra-${tag}`;
    try {
      await page.goto(`${root}catalog/stone/?stone=new`); await page.locator('#id_name_es').fill(`E2E Piedra ${tag}`);
      await page.locator('summary').filter({ hasText: 'Google y dirección web' }).click(); await page.locator('#id_slug_es').fill(slug);
      await page.locator('[data-swatch="0"]').click(); await savePane(page);
      await expect(page.locator('.cat-row').filter({ hasText: `E2E Piedra ${tag}` }).locator('.stone-dot')).toHaveCSS('background-color', 'rgb(31, 122, 85)');
      await page.locator('#id_description_es').fill('Gema editada'); await savePane(page); await page.reload(); await expect(page.locator('#id_description_es')).toHaveValue('Gema editada');
      await deleteEmpty(page); await expect(page.locator('.cat-row').filter({ hasText: `E2E Piedra ${tag}` })).toHaveCount(0); result('El color y la descripción persisten y la piedra vacía se elimina.');
    } finally { manage('shell', '-c', `from apps.catalog.models import Stone; Stone.objects.filter(slug_es='${slug}',pieces__isnull=True).delete()`); }
  });
  test('rechazar colores inválidos y bloquear borrado con piezas', async ({ page }) => {
    const s = taxonomy('Stone', stamp()), piece = createPiece();
    try {
      manage('shell', '-c', `from apps.catalog.models import Piece,Stone; Piece.objects.get(sku='${piece.sku}').stones.add(Stone.objects.get(pk=${s.id}))`);
      for (const color of ['verde', '#12345']) { await page.goto(`${root}catalog/stone/?stone=${s.id}`); await page.locator('#id_color').fill(color); await savePane(page); await expect(page.locator('.errorlist').first()).toBeVisible(); }
      await page.goto(`${root}catalog/stone/?stone=${s.id}`); await page.getByRole('link', { name: 'Eliminar…' }).click(); await expect(page.locator('.ca-guide-row')).toContainText(piece.sku); await expect(page.locator('[data-guide-submit]')).toBeDisabled(); result('Se rechazan los colores inválidos y se protege la piedra vinculada.');
    } finally { cleanTaxonomy('Stone', s.id); }
  });
});

test.describe('Colecciones', () => {
  test.skip(({ isMobile }) => isMobile);
  test('crear, curar, reordenar y retirar piezas', async ({ page }) => {
    const tag = stamp(), slug = `e2e-coleccion-${tag}`, first = createPiece(), second = createPiece();
    await page.goto(`${root}catalog/collection/?collection=new`); await page.locator('#id_name_es').fill(`E2E Colección ${tag}`); await page.locator('summary').filter({ hasText: 'Google y dirección web' }).click(); await page.locator('#id_slug_es').fill(slug); await page.locator('.collection-dialog button[type=submit]').click();
    for (const p of [first, second]) { await page.locator('[data-search]').fill(p.sku); await page.locator('.collection-item button').click(); }
    await page.locator('.collection-card').nth(1).focus(); await page.keyboard.press('ArrowLeft'); await expect(page.locator('.collection-card').first()).toContainText(second.name);
    await page.getByRole('button', { name: `Quitar ${first.name}` }).click(); await page.locator('[data-save]').click(); await expect(page.locator('[data-message]')).toHaveText('Colección guardada.'); await page.reload(); await expect(page.locator('.collection-card')).toHaveCount(1); await expect(page.locator('.collection-card')).toContainText(second.name); result('La curación y el orden sobreviven a la recarga.');
  });
  test('rechazar nombre vacío y curación con pieza inexistente', async ({ page }) => {
    const c = taxonomy('Collection', stamp());
    await page.goto(`${root}catalog/collection/?collection=new`); await page.locator('.collection-dialog button[type=submit]').click(); await expect(page.locator('.collection-dialog .errorlist').first()).toBeVisible();
    await page.goto(`${root}catalog/collection/?collection=${c.id}`);
    const status = await page.evaluate(async () => { const app = document.querySelector<HTMLElement>('.collection-app')!; const csrf = document.querySelector<HTMLInputElement>('[name=csrfmiddlewaretoken]')!.value; return (await fetch(app.dataset.url!, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify({ collection: Number(app.dataset.id), pieces: [2147483647] }) })).status; });
    expect(status).toBe(400); await expect(page.locator('.collection-card')).toHaveCount(0); await page.reload(); await expect(page.locator('.collection-card')).toHaveCount(0); result('El nombre vacío y la pieza inexistente se rechazan.');
  });
});

test.describe('Materiales', () => {
  test.skip(({ isMobile }) => isMobile);
  test('crear con tono, editar inglés, reordenar y eliminar', async ({ page }) => {
    const tag = stamp(), slug = `e2e-material-${tag}`, other = taxonomy('Material', stamp());
    await page.goto(`${root}catalog/material/?material=new`); await page.locator('[name=name_es]').fill(`E2E Material ${tag}`); await page.locator('[name=name_en]').fill('E2E Material'); await page.locator('[data-color="#e3a98e"]').click(); await page.locator('summary').filter({ hasText: 'Dirección web' }).click(); await page.locator('[name=slug_es]').fill(slug); await page.locator('.mat-form button[type=submit]').click();
    const card = page.locator('.mat-card').filter({ hasText: `E2E Material ${tag}` }); await card.getByText('Editar').click(); await page.locator('[name=name_en]').fill('E2E Rose material'); await page.locator('.mat-form button[type=submit]').click(); await expect(card).toContainText('E2E Rose material');
    const id = (await card.getAttribute('data-id'))!; await reorder(page, '.mat-app', '.mat-card[data-id]', [id, other.id]); await expect(page.locator('.mat-card').first()).toHaveAttribute('data-id', id);
    await page.locator(`.mat-card[data-id="${id}"]`).getByText('Editar').click(); await expect(page.locator('[name=color]')).toHaveValue('#e3a98e'); await page.goto(`${root}catalog/material/`); await page.locator(`.mat-card[data-id="${id}"]`).getByRole('link', { name: 'Eliminar…' }).click(); await page.locator('input[type=submit], button[type=submit]').filter({ visible: true }).last().click(); await expect(page.locator(`.mat-card[data-id="${id}"]`)).toHaveCount(0); result('El tono, nombre inglés y orden persisten; el material se elimina.');
  });
  test('rechazar tono inválido', async ({ page }) => {
    await page.goto(`${root}catalog/material/?material=new`); await page.locator('[name=name_es]').fill(`E2E Material ${stamp()}`); await page.locator('[name=color]').fill('verde'); await page.locator('.mat-form button[type=submit]').click(); await expect(page.locator('.mat-form .errorlist').first()).toBeVisible(); result('El formulario rechaza un tono inválido.');
  });
});

test.describe('Piezas', () => {
  test.skip(({ isMobile }) => isMobile);
  test('crear pieza desde el formulario de alta', async ({ page }) => {
    const tag = stamp(), sku = `E2E-${tag}`, category = taxonomy('Category', tag);
    try {
      await page.goto(`${root}catalog/piece/add/`);
      await page.locator('[name=name_es]').fill(`E2E Pieza ${tag}`); await page.locator('[name=sku]').fill(sku);
      await page.locator('[name=short_description_es]').fill('Descripción corta'); await page.locator('[name=long_description_es]').fill('Descripción larga de la pieza.');
      await page.locator('[name=category]').selectOption(category.id); await page.locator('[name=price_cents]').fill('1234567');
      await page.locator('button[name=_continue]').click();
      const card = await openPiece(page, sku); await expect(card).toContainText('$ 1.234.567'); result('El alta guarda la pieza y presenta el precio en pesos.');
    } finally { cleanTaxonomy('Category', category.id); }
  });
  test('editar precio y oferta desde la ventana flotante', async ({ page }) => {
    const piece = createPiece(), frame = await editor(page, piece.sku);
    await frame.locator('details').filter({ hasText: 'Precio y disponibilidad' }).evaluate(el => (el as HTMLDetailsElement).open = true);
    await frame.locator('[name=price_cents]').fill('1500000'); await frame.locator('[name=sale_price_cents]').fill('1200000'); await frame.locator('button[name=_save]').click();
    await expect(page.locator('dialog.pe-dialog')).toBeHidden(); await expect(page.locator('.showcase-card')).toContainText('$ 1.200.000');
    await page.goto(`/es/piezas/${piece.slug_es}`); await expect(page.locator('body')).toContainText(/1[.,]200[.,]000/); result('El editor guarda el precio y la tienda muestra la oferta.');
  });
  test('rechazar precios inválidos y SKU duplicado', async ({ page }) => {
    const piece = createPiece(), duplicate = createPiece();
    const before = pk(`from apps.catalog.models import Piece; print(Piece.objects.get(sku='${piece.sku}').price_cents)`);
    for (const value of ['', '-1', 'texto']) {
      const frame = await editor(page, piece.sku); const field = frame.locator('[name=price_cents]');
      await frame.locator('details').filter({ hasText: 'Precio y disponibilidad' }).evaluate(el => (el as HTMLDetailsElement).open = true);
      if (value === 'texto') await field.evaluate((el: HTMLInputElement) => { el.type = 'text'; });
      await field.fill(value); await frame.locator('button[name=_save]').click();
      // Either the browser blocks the submit (required/min) or the server returns a form error.
      await expect.poll(async () => {
        try { return (await frame.locator('.errorlist').count()) > 0 || await field.evaluate((el: HTMLInputElement) => !el.checkValidity()); }
        catch { return false; } // the iframe may be reloading with the server's error page
      }).toBe(true);
      expect(pk(`from apps.catalog.models import Piece; print(Piece.objects.get(sku='${piece.sku}').price_cents)`)).toBe(before);
      await page.goto(`${root}catalog/piece/`);
    }
    const frame = await editor(page, piece.sku); await frame.locator('[name=sku]').fill(duplicate.sku); await frame.locator('button[name=_save]').click(); await expect(frame.locator('.errorlist').first()).toBeVisible();
    expect(pk(`from apps.catalog.models import Piece; print(Piece.objects.filter(sku='${piece.sku}').count())`)).toBe('1'); result('Los precios inválidos y el SKU duplicado no se guardan.');
  });
  test('ocultar y publicar desde las acciones de la vitrina', async ({ page }) => {
    const piece = createPiece(); let card = await openPiece(page, piece.sku);
    await card.locator('summary[aria-label="Más acciones"]').click(); await card.getByRole('link', { name: 'Ocultar', exact: true }).click();
    const confirm = page.locator('button[type=submit], input[type=submit]').filter({ visible: true }).last(); await confirm.click();
    card = await openPiece(page, piece.sku); await expect(card.locator('.showcase-ribbon')).toHaveText('Oculta');
    await card.locator('summary[aria-label="Más acciones"]').click(); await card.getByRole('link', { name: 'Publicar', exact: true }).click(); await page.locator('button[type=submit], input[type=submit]').filter({ visible: true }).last().click();
    card = await openPiece(page, piece.sku); await expect(card.locator('.showcase-ribbon')).toHaveCount(0); result('La cinta refleja los cambios de publicación.');
  });
  test('eliminar definitivamente una pieza sin historial', async ({ page, request }) => {
    const piece = createPiece(); await deletePiece(page, piece.sku);
    expect(pk(`from apps.catalog.models import Piece; print(Piece.objects.filter(sku='${piece.sku}').exists())`)).toBe('False');
    const response = await request.get(`/es/piezas/${piece.slug_es}`, { maxRedirects: 0 }); expect([301, 404]).toContain(response.status()); result('La pieza se borra y su antigua dirección deja de servir la ficha.');
  });
  test('eliminar pieza vendida conservando el pedido y seguimiento', async ({ page, baseURL }) => {
    const piece = createPiece(), wompi = await stubWompi(page);
    let orderNumber = '';
    try {
    await addToCartAndCheckout(page, piece.slug_es, piece.name); await fillCheckout(page, buyer('crud-paid'), 'online'); await page.getByRole('button', { name: /Confirmar pedido/ }).click(); await expect(page.getByRole('button', { name: 'Wompi stub' })).toBeVisible();
    const fields = wompi(), reference = fields.get('reference')!, orderUrl = localRedirect(fields.get('redirect-url')!, baseURL!); simulateWompi(reference, 'APPROVED'); await page.goto(orderUrl); await expect(page.getByRole('heading', { name: 'Esta pieza es solo tuya.' })).toBeVisible();
    orderNumber = reference.replace(/-\d+$/, '');
    await page.goto(`${root}orders/order/?q=${encodeURIComponent(orderNumber)}`); await page.getByRole('link', { name: /Ver pedido/ }).first().click();
    const detail = page.locator('.ord-detail'); await expect(detail).toContainText(piece.sku); const before = (await detail.locator('.ord-kv').first().textContent())!;
    await deletePiece(page, piece.sku); await page.goto(`${root}orders/order/?q=${encodeURIComponent(orderNumber)}`); await page.getByRole('link', { name: /Ver pedido/ }).first().click();
    await expect(page.locator('.ord-detail')).toContainText(piece.name); await expect(page.locator('.ord-detail')).toContainText(piece.sku); await expect(page.locator('.ord-detail .ord-kv').first()).toHaveText(before); // subtotal, total y pago intactos
    expect((await page.goto(orderUrl))?.status()).toBe(200); result('El pedido pagado conserva su línea y sus importes tras el borrado.');
    } finally {
      // e2e_cleanup also removes orders whose lines kept only the E2E- SKU snapshot.
    }
  });
  test('bloquear eliminación definitiva de pieza con pago pendiente', async ({ page }) => {
    const piece = createPiece(), wompi = await stubWompi(page);
    await addToCartAndCheckout(page, piece.slug_es, piece.name); await fillCheckout(page, buyer('crud-pending'), 'online'); await page.getByRole('button', { name: /Confirmar pedido/ }).click(); await expect(page.getByRole('button', { name: 'Wompi stub' })).toBeVisible(); expect(wompi().get('reference')).toBeTruthy();
    const card = await openPiece(page, piece.sku); await card.locator('summary[aria-label="Más acciones"]').click(); await card.getByRole('link', { name: 'Eliminar…' }).click();
    await expect(page.locator('.ca-pdel-blockers')).toContainText(/Reserva activa|Pedido pendiente/); await expect(page.locator('button[name=action][value=delete]')).toBeDisabled(); result('La reserva o el pago pendiente impide el borrado definitivo.');
  });
});

test.describe('Humo móvil', () => {
  test('abrir las cinco pantallas sin errores ni desbordamiento', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'Solo se ejecuta en el proyecto móvil');
    for (const path of ['piece', 'category', 'stone', 'collection', 'material']) {
      await page.goto(`${root}catalog/${path}/`); await expect(page.locator('body')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), path).toBe(true);
    }
    result('Las cinco pantallas móviles cargan sin errores ni desplazamiento horizontal.');
  });
});
