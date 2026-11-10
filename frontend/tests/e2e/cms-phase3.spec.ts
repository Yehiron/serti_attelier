import { test, expect } from './fixtures';
import { adminSession, manage } from './support';

/** Dev only. Run serially against a migrated PostgreSQL stack with no pending Home draft. */
test('el registro publica Imagen con texto en ES/EN y conserva la tienda al limpiar', async ({ page, isMobile }) => {
  test.setTimeout(120_000);
  adminSession(); // creates an explicitly authorized development owner
  const initial = JSON.parse(manage('shell', '-c', `import json
from apps.cms.models import HomePublication
from apps.cms.publishing import pending_changes
p=HomePublication.objects.first()
assert p is not None, 'Publica el inicio antes de ejecutar la prueba'
assert pending_changes('home')['count']==0, 'Guarda o respalda los borradores antes de ejecutar la prueba'
print(json.dumps({'publication':p.pk}))`).trim().split('\n').pop()!);
  const tag = `Registro ${isMobile ? 'celular' : 'escritorio'} ${Date.now()}`;
  const en = `Registry ${isMobile ? 'mobile' : 'desktop'} ${Date.now()}`;
  try {
    manage('shell', '-c', `from django.conf import settings
assert settings.DEBUG, 'Solo desarrollo'
from apps.cms.models import HomeSection
from apps.cms.services import save_section,publish_home
from apps.cms.documents import get_document
from apps.accounts.models import User
u=User.objects.filter(is_staff=True,groups__name='Propietario').order_by('-pk').first()
p={'title':{'es':'${tag}','en':'${en}'},'body':{'es':'Una historia en tu joya.','en':'A story in your jewel.'},'image':{'src':'/brand/brand-leather.webp','srcset':'','width':1284,'height':2778,'alt':{'es':'Textura de cuero SERTI','en':'SERTI leather texture'}},'mobile_image':{'src':'/brand/logo/monogram-wine.webp','srcset':'','width':600,'height':600,'alt':{'es':'Monograma SERTI','en':'SERTI monogram'}},'image_position':'right','cta':{'kind':'personalize','label':{'es':'Crear mi joya','en':'Create my jewel'}}}
s=HomeSection(kind='image_text',props=p,position=10000)
save_section(s,actor=u,expected_version=get_document('home').draft_version)
publish_home(u,expected_version=get_document('home').draft_version)`);
    for (const [locale, title, action] of [['es', tag, 'Crear mi joya'], ['en', en, 'Create my jewel']]) {
      await page.goto(`/${locale}`);
      const section = page.locator('.cms-image-text').filter({ has: page.getByRole('heading', { name: title, exact: true }) });
      await section.scrollIntoViewIfNeeded();
      await expect(section).toBeVisible();
      await expect(section.getByRole('link', { name: action })).toHaveAttribute('href', locale === 'es' ? '/es/personaliza' : '/en/customize');
      const image = section.locator('img');
      await expect(image).toBeVisible();
      await expect.poll(() => image.evaluate(element => (element as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
      expect(await image.evaluate(element => (element as HTMLImageElement).currentSrc)).toContain(isMobile ? 'monogram-wine.webp' : 'brand-leather.webp');
      const box = await section.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
      await section.screenshot({ path: test.info().outputPath(`imagen-texto-${locale}.png`) });
    }
  } finally {
    manage('shell', '-c', `from django.conf import settings
assert settings.DEBUG
from apps.cms.models import HomePublication
from apps.cms.services import restore_home,publish_home
from apps.cms.documents import get_document
from apps.accounts.models import User
u=User.objects.filter(is_staff=True,groups__name='Propietario').order_by('-pk').first()
p=HomePublication.objects.get(pk=${initial.publication})
restore_home(p,u,expected_version=get_document('home').draft_version)
publish_home(u,expected_version=get_document('home').draft_version)`);
    await page.goto('/es');
    await expect(page.getByRole('heading', { name: tag, exact: true })).toHaveCount(0);
  }
});
