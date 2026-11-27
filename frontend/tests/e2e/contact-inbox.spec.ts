import { expect, test } from './fixtures';
import { adminSession, manage } from './support';

test('bandeja de contacto permite preparar y registrar una respuesta', async ({ page, context, baseURL }) => {
  const session = adminSession();
  const root = session.admin_url.split('/orders/')[0].replace(/\/?$/, '/');
  await context.addCookies([{ name: session.name, value: session.value, url: baseURL! }]);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const tag = Date.now();
  const output = manage('shell', '-c', `from apps.inquiries.models import ContactInquiry; x=ContactInquiry.objects.create(name='E2E ${tag}', email='contact.${tag}@e2e.invalid', phone='3001234567', topic='piece', message='Hola, quiero conocer esta hermosa pieza', preferred_channel='whatsapp', privacy_version=1, locale='es'); print(x.pk)`);
  const id = output.trim().split('\n').pop();
  await page.goto(`${root}inquiries/contactinquiry/?bandeja=all&mensaje=${id}`);
  await expect(page.getByRole('heading', { name: `E2E ${tag}` })).toBeVisible();
  await page.getByRole('button', { name: 'Gracias por escribir' }).click();
  const text = await page.locator('#msg-reply').inputValue();
  expect(decodeURIComponent((await page.locator('#msg-whatsapp').getAttribute('href'))!)).toContain(text);
  expect(decodeURIComponent((await page.locator('#msg-email').getAttribute('href'))!)).toContain(text);
  await page.getByRole('button', { name: 'Marcar como respondido' }).click();
  await page.getByRole('link', { name: /Respondidos/ }).click();
  await expect(page.getByText(`E2E ${tag}`).first()).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});
