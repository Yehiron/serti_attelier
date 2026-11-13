import { test, expect } from './fixtures';
import { adminSession, manage, createPiece, addToCartAndCheckout, fillCheckout, buyer } from './support';

let testSku: string | undefined;
let initial: {home:number; page:number; brand:number; menu:number; url:string} | undefined;
const shell = (code:string) => manage('shell','-c',code).trim().split('\n').pop()!;
const prelude = `from django.conf import settings
assert settings.DEBUG
from apps.accounts.models import User
from apps.cms import services,brand,visual_documents
from apps.cms.documents import get_document,edit_document
from apps.cms.models import HomePublication,HomeSection,Page,PageRevision,BrandPublication,MenuPublication,CacheInvalidation
from apps.cms.menus import restore_menu,publish_menu
from apps.cms.publishing import pending_changes
u=User.objects.filter(groups__name='Propietario',is_staff=True).order_by('-pk').first()
assert u
`;
function saveInitial() {
  markInvalidationBaseline();
  initial=JSON.parse(shell(prelude+`import json
from apps.cms.selectors import page_payload
assert all(pending_changes(k)['count']==0 for k in ['home','page:shipping',brand.KEY,'menu:main']), 'Usa una base sin borradores pendientes'
p=Page.objects.get(kind='shipping')
r=p.revisions.first()
assert r and HomePublication.objects.first()
print(json.dumps({'home':HomePublication.objects.first().pk,'page':r.pk,'brand':get_document(brand.KEY).brand_publication_id,'menu':get_document('menu:main').menu_publication_id,'url':page_payload(p,'es',r)['alternates']['es']}))`));
}
// Only invalidations created by this run count: older failed rows are history, not this test.
let baseline = 0;
function markInvalidationBaseline() {
  baseline = Number(shell(prelude+`print(CacheInvalidation.objects.order_by('-pk').values_list('pk',flat=True).first() or 0)`));
}
async function waitInvalidation() {
  await expect.poll(()=>shell(prelude+`print(CacheInvalidation.objects.filter(pk__gt=${baseline}).exclude(state='sent').count())`),{timeout:30_000,intervals:[200,500,1000]}).toBe('0');
}
function cleanup() {
  if (!initial && !testSku) return;
  if (initial) {
  const data=Buffer.from(JSON.stringify(initial)).toString('base64');
  shell(prelude+`import base64,json
from django.db import transaction
s=json.loads(base64.b64decode('${data}'))
with transaction.atomic():
 services.restore_home(HomePublication.objects.get(pk=s['home']),u,expected_version=get_document('home').draft_version)
 services.publish_home(u,expected_version=get_document('home').draft_version)
 r=PageRevision.objects.get(pk=s['page'])
 services.restore_page_revision(r,u,expected_version=get_document('page:shipping').draft_version)
 services.publish_page(r.page,u,expected_version=get_document('page:shipping').draft_version)
 brand.restore(BrandPublication.objects.get(pk=s['brand']),u,expected_version=get_document(brand.KEY).draft_version)
 brand.publish(u,expected_version=get_document(brand.KEY).draft_version)
 restore_menu(MenuPublication.objects.get(pk=s['menu']),u,expected_version=get_document('menu:main').draft_version)
 publish_menu('menu:main',u,expected_version=get_document('menu:main').draft_version)
assert all(pending_changes(k)['count']==0 for k in ['home','page:shipping',brand.KEY,'menu:main'])
assert get_document(brand.KEY).brand_identity==BrandPublication.objects.get(pk=s['brand']).snapshot
assert get_document('menu:main').menu_items==MenuPublication.objects.get(pk=s['menu']).snapshot
print('Contenido original restaurado; se conserva el historial')`);
  initial=undefined;
  }
  if (testSku) {
    shell(prelude+`from apps.catalog.models import Piece
from apps.catalog.services import delete_piece
from apps.cart.models import Cart
p=Piece.objects.filter(sku='${testSku}').first()
if p:
 assert p.sku.startswith('E2E-') and not p.orderitem_set.exists() and not p.reservations.exists()
 for cart in Cart.objects.filter(items__piece=p):
  assert not cart.items.exclude(piece=p).exists()
  cart.delete()
 # Test fixture only: undo e2e_piece's publication before using conservative deletion.
 Piece.objects.filter(pk=p.pk).update(status='draft')
 p.refresh_from_db()
 delete_piece(p,actor=u)`);
    testSku=undefined;
  }
}
// Runs after fixture teardown, including a failure before entering the scenario's finally.
test.afterEach(()=>cleanup());
test.afterAll(()=>cleanup());

