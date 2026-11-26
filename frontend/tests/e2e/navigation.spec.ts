import { expect, test, type Locator, type Page } from './fixtures';
import { createPiece } from './support';

const openMenus = (scope: Locator) => scope.locator('details[open] > summary');

/** The desktop nav, or the mobile dialog after opening it (a tap before hydration is lost). */
async function navigation(page: Page): Promise<Locator> {
  await page.goto('/es');
  // The header streams in after the shell; decide desktop/mobile only once it is there.
  await expect(page.locator('.site-header .utilities')).toBeVisible();
  const trigger = page.locator('.menu-trigger');
  if (!(await trigger.isVisible())) return page.locator('nav.desktop-nav');
  const dialog = page.locator('dialog.menu-dialog');
  await expect(async () => {
    await trigger.click();
    await expect(dialog).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 15_000 });
  return dialog;
}

test('only one main menu is open at a time', async ({ page }) => {
  const nav = await navigation(page);
  const jewelry = nav.locator('summary', { hasText: 'Joyería' });
  const stones = nav.locator('summary', { hasText: 'Piedras' });
  await expect(async () => {
    await jewelry.click();
    await expect(openMenus(nav)).toHaveText(['Joyería'], { timeout: 1000 });
  }).toPass({ timeout: 15_000 });
  await stones.click();
  await expect(openMenus(nav)).toHaveText(['Piedras']);
  // Pressing the active one again closes it.
  await stones.click();
  await expect(openMenus(nav)).toHaveCount(0);
});

test('desktop menus close on outside click, Escape and navigation', async ({ page }) => {
  const nav = await navigation(page);
  test.skip(!(await nav.evaluate(el => el.matches('.desktop-nav'))), 'Desktop navigation only');
  const jewelry = nav.locator('summary', { hasText: 'Joyería' });
  await expect(async () => {
    await jewelry.click();
    await expect(openMenus(nav)).toHaveCount(1, { timeout: 1000 });
  }).toPass({ timeout: 15_000 });
  await page.locator('main').click({ position: { x: 5, y: 300 } });
  await expect(openMenus(nav)).toHaveCount(0);

  await jewelry.focus();
  await page.keyboard.press('Enter');
  await expect(openMenus(nav)).toHaveCount(1);
  await page.keyboard.press('Escape');
  await expect(openMenus(nav)).toHaveCount(0);
  await expect(jewelry).toBeFocused();

  await page.keyboard.press('Enter');
  await nav.getByRole('link', { name: 'Ver todas' }).click();
  await expect(page).toHaveURL(/\/es\/joyeria$/);
  await expect(openMenus(nav)).toHaveCount(0);
});

test('mobile menu: Escape closes the dialog and its open submenu', async ({ page }) => {
  const nav = await navigation(page);
  test.skip(!(await nav.evaluate(el => el.matches('dialog'))), 'Mobile navigation only');
  await nav.locator('summary', { hasText: 'Piedras' }).click();
  await expect(openMenus(nav)).toHaveText(['Piedras']);
  await page.keyboard.press('Escape');
  await expect(nav).toBeHidden();
  await expect(openMenus(nav)).toHaveCount(0);
});

test('product card supports desktop hover and mobile photo scrolling', async ({ page, isMobile }) => {
  const withHover = createPiece({ hover: true });
  const plain = createPiece();
  // Search by each unique name: earlier runs leave many E2E pieces in the catalog.
  await page.goto(`/es/buscar?q=${encodeURIComponent(plain.name)}`);
  const plainCard = page.locator('.piece-card', { hasText: plain.name });
  await expect(plainCard).toBeVisible();
  await expect(plainCard.locator('.hover-image')).toHaveCount(0);
  await page.goto(`/es/buscar?q=${encodeURIComponent(withHover.name)}`);
  const card = page.locator('.piece-card', { hasText: withHover.name });
  await expect(card).toBeVisible();
  const alternate = card.locator('.hover-image');
  await expect(alternate).toHaveAttribute('alt', '');
  if (isMobile) {
    await expect(card.locator('.piece-photo-dots > span')).toHaveCount(2);
    await expect(card.locator('.piece-photo-dots')).toBeVisible();
    await expect(alternate).toHaveCSS('opacity', '1');
    return;
  }
  await expect(alternate).toHaveCSS('opacity', '0');
  await card.locator('.piece-photo').hover();
  await expect(alternate).toHaveCSS('opacity', '1');
  await page.mouse.move(0, 0);
  await expect(alternate).toHaveCSS('opacity', '0');
  // Same layout box for both photos (the zoom is a transform): no layout shift when swapping.
  const layout = (el: HTMLElement) => [el.offsetLeft, el.offsetTop, el.offsetWidth, el.offsetHeight];
  const [primary, secondary] = await Promise.all([card.locator('.piece-photo img').first().evaluate(layout), alternate.evaluate(layout)]);
  expect(secondary).toEqual(primary);
});

test('el logo lleva al principio de la portada', async ({ page }) => {
  await page.goto('/es', { waitUntil: 'networkidle' });
  // Retry until the streamed page is tall enough to scroll.
  await expect.poll(() => page.evaluate(() => { window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' }); return window.scrollY; })).toBeGreaterThan(0);
  await page.locator('a.brand-link:visible').first().click();
  await expect(page).toHaveURL(/\/es$/);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await page.goto('/es/joyeria', { waitUntil: 'networkidle' });
  await expect.poll(() => page.evaluate(() => { window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' }); return window.scrollY; })).toBeGreaterThan(0);
  await page.locator('a.brand-link:visible').first().click();
  await expect(page).toHaveURL(/\/es$/);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
});
