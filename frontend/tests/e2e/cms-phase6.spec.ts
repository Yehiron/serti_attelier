import { test, expect } from './fixtures';
import { adminSession, manage } from './support';

// Local migrated PostgreSQL stack only; no simultaneous editorial work.
// Cleanup preserves immutable history and restores the complete initial live configuration.
test('páginas: dirección, menú, SEO y traducciones con limpieza completa', async ({ page, context, browser, isMobile }) => {
  test.skip(isMobile, 'La Fase 6 se prueba en escritorio');
  test.setTimeout(240_000);
  const session = adminSession('Propietario');
  const root = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  const tag = `fase6-${Date.now()}`;
  const initial = JSON.parse(manage('shell', '-c', `import json
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from apps.cms.models import Page,Redirect,ContentDocument
from apps.cms.publishing import pending_changes
from apps.cms.selectors import page_payload
assert settings.DEBUG
p=Page.objects.get(kind='shipping')
r=p.revisions.first()
keys=['page:shipping','menu:main','menu:footer']
assert r and all(pending_changes(k)['count']==0 for k in keys), 'Respalda o publica los borradores antes de la prueba'
menus={k:ContentDocument.objects.get(key=k).menu_publication_id for k in keys[1:]}
state={k:ContentDocument.objects.get(key=k).seo for k in keys}
page_state={f:getattr(p,f) for f in ['slug_es','slug_en','slug_paths','body_enabled']}
assert all(menus.values())
print(json.dumps({'page':r.pk,'url':page_payload(p,'es',r)['alternates']['es'],'menus':menus,'seo':state,'page_state':page_state,'redirects':list(Redirect.objects.values())},cls=DjangoJSONEncoder))`).trim().split('\n').pop()!);
  await context.addCookies([{ name: 'sessionid', value: session.value, url: 'http://localhost:8090' }]);
  const publicContext = await browser.newContext({ baseURL: 'http://localhost:8090' });
  const publicPage = await publicContext.newPage();
  const saved = async () => { await expect(page.locator('#cms-save-status')).toHaveText('Guardado'); };
  const publish = async () => { await saved(); await page.locator('#cms-review').click(); await page.getByRole('button', { name: 'Publicar ahora', exact: true }).click(); };
  try {
    await page.goto(`${root}editor/?document=page:shipping`);
    await page.getByLabel('Dirección de la página (ES)', { exact: true }).fill(`envios-${tag}`);
    await page.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
    await publish();
    await expect.poll(async () => {
      const response = await publicContext.request.get(initial.url, { maxRedirects: 0 });
      return [response.status(), new URL(response.headers().location || initial.url, 'http://localhost:8090').pathname];
    }, { timeout: 80_000, intervals: [1000, 2000, 5000] }).toEqual([301, `/es/envios-${tag}`]);
    await publicPage.goto(`/es/envios-${tag}`);
    await expect(publicPage.locator('h1')).toBeVisible();

    await page.goto(`${root}editor/?document=menu:main`);
    await page.getByLabel('Texto del enlace (ES)', { exact: true }).first().fill(`Joyería ${tag}`);
    await page.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
    await publish();
    await publicPage.goto('/es');
    await expect(publicPage.locator('.desktop-nav summary').first()).toHaveText(`Joyería ${tag}`);

    await page.goto(`${root}editor/?document=page:shipping&section=seo`);
    await page.getByLabel('Título SEO (ES)', { exact: true }).fill(`Envíos seguros ${tag}`);
    await page.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
    await publish();
    await publicPage.goto(`/es/envios-${tag}`);
    await expect(publicPage).toHaveTitle(new RegExp(`Envíos seguros ${tag}`));
    await expect(publicPage.locator('meta[property="og:title"]')).toHaveAttribute('content', `Envíos seguros ${tag}`);

    await page.goto(`${root}editor/?document=page:shipping&section=page`);
    await page.getByLabel('Título (ES)', { exact: true }).fill(`Texto pendiente ${tag}`);
    await page.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
    await saved();
    await page.getByRole('button', { name: 'EN', exact: true }).click();
    await page.getByLabel('Título (EN)', { exact: true }).fill(`Texto pendiente ${tag}`);
    await page.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
    await saved();
    await page.goto(`${root}traducciones/`);
    const pending = page.getByRole('row').filter({ has: page.getByRole('cell', { name: `Texto pendiente ${tag}`, exact: true }) });
    await expect(pending).toHaveCount(1);
    await pending.getByRole('link', { name: 'Traducir al inglés' }).click();
    await expect(page.getByLabel('Título (EN)', { exact: true })).toBeFocused();
    await page.getByLabel('Título (EN)', { exact: true }).fill(`Shipping information ${tag}`);
    await page.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
    await saved();
    await page.goto(`${root}traducciones/`);
    await expect(page.getByRole('cell', { name: `Texto pendiente ${tag}`, exact: true })).toHaveCount(0);
  } finally {
    try {
      // The fixture is JSON encoded, then parsed by Python: no interpolation of page content as code.
      const encoded = Buffer.from(JSON.stringify(initial)).toString('base64');
      manage('shell', '-c', `import base64,json
from django.conf import settings
from django.db import transaction
from django.core.serializers.json import DjangoJSONEncoder
from apps.accounts.models import User
from apps.cms.models import Page,PageRevision,MenuPublication,Redirect
from apps.cms.publishing import pending_changes
from apps.cms.review_changes import equivalent
from apps.cms.redirects import invalidate_redirects
from apps.cms.documents import get_document
from apps.cms.services import restore_page_revision,publish_page
from apps.cms.menus import restore_menu,publish_menu
assert settings.DEBUG
initial=json.loads(base64.b64decode('${encoded}'))
u=User.objects.filter(groups__name='Propietario').order_by('-pk').first()
with transaction.atomic():
 r=PageRevision.objects.get(pk=initial['page'])
 restore_page_revision(r,u,expected_version=get_document('page:shipping').draft_version)
 publish_page(r.page,u,expected_version=get_document('page:shipping').draft_version)
 for key,pk in initial['menus'].items():
  restore_menu(MenuPublication.objects.get(pk=pk),u,expected_version=get_document(key).draft_version)
  publish_menu(key,u,expected_version=get_document(key).draft_version)
 Redirect.objects.exclude(pk__in=[r['id'] for r in initial['redirects']]).delete()
 for row in initial['redirects']:
  pk=row.pop('id')
  assert Redirect.objects.filter(pk=pk).update(**row)==1
 invalidate_redirects()
p=Page.objects.get(kind='shipping')
assert {f:getattr(p,f) for f in initial['page_state']}==initial['page_state']
for key,seo in initial['seo'].items():
 assert equivalent(get_document(key).seo,seo)
 assert pending_changes(key)['count']==0
for key,pk in initial['menus'].items():
 assert get_document(key).menu_items==MenuPublication.objects.get(pk=pk).snapshot
expected=json.loads(base64.b64decode('${encoded}'))['redirects']
actual=json.loads(json.dumps(list(Redirect.objects.order_by('pk').values()),cls=DjangoJSONEncoder))
assert actual==sorted(expected,key=lambda row:row['id'])`);
    } finally { await publicContext.close(); }
  }
});
