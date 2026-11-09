import { test, expect } from './fixtures';
import { adminSession, manage } from './support';

test('Personaliza guarda un borrador, publica ambos idiomas y protege el preview localizado', async ({ page, context, baseURL, isMobile }) => {
  // The dashboard editing flow is exercised on desktop; the store pages are covered by other mobile specs.
  test.skip(isMobile, 'Flujo del panel en escritorio');
  test.setTimeout(120_000);
  const session = adminSession();
  await context.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  const initial = JSON.parse(manage('shell', '-c', `import json; from apps.cms.models import Page; p=Page.objects.get(kind='personalize'); r=p.revisions.first(); print(json.dumps({'id':p.pk, 'revision':r.pk, 'es':r.snapshot['es']['faq']['items'][0]['question'], 'en':r.snapshot['en']['faq']['items'][0]['question']}))`).trim().split('\n').pop()!);
  const es = `¿Mi joya de prueba ${Date.now()}?`;
  const en = `My test jewel ${Date.now()}?`;
  const adminRoot = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  try {
    await page.goto(`${adminRoot}cms/page/${initial.id}/change/`);
    const esInput = page.locator('[name="faq_items-0-question_es"]');
    const enInput = page.locator('[name="faq_items-0-question_en"]');
    // Inline translations can be behind tabs; filling through DOM avoids depending on tab labels.
    await esInput.evaluate((element, value) => { (element as HTMLInputElement).value = value; element.dispatchEvent(new Event('input', { bubbles: true })); }, es);
    const originalEnDraft = await enInput.inputValue();
    expect(originalEnDraft).toBe(initial.en);
    await page.locator('[name="_save"]').click();
    for (const [path, original] of [['/es/personaliza', initial.es], ['/en/customize', initial.en]]) {
      await page.goto(path);
      await expect(page.locator('.faq-section summary').first()).toHaveText(original);
    }
    await page.goto(`${adminRoot}cms/page/${initial.id}/change/`);
    await page.getByRole('link', { name: 'Publicar', exact: true }).click();
    await page.getByRole('button', { name: 'Confirmar', exact: true }).click();
    for (const [path, question] of [['/es/personaliza', es], ['/en/customize', initial.en]]) {
      await page.goto(path);
      await expect(page.locator('.faq-section summary').first()).toHaveText(question);
    }
    // Changing English in a later save must retain the Spanish question.
    await page.goto(`${adminRoot}cms/page/${initial.id}/change/`);
    await page.locator('[name="faq_items-0-question_en"]').evaluate((element, value) => {
      (element as HTMLInputElement).value = value;
      element.dispatchEvent(new Event('input', { bubbles: true }));
    }, en);
    await page.locator('[name="_save"]').click();
    await page.goto(`${adminRoot}cms/page/${initial.id}/change/`);
    await page.getByRole('link', { name: 'Publicar', exact: true }).click();
    await page.getByRole('button', { name: 'Confirmar', exact: true }).click();
    for (const [path, question] of [['/es/personaliza', es], ['/en/customize', en]]) {
      await page.goto(path);
      await expect(page.locator('.faq-section summary').first()).toHaveText(question);
    }
    // The dashboard redirects to PUBLIC_SITE_URL (https://serti.localhost in dev, whose local CA the
    // test browser does not trust); follow the same signed preview link on the test origin instead.
    const issued = await page.request.get(`${adminRoot}cms/page/${initial.id}/preview/`, { maxRedirects: 0 });
    const previewLink = new URL(issued.headers()['location']);
    await page.goto(new URL(previewLink.pathname + previewLink.search, baseURL).toString());
    for (const path of ['/es/personaliza', '/en/customize']) {
      const response = await page.goto(path);
      expect(response!.headers()['cache-control']).toContain('no-store');
      expect(response!.headers()['x-robots-tag']).toBe('noindex, nofollow');
      expect(response!.headers()['referrer-policy']).toBe('no-referrer');
    }
  } finally {
    // Development stack only: restore the original published content after the scenario.
    manage('shell', '-c', `from apps.cms.models import PageRevision; from apps.cms.services import restore_page_revision,publish_page; from apps.accounts.models import User; r=PageRevision.objects.get(pk=${initial.revision}); u=User.objects.filter(is_staff=True,groups__name='Propietario').first(); restore_page_revision(r,u); publish_page(r.page,u)`);
  }
});