test('publicar home y página invalida la siguiente visita; el borrador permanece privado',async({page,isMobile})=>{
  test.skip(isMobile,'Publicación editorial en escritorio');
  test.setTimeout(120_000);
  adminSession(); saveInitial(); await waitInvalidation();
  await page.goto('/es'); await page.goto(initial!.url); // Warm the published cache first.
  const text=`Publicación fase ocho ${Date.now()}`;
  shell(prelude+`s=HomeSection(kind='statement',title_es='${text}',title_en='Phase eight',position=10000)
services.save_section(s,actor=u,expected_version=get_document('home').draft_version)
p=Page.objects.get(kind='shipping')
p.title_es='${text}'
services.save_page(p,actor=u,expected_version=get_document('page:shipping').draft_version)`);
  await page.goto('/es'); await expect(page.getByRole('heading',{name:text,exact:true})).toHaveCount(0);
  await page.goto(initial!.url); await expect(page.getByRole('heading',{name:text,exact:true})).toHaveCount(0);
  shell(prelude+`services.publish_home(u,expected_version=get_document('home').draft_version)
services.publish_page(Page.objects.get(kind='shipping'),u,expected_version=get_document('page:shipping').draft_version)`);
  // Wait for delivery, not a TTL. A single visit must then contain the new text.
  await waitInvalidation();
  await page.goto('/es'); await expect(page.getByRole('heading',{name:text,exact:true})).toBeVisible();
  await page.goto(initial!.url); await expect(page.getByRole('heading',{level:1,name:text,exact:true})).toBeVisible();
});

test('identidad publicada conserva carrito y checkout en móvil y escritorio',async({page})=>{
  test.setTimeout(120_000);
  adminSession(); saveInitial(); await waitInvalidation();
  const piece=createPiece(); testSku=piece.sku;
  await addToCartAndCheckout(page,piece.slug_es,piece.name);
  const form=page.locator('main form').first();
  await expect(form).toBeVisible();
  // Departments load asynchronously; compare the form once it is complete.
  await expect.poll(()=>page.locator('#department option').count()).toBeGreaterThan(1);
  await expect(form.locator('[aria-busy]')).toHaveAttribute('aria-busy','false');
  await expect(form.locator('.commerce-totals')).toBeVisible();
  const before=await form.innerHTML();
  shell(prelude+`doc=get_document(brand.KEY)
with edit_document(brand.KEY,u,doc.draft_version):
 visual_documents.mutate(brand.KEY,'update',{'id':'brand','values':{'wine':'#6a1f36','title_font':'cormorant','title_scale':110}},u,None)
brand.publish(u,expected_version=get_document(brand.KEY).draft_version)
doc=get_document('home')
with edit_document('home',u,doc.draft_version):
 visual_documents.mutate('home','update',{'id':'seo','values':{'title':{'es':'Inicio de prueba'}}},u,None)
services.publish_home(u,expected_version=get_document('home').draft_version)
doc=get_document('menu:main')
with edit_document('menu:main',u,doc.draft_version):
 doc.menu_items=[{'visible':True,'link':{'kind':'home','label':{'es':'Inicio de prueba','en':'Test home'}}}]
 doc.save(update_fields=['menu_items'])
publish_menu('menu:main',u,expected_version=get_document('menu:main').draft_version)`);
  await waitInvalidation();
  await page.reload();
  await expect(page.locator('html')).toHaveCSS('--color-wine','#6a1f36');
  // Departments load asynchronously; compare the form once it is complete.
  await expect.poll(()=>page.locator('#department option').count()).toBeGreaterThan(1);
  await expect(form.locator('[aria-busy]')).toHaveAttribute('aria-busy','false');
  await expect(form.locator('.commerce-totals')).toBeVisible();
  expect(await form.innerHTML()).toBe(before);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await fillCheckout(page,buyer('cms-phase8'),'manual');
  await expect(page.getByRole('button',{name:/Confirmar pedido/})).toBeEnabled();
  // Exercise the cart again with the custom identity, without creating persistent orders.
  await page.goto('/es/carrito');
  // The header drawer (closed) also lists the piece; check the cart page itself.
  await expect(page.locator('main').getByText(piece.name).first()).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});
