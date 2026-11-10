import { test, expect } from './fixtures';
import { resolve } from 'node:path';
import { readFileSync } from 'node:fs';
import { adminSession, manage } from './support';

const initialState = () => JSON.parse(manage('shell','-c',`import json
from apps.cms.models import HomePublication
from apps.cms.publishing import pending_changes
p=HomePublication.objects.first()
assert p is not None, 'Publica Inicio antes de ejecutar la prueba'
assert pending_changes('home')['count']==0, 'Respalda los borradores antes de ejecutar la prueba'
print(json.dumps({'publication':p.pk}))`).trim().split('\n').pop()!);

function restore(publication: number) {
  manage('shell','-c',`from django.conf import settings
assert settings.DEBUG
from apps.cms.models import HomePublication
from apps.cms.services import restore_home,publish_home
from apps.cms.documents import get_document
from apps.accounts.models import User
u=User.objects.filter(groups__name='Propietario',is_staff=True).order_by('-pk').first()
restore_home(HomePublication.objects.get(pk=${publication}),u,expected_version=get_document('home').draft_version)
publish_home(u,expected_version=get_document('home').draft_version)`);
}

test('Inicio: selección, autosave, celular, conflicto y publicación revisada', async ({ page, context, isMobile, browser }) => {
  test.skip(isMobile, 'El editor completo se prueba en escritorio');
  test.setTimeout(120_000);
  const session=adminSession('Propietario');
  const initial=initialState();
  const tag=`Edición ${Date.now()}`;
  await context.addCookies([{name:'sessionid',value:session.value,url:'http://localhost:8090'}]);
  const root=session.admin_url.split('/orders/')[0].replace(/\/?$/,'/');
  const editor=`${root}editor/`;
  const api=`${root}editor/documento/`;
  try {
    manage('shell','-c',`from apps.cms.models import HomeSection
from apps.cms.services import save_section
from apps.cms.documents import get_document
from apps.accounts.models import User
u=User.objects.filter(groups__name='Propietario').order_by('-pk').first()
save_section(HomeSection(kind='statement',title_es='${tag}',title_en='English',position=10000),actor=u,expected_version=get_document('home').draft_version)`);
    await page.goto(editor);
    await page.locator('.cms-section-select').filter({hasText:tag}).click();
    const data=await (await context.request.get(api)).json();
    const section=data.sections.find((s: {values:{title?:{es:string}}})=>s.values.title?.es===tag);
    const frame=page.frameLocator('#cms-frame');
    await frame.locator(`[data-cms-section="${section.id}"]`).click();
    const title=page.getByRole('textbox',{name:'Título (ES)',exact:true});
    await expect(title).toHaveValue(tag);
    const edited=tag+' actualizado';
    await title.fill(edited);
    await expect(page.locator('#cms-save-status')).toHaveText('Guardado');
    await expect(frame.getByRole('heading',{name:edited,exact:true})).toBeVisible();
    await page.locator('#cms-device').selectOption('390');
    await expect(page.locator('#cms-frame')).toHaveCSS('width','390px');
    await page.screenshot({path:test.info().outputPath('editor-celular.png'),fullPage:true});
    // A second authenticated request simulates another editor saving the same document.
    const current=await (await context.request.get(api)).json();
    const csrf=await page.locator('[name=csrfmiddlewaretoken]').first().inputValue();
    const conflict=await context.request.post(api,{headers:{'X-CSRFToken':csrf},data:{action:'update',id:section.id,expected_version:current.version,values:{...section.values,title:{es:'Cambio del equipo',en:'Team change'}}}});
    expect(conflict.status()).toBe(200);
    await title.fill(edited+' local');
    await expect(page.locator('#cms-conflict')).toBeVisible();
    await page.screenshot({path:test.info().outputPath('conflicto.png'),fullPage:true});
    await page.getByRole('button',{name:'Copiar mis textos'}).click();
    expect(await page.locator('#cms-copy-text').inputValue()).toContain(edited+' local');
    await page.getByRole('button',{name:'Ver sus cambios (recargar)'}).click();
    await page.locator('.cms-section-select').filter({hasText:'Cambio del equipo'}).click();
    await page.getByRole('textbox',{name:'Título (ES)',exact:true}).fill(edited);
    await expect(page.locator('#cms-save-status')).toHaveText('Guardado');
    const contentSession=adminSession('Contenido');
    const contentContext=await browser.newContext({baseURL:'http://localhost:8090'});
    try {
      await contentContext.addCookies([{name:'sessionid',value:contentSession.value,url:'http://localhost:8090'}]);
      const contentPage=await contentContext.newPage();await contentPage.goto(editor);
      await expect(contentPage.locator('#cms-sections li').first()).toBeVisible();
      await expect(contentPage.locator('#cms-review')).toHaveCount(0);
    } finally {await contentContext.close();}
    await page.locator('#cms-review').click();
    await expect(page.getByText('Revisar y publicar',{exact:true}).first()).toBeVisible();
    await page.getByLabel('Nota opcional').fill('Prueba del editor visual');
    await page.getByRole('button',{name:'Publicar ahora'}).click();
    // Public context has no draft cookies.
    const publicContext=await browser.newContext({baseURL:'http://localhost:8090'});
    try {const publicPage=await publicContext.newPage();await publicPage.goto('/es');await expect(publicPage.getByRole('heading',{name:edited,exact:true})).toBeVisible();await expect(publicPage.locator('[data-cms-section]')).toHaveCount(0);} finally {await publicContext.close();}
  } finally {restore(initial.publication);}
});

