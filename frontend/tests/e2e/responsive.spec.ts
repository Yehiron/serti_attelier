import { expect, test } from './fixtures';

for (const width of [320, 360, 390, 414]) {
  test(`las páginas públicas caben en ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 740 });
    await page.goto('/es/joyeria');
    await expect(page.locator('main.listing-page')).toBeVisible();
    const paths = ['/es', '/es/joyeria', '/es/buscar?q=anillo', '/es/contacto', '/es/historia', '/es/personaliza', '/es/deseos', '/es/carrito', '/es/checkout', '/es/legal/terminos', '/es/no-existe'];
    for (const prefix of ['/es/piezas/', '/es/colecciones/', '/es/piedras/']) {
      const link = page.locator(`a[href^="${prefix}"]`).first();
      await expect(link).toHaveCount(1);
      paths.push((await link.getAttribute('href'))!);
    }
    for (const path of paths) {
      await page.goto(path, { waitUntil: 'networkidle' });
      // Next 16 keeps previously visited routes hidden in the DOM (Activity).
      await expect(page.locator('main:visible')).toBeVisible();
      await page.evaluate(async () => {
        for (let y = 0; y < document.documentElement.scrollHeight; y += window.innerHeight) {
          window.scrollTo({ top: y, behavior: 'instant' });
          await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
        }
      });
      const dimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
      expect(dimensions.scroll, path).toBeLessThanOrEqual(dimensions.client);
    }
  });
}

for (const [width, height] of [[1440, 900], [1366, 768], [1280, 720], [390, 844], [390, 664], [360, 740]] as const) {
  test(`el hero ocupa la primera pantalla en ${width}×${height}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto('/es');
    const hero = page.locator('.home-page .hero').first();
    await expect(hero).toBeVisible();
    await expect.poll(() => hero.evaluate(el => Math.abs(el.getBoundingClientRect().bottom - window.innerHeight))).toBeLessThanOrEqual(2);
    const indicators = hero.locator('.hero-indicators button:visible');
    await expect(indicators.first()).toBeVisible();
    const boxes = await indicators.evaluateAll(buttons => buttons.map(button => ({ top: button.getBoundingClientRect().top, width: button.getBoundingClientRect().width, height: button.getBoundingClientRect().height })));
    expect(new Set(boxes.map(box => box.top)).size).toBe(1);
    expect(boxes.every(box => box.width >= 24 && box.height >= 24)).toBe(true);
    const whatsapp = page.locator('.floating-whatsapp:visible');
    if (await whatsapp.count()) {
      const last = await indicators.last().boundingBox();
      const floating = await whatsapp.boundingBox();
      expect(last!.x + last!.width <= floating!.x || last!.y + last!.height <= floating!.y || floating!.y + floating!.height <= last!.y).toBe(true);
    }
  });
}

test('la navegación desde abajo llega arriba sin desplazamiento animado', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/es');
  const link = page.locator('footer a[href^="/es/legal/"]:visible').first();
  await expect(link).toBeVisible();
  await link.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  await page.evaluate(() => {
    const samples: { path: string; y: number; time: number }[] = [];
    Object.assign(window, { responsiveScrollSamples: samples });
    const sample = () => { samples.push({ path: location.pathname, y: window.scrollY, time: performance.now() }); requestAnimationFrame(sample); };
    requestAnimationFrame(sample);
  });
  await link.click();
  const target = await link.getAttribute('href');
  await expect(page).toHaveURL(new RegExp(`${target}$`));
  await expect(page.locator('main:visible')).toBeVisible();
  await page.waitForTimeout(500);
  const samples = await page.evaluate(() => (window as unknown as { responsiveScrollSamples: { path: string; y: number; time: number }[] }).responsiveScrollSamples);
  const destination = samples.filter(sample => sample.path === target);
  expect(destination.length).toBeGreaterThan(0);
  expect(destination.every(sample => sample.y === 0)).toBe(true);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});


test('atrás restaura el scroll de la portada', async ({ page }) => {
  await page.goto('/es');
  const link = page.locator('footer a[href^="/es/legal/"]:visible').first();
  await link.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  const target = await link.getAttribute('href');
  await link.click();
  await expect(page).toHaveURL(new RegExp(`${target}$`));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await page.goBack();
  await expect(page).toHaveURL(/\/es$/);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
});
