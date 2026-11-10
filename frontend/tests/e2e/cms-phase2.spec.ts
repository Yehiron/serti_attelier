import { test, expect } from './fixtures';
import { adminSession, manage } from './support';

test('Contenido guarda sin publicar; Propietaria resuelve conflicto, revisa y publica exactamente', async ({ browser, baseURL, isMobile }) => {
  test.skip(isMobile, 'Flujo del panel en escritorio');
  test.setTimeout(120_000);
  const contentSession = adminSession('Contenido');
  const ownerSession = adminSession('Propietario');
  const root = ownerSession.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  const initial = JSON.parse(manage('shell', '-c', "import json; from apps.cms.models import Page; p=Page.objects.get(kind='personalize'); print(json.dumps({'id':p.pk,'revision':p.revisions.first().pk}))").trim().split('\n').pop()!);
  const content = await browser.newContext({ baseURL });
  const owner = await browser.newContext({ baseURL });
  const text = `Pregunta de revisión ${Date.now()}`;
  const typed = `Mi texto conservado ${Date.now()}`;
  try {
    await content.addCookies([{ name: contentSession.name, value: contentSession.value, url: baseURL! }]);
    await owner.addCookies([{ name: ownerSession.name, value: ownerSession.value, url: baseURL! }]);
    const contentPage = await content.newPage();
    const ownerPage = await owner.newPage();
    const edit = `${root}cms/page/${initial.id}/change/`;
    await contentPage.goto(edit);
    await ownerPage.goto(edit);
    await expect(contentPage.getByRole('link', { name: 'Revisar y publicar', exact: true })).toHaveCount(0);
    const field = '[name="faq_items-0-question_es"]';
    const setQuestion = async (page: typeof contentPage, value: string) => {
      await page.locator(field).evaluate((element, next) => {
        (element as HTMLInputElement).value = next;
        element.dispatchEvent(new Event('input', { bubbles: true }));
      }, value);
    };
    await setQuestion(contentPage, text);
    await contentPage.locator('[name="_continue"]').click();
    await expect(contentPage.getByText('Cambios pendientes de publicar — la Propietaria puede publicarlos')).toBeVisible();
    const denied = await content.request.get(`${root}revisar-publicacion/page:personalize/`);
    expect(denied.status()).toBe(403);
    await setQuestion(ownerPage, typed);
    await ownerPage.locator('[name="_continue"]').click();
    await expect(ownerPage.getByText(/Otra persona guardó cambios/)).toBeVisible();
    await expect(ownerPage.locator(field)).toHaveValue(typed);
    await expect(ownerPage.getByRole('link', { name: 'Ver versión actual', exact: true })).toHaveAttribute('target', '_blank');
    await ownerPage.goto(edit);
    await expect(ownerPage.locator(field)).toHaveValue(text);
    await ownerPage.getByRole('link', { name: 'Revisar y publicar', exact: true }).click();
    await expect(ownerPage.getByText('Preguntas frecuentes en español actualizadas.', { exact: true })).toBeVisible();
    await ownerPage.getByLabel('Nota opcional').fill('Revisión de permisos y conflicto');
    await ownerPage.getByRole('button', { name: 'Publicar ahora', exact: true }).click();
    await ownerPage.goto('/es/personaliza');
    await expect(ownerPage.locator('.faq-section summary').first()).toHaveText(text);
    await ownerPage.goto(`${root}revisar-publicacion/page:personalize/`);
    await expect(ownerPage.getByText('No hay cambios pendientes', { exact: true })).toBeVisible();
    await expect(ownerPage.getByRole('button', { name: 'Publicar ahora', exact: true })).toBeDisabled();
  } finally {
    // Development-only fixture cleanup. Use a database without drafts to preserve.
    manage('shell', '-c', `from apps.cms.models import PageRevision; from apps.cms.services import restore_page_revision,publish_page; from apps.cms.documents import get_document; from apps.accounts.models import User; r=PageRevision.objects.get(pk=${initial.revision}); u=User.objects.filter(is_staff=True,groups__name='Propietario',username__startswith='e2e-').order_by('-pk').first(); k='page:'+r.page.kind; restore_page_revision(r,u,expected_version=get_document(k).draft_version); publish_page(r.page,u,expected_version=get_document(k).draft_version)`);
    await content.close();
    await owner.close();
  }
});
