import { expect, test } from './fixtures';
import { createPiece } from './support';

test('reduced motion mantiene las secciones y tarjetas visibles de inmediato', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/es');
  await expect(page.locator('html')).toHaveClass(/motion-ready/);
  const sections = page.locator('.home-page > section');
  expect(await sections.count()).toBeGreaterThan(1);
  for (const section of await sections.all()) {
    await expect(section).toHaveCSS('opacity', '1');
    await expect(section).toHaveCSS('transform', 'none');
  }
  await expect(page.locator('.motion-pending')).toHaveCount(0);
  await expect(page.locator('.hero-copy .title-reveal')).toHaveCSS('animation-name', 'none');
  await expect(page.locator('.hero-slide.is-current:visible').first()).toHaveCSS('transform', 'none');
  await page.goto('/es/joyeria');
  await expect(page.locator('.piece-card').first()).toBeVisible();
  for (const card of await page.locator('.piece-card').all()) {
    await expect(card).toHaveCSS('opacity', '1');
    await expect(card).toHaveCSS('transform', 'none');
  }
});

test('las secciones terminan visibles después de entrar al viewport', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/es');
  await expect(page.locator('html')).toHaveClass(/motion-ready/);
  const sections = page.locator('.home-page [data-scroll-reveal]');
  expect(await sections.count()).toBeGreaterThan(0);
  for (const section of await sections.all()) {
    await section.scrollIntoViewIfNeeded();
    await expect(section).toHaveCSS('opacity', '1');
    await expect(section).toHaveCSS('transform', 'none');
  }
});

test.describe('fotos táctiles a 390px', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  test('deslizar cambia la foto, conserva los puntos y el tap abre la ficha', async ({ page }) => {
    const piece = createPiece({ hover: true });
    await page.goto(`/es/buscar?q=${encodeURIComponent(piece.name)}`);
    const card = page.locator('.piece-card', { hasText: piece.name });
    const photo = card.locator('.piece-photo-link');
    const dots = card.locator('.piece-photo-dots > span');
    await expect(dots).toHaveCount(2);
    await expect(card.locator('.piece-photo-dots')).toBeVisible();
    await photo.scrollIntoViewIfNeeded();
    const box = (await photo.boundingBox())!;
    const session = await page.context().newCDPSession(page);
    const y = box.y + box.height / 2;
    await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: box.x + box.width * .85, y }] });
    for (let step = 1; step <= 8; step++) {
      await session.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: box.x + box.width * (.85 - step * .09), y }] });
      await page.waitForTimeout(25);
    }
    await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await session.detach();
    await expect(dots.nth(1)).toHaveAttribute('data-current', 'true');
    await expect.poll(() => photo.evaluate(el => el.scrollLeft / el.clientWidth)).toBeGreaterThan(.95);
    await expect(page).toHaveURL(/\/es\/buscar/);
    const dimensions = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    expect(dimensions[0]).toBeLessThanOrEqual(dimensions[1]);
    const target = (await photo.getAttribute('href'))!;
    await photo.tap();
    await expect(page).toHaveURL(new RegExp(`${target}$`));
  });
});