test('el cajón permite editar en ancho tableta', async ({page,context,isMobile})=>{
  test.skip(isMobile,'Caso del cajón en el proyecto de escritorio');
  const session=adminSession('Contenido');
  await context.addCookies([{name:'sessionid',value:session.value,url:'http://localhost:8090'}]);
  await page.setViewportSize({width:820,height:1000});
  await page.goto(`${session.admin_url.split('/orders/')[0].replace(/\/?$/,'/')}editor/`);
  await expect(page.locator('.cms-structure')).toBeVisible();
  await page.locator('.cms-section-select').first().click();
  await expect(page.locator('.cms-properties')).toBeVisible();
  await page.getByRole('button',{name:'Vista previa',exact:true}).click();
  await expect(page.locator('.cms-preview')).toBeVisible();
});


test('carrusel: subir una foto para celular, verla y eliminarla', async ({page,context,isMobile})=>{
  test.skip(isMobile,'El panel se prueba en escritorio con la vista previa en Celular');
  test.setTimeout(120_000);
  const session=adminSession('Contenido');
  const initial=initialState();
  const root=session.admin_url.split('/orders/')[0].replace(/\/?$/,'/');
  const api=`${root}editor/documento/`;
  const tag=`Portada de prueba ${Date.now()}`;
  await context.addCookies([{name:'sessionid',value:session.value,url:'http://localhost:8090'}]);
  let heroId: string | undefined;
  try {
    manage('shell','-c',`from apps.cms.models import HomeSection
from apps.cms.services import save_section
from apps.cms.documents import get_document
from apps.accounts.models import User
u=User.objects.filter(groups__name='Contenido').order_by('-pk').first()
save_section(HomeSection(kind='hero',title_es='${tag}',title_en='Test cover',position=10000),actor=u,expected_version=get_document('home').draft_version)`);
    await page.goto(`${root}editor/`);
    await page.locator('.cms-section-select').filter({hasText:tag}).click();
    const state=await (await context.request.get(api)).json();
    heroId=state.sections.find((s: {values:{title?:{es:string}}})=>s.values.title?.es===tag).id;
    const mobile=page.locator('[data-carousel="mobile"]');
    await mobile.getByRole('button',{name:'Elegir de la biblioteca',exact:true}).click();
    const library=page.getByRole('dialog',{name:'Elegir de la biblioteca'});
    const [upload] = await Promise.all([
      page.waitForResponse(response=>response.url().endsWith('/biblioteca/api/') && response.request().method()==='POST'),
      library.getByLabel('Subir nuevas fotos').setInputFiles({name:'portada.png',mimeType:'image/png',buffer:Buffer.concat([readFileSync(resolve(__dirname,'fixtures/cms-carousel-mobile.png')),Buffer.from(tag)])}),
    ]);
    expect(upload.ok()).toBe(true);
    const assetId=(await upload.json()).items[0].asset.id;
    await expect.poll(async ()=>(await (await context.request.get(`${root}biblioteca/api/${assetId}/`,{timeout:5000})).json()).state,{timeout:45000}).toBe('ready');
    // The ready poll redraws the fields; fill only after that redraw completes.
    await expect(library.getByRole('button',{name:'Usar esta foto',exact:true})).toBeEnabled({timeout:10000});
    await library.getByLabel('Texto alternativo (ES)',{exact:true}).fill(tag);
    await library.getByLabel('Texto alternativo (EN)',{exact:true}).fill('Workshop photo');
    await expect(library.getByRole('button',{name:'Usar esta foto',exact:true})).toBeEnabled({timeout:60000});
    await library.getByRole('button',{name:'Usar esta foto',exact:true}).click();
    await expect(library).not.toBeVisible({timeout:60000});
    await expect(mobile.locator('[data-slide]')).toHaveCount(1);
    await expect(page.locator('#cms-save-status')).toHaveText('Guardado');
    const thumbnail=mobile.locator('img');
    await expect(thumbnail).toHaveAttribute('src',/\.webp$/);
    const alt=tag;
    await page.locator('#cms-device').selectOption('390');
    const image=page.frameLocator('#cms-frame').locator(`[data-cms-section="${heroId}"] .hero-slide--mobile img`);
    await expect(image).toHaveAttribute('alt',alt);
    await image.scrollIntoViewIfNeeded();
    await expect(image).toBeVisible();
    await expect(image).toHaveAttribute('src',/\.webp$/);
    await expect.poll(()=>image.evaluate((el: HTMLImageElement)=>el.complete && el.naturalWidth>0)).toBe(true);
    await mobile.getByRole('button',{name:'Eliminar foto 1',exact:true}).click();
    await page.locator('#cms-confirm-yes').click();
    await expect(mobile.locator('[data-slide]')).toHaveCount(0);
    const cleaned=await (await context.request.get(api)).json();
    expect(cleaned.sections.find((s:{id:string})=>s.id===heroId).values.slides).toHaveLength(0);
  } finally {
    // Also delete through the versioned API if an assertion interrupted the UI cleanup.
    try {
      if(heroId) {
        const state=await (await context.request.get(api,{timeout:5000})).json();
        const hero=state.sections.find((s:{id:string})=>s.id===heroId);
        let version=state.version;
        const csrf=(await context.cookies()).find(cookie=>cookie.name==='csrftoken')?.value || '';
        for(const slide of hero?.values.slides || []) {
          const result=await context.request.post(api,{timeout:5000,headers:{'X-CSRFToken':csrf},data:{action:'hero-delete',id:heroId,slide:slide.id,device:slide.device,expected_version:version}});
          expect(result.status()).toBe(200);version=(await result.json()).version;
        }
      }
    } finally { restore(initial.publication); }
  }
});
