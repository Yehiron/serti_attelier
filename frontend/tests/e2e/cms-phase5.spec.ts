import { test, expect } from './fixtures';
import { resolve } from 'node:path';
import { readFileSync } from 'node:fs';
import { adminSession, manage } from './support';

// Requires migrated local stack, PostgreSQL and the existing Celery worker.
// Published history remains immutable; finally restores and republishes the initial document.
test('biblioteca: subir, describir, recortar, elegir, revisar y publicar', async ({ page, context, browser, isMobile }) => {
  test.skip(isMobile, 'El flujo editorial se prueba en escritorio');
  test.setTimeout(180_000);
  const session = adminSession('Propietario');
  const initial = Number(manage('shell', '-c', `from apps.cms.models import HomePublication
from apps.cms.publishing import pending_changes
p=HomePublication.objects.first()
assert p and pending_changes('home')['count']==0, 'Publica o respalda el borrador antes de ejecutar la prueba'
print(p.pk)`).trim().split('\n').pop());
  const root = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  const tag = `Biblioteca ${Date.now()}`;
  await context.addCookies([{ name: 'sessionid', value: session.value, url: 'http://localhost:8090' }]);
  try {
    await page.goto(`${root}biblioteca/`);
    const [upload] = await Promise.all([
      page.waitForResponse(response => response.url().endsWith('/biblioteca/api/') && response.request().method() === 'POST'),
      page.getByLabel('Subir nuevas fotos').setInputFiles({ name: 'biblioteca.png', mimeType: 'image/png', buffer: Buffer.concat([readFileSync(resolve(__dirname, 'fixtures/cms-carousel-mobile.png')), Buffer.from(tag)]) }),
    ]);
    const assetId = (await upload.json()).items[0].asset.id;
    await expect.poll(async () => (await (await context.request.get(`${root}biblioteca/api/${assetId}/`)).json()).state, {timeout: 60_000}).toBe('ready');
    const detail = page.getByRole('complementary', { name: 'Detalle de la foto' });
    await expect(detail.getByLabel('Texto alternativo (ES)', { exact: true })).toBeVisible();
    await expect(page.getByRole('status')).not.toContainText('Preparando versiones', { timeout: 60_000 });
    await detail.getByLabel('Título interno (opcional)').fill(tag);
    await detail.getByLabel('Texto alternativo (ES)', { exact: true }).fill(tag);
    await detail.getByLabel('Texto alternativo (EN)', { exact: true }).fill(`Workshop ${tag}`);
    await detail.getByRole('button', { name: '4:5 celular', exact: true }).click();
    await expect(detail.locator('.cropper-container')).toBeVisible();
    await detail.getByRole('button', { name: 'Recorte más pequeño' }).click();
    await detail.getByRole('button', { name: 'Mover recorte →', exact: true }).click();
    await detail.getByLabel('Punto horizontal', { exact: true }).fill('0.7');
    await detail.getByLabel('Punto vertical', { exact: true }).fill('0.3');
    await Promise.all([
      page.waitForResponse(response => response.url().endsWith(`/biblioteca/api/${assetId}/`) && response.request().method() === 'POST'),
      detail.getByRole('button', { name: 'Guardar foto y recortes' }).click(),
    ]);
    await expect.poll(async () => (await (await context.request.get(`${root}biblioteca/api/${assetId}/`)).json()).state, {timeout: 60_000}).toBe('ready');
    // Add a temporary hero through the normal versioned service, then choose in its mobile slot.
    manage('shell', '-c', `from apps.cms.models import HomeSection
from apps.cms.services import save_section
from apps.cms.documents import get_document
from apps.accounts.models import User
u=User.objects.filter(groups__name='Propietario').order_by('-pk').first()
save_section(HomeSection(kind='hero',title_es='${tag}',title_en='${tag}',position=10000),actor=u,expected_version=get_document('home').draft_version)`);
    await page.goto(`${root}editor/`);
    await page.locator('.cms-section-select').filter({ hasText: tag }).click();
    await page.locator('[data-carousel="mobile"]').getByRole('button', { name: 'Elegir de la biblioteca', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Elegir de la biblioteca' });
    await dialog.getByRole('searchbox').fill(tag);
    await dialog.locator('.cms-library-card').filter({ hasText: tag }).click();
    await dialog.getByRole('button', { name: 'Usar esta foto', exact: true }).click();
    await expect(dialog).not.toBeVisible({ timeout: 60_000 });
    await expect(page.locator('#cms-save-status')).toHaveText('Guardado');
    await page.locator('#cms-device').selectOption('390');
    const frame = page.frameLocator('#cms-frame');
    await expect(frame.getByRole('img', { name: tag, exact: true }).first()).toBeVisible();
    await page.locator('#cms-review').click();
    await page.getByLabel('Nota opcional').fill('Prueba de biblioteca de fotos');
    await page.getByRole('button', { name: 'Publicar ahora' }).click();
    const publicContext = await browser.newContext({ baseURL: 'http://localhost:8090', viewport: { width: 390, height: 844 } });
    try {
      const storefront = await publicContext.newPage();
      await storefront.goto('/es');
      const image = storefront.getByRole('img', { name: tag, exact: true }).first();
      await expect(image).toBeVisible();
      await expect(image).toHaveCSS('object-position', '70% 30%');
      await expect(image).toHaveJSProperty('complete', true);
      await storefront.screenshot({ path: test.info().outputPath('foto-publicada.png'), fullPage: true });
    } finally { await publicContext.close(); }
  } finally {
    manage('shell', '-c', `from django.conf import settings
assert settings.DEBUG
from apps.cms.models import HomePublication,MediaAsset
from apps.cms.services import restore_home,publish_home
from apps.cms.documents import get_document
from apps.accounts.models import User
u=User.objects.filter(groups__name='Propietario').order_by('-pk').first()
restore_home(HomePublication.objects.get(pk=${initial}),u,expected_version=get_document('home').draft_version)
publish_home(u,expected_version=get_document('home').draft_version)
# Historical publication references must survive; archive this test's asset.
MediaAsset.objects.filter(title='${tag}').update(archived=True)`);
  }
});
