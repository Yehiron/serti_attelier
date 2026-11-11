import { test, expect } from './fixtures';
import { adminSession, manage } from './support';

let initial: { publication: number; snapshot: Record<string, unknown> } | undefined;
// Runs even if the scenario fails. Browser teardown cancels pending autosave timers;
// the synchronous service waits for the document lock and verifies exact restored state.
test.afterAll(async () => {
  if (!initial) return;
  const encoded=Buffer.from(JSON.stringify(initial)).toString('base64');
  manage('shell','-c',`import base64,json
from django.conf import settings
from django.db import transaction
from apps.accounts.models import User
from apps.cms import brand
from apps.cms.models import BrandPublication
from apps.cms.documents import lock_document
from apps.cms.publishing import pending_changes
assert settings.DEBUG
initial=json.loads(base64.b64decode('${encoded}'))
u=User.objects.filter(groups__name='Propietario').order_by('-pk').first()
with transaction.atomic():
 doc=lock_document(brand.KEY)
 brand.restore(BrandPublication.objects.get(pk=initial['publication']),u,expected_version=doc.draft_version)
 doc.refresh_from_db()
 brand.publish(u,expected_version=doc.draft_version)
assert brand.public_identity()==initial['snapshot']
assert pending_changes(brand.KEY)['count']==0
print('Identidad original restaurada y publicada')`);
});

test('identidad: vista previa, contraste, publicación y tipografía', async ({page,context,browser,isMobile}) => {
  test.skip(isMobile,'La Fase 7 se prueba en escritorio');
  test.setTimeout(180_000);
  const session=adminSession('Propietario');
  const root=session.admin_url.split('/orders/')[0].replace(/\/?$/,'/');
  initial=JSON.parse(manage('shell','-c',`import json
from django.conf import settings
from apps.cms import brand
from apps.cms.documents import get_document
from apps.cms.publishing import pending_changes
assert settings.DEBUG
assert pending_changes(brand.KEY)['count']==0, 'Respalda o publica el borrador antes de la prueba'
doc=get_document(brand.KEY)
assert all(doc.brand_publication.snapshot[k] is None for k in brand.SLOTS), 'Usa una identidad original sin logos personalizados en la base E2E'
print(json.dumps({'publication':doc.brand_publication_id,'snapshot':brand.public_identity()}))`).trim().split('\n').pop()!);
  await context.addCookies([{name:'sessionid',value:session.value,url:'http://localhost:8090'}]);
  const publicContext=await browser.newContext({baseURL:'http://localhost:8090'});
  const storefront=await publicContext.newPage();
  const editor=async()=>{await page.goto(`${root}editor/?document=brand:identity`);await expect(page.getByLabel('Color principal: código hexadecimal',{exact:true})).toBeVisible();};
  const save=async()=>{
    await page.getByRole('button',{name:'Guardar cambios',exact:true}).click();
    await expect(page.locator('#cms-save-status')).toHaveText('Guardado');
    await expect(page.locator('#cms-review')).not.toHaveAttribute('aria-disabled','true');
  };
  try {
    await editor();
    await expect(page.getByRole('group',{name:'Idioma de los textos',exact:true})).toBeHidden();
    await expect(page.getByRole('button',{name:'Añadir sección',exact:true})).toBeHidden();
    await expect(page.locator('#cms-sections .cms-row-tools')).toHaveCount(0);
    await expect(page.locator('#cms-section-actions button')).toHaveCount(0);
    await expect(page.getByText('Sin imagen (se usa la de cada página)',{exact:true})).toBeVisible();
    await expect(page.getByRole('button',{name:'Quitar imagen',exact:true})).toBeVisible();
    await expect(page.getByRole('button',{name:'Ícono original',exact:true})).toBeVisible();
    await page.getByLabel('Color principal: código hexadecimal',{exact:true}).fill('#6a1f36');
    await save();
    await expect.poll(()=>page.frameLocator('#cms-frame').locator('html').evaluate(el=>getComputedStyle(el).getPropertyValue('--color-wine').trim())).toBe('#6a1f36');
    await page.getByLabel('Acento: código hexadecimal',{exact:true}).fill('#ffffff');
    await save();
    await expect(page.locator('.cms-brand-checks')).toContainText('✗');
    await page.locator('#cms-review').click();
    await expect(page.getByRole('button',{name:'Publicar ahora',exact:true})).toBeDisabled();
    await expect(page.getByText(/No se puede publicar: ajusta los colores/)).toBeVisible();
    await expect(page.getByText(/El texto al pasar sobre el botón no se lee bien/)).toBeVisible();
    await expect(page.getByText('Revisa los textos en español e inglés.',{exact:false})).toHaveCount(0);
    await expect(page.locator('.cms-after .cms-color-swatch').first()).toBeVisible();
    await editor();
    await page.getByLabel('Acento: código hexadecimal',{exact:true}).fill('#8a1538');
    await page.getByLabel('Fuente de títulos',{exact:true}).selectOption('cormorant');
    await page.getByLabel('Tamaño de los títulos',{exact:true}).selectOption('110');
    await save();
    await page.locator('#cms-review').click();
    await page.getByRole('button',{name:'Publicar ahora',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Historial de publicaciones',exact:true})).toBeVisible();
    await storefront.goto('/es');
    await expect.poll(()=>storefront.locator('html').evaluate(el=>getComputedStyle(el).getPropertyValue('--color-wine').trim())).toBe('#6a1f36');
    await expect.poll(()=>storefront.locator('html').evaluate(el=>getComputedStyle(el).getPropertyValue('--title-scale').trim())).toBe('1.1');
    await expect.poll(()=>storefront.locator('html').evaluate(el=>getComputedStyle(el).getPropertyValue('--font-serif'))).toContain('Cormorant');
  } finally {
    await page.close();
    await publicContext.close();
  }
});
