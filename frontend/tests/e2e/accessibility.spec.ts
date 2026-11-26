import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './fixtures';
import { createPiece } from './support';

test.use({ reducedMotion: 'reduce' });

// WCAG 2.2 AA target (docs/ux-ui-plan.md): no serious or critical axe violations.
const pages = ['/es', '/es/joyeria', '/es/personaliza', '/es/contacto', '/es/legal/terminos', '/es/deseos', '/es/carrito'];

for (const path of pages) {
  test(`no serious accessibility violations on ${path}`, async ({ page }) => {
    await page.goto(path);
    await page.locator('main').first().waitFor();
    // Next streams metadata after the content when it depends on API data.
    await expect(page).toHaveTitle(/SERTI/);
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    const blocking = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
    expect(blocking.map((v) => `${v.id}: ${v.nodes.length} × ${v.help}`)).toEqual([]);
  });
}

test('no serious accessibility violations on a piece page', async ({ page }) => {
  const piece = createPiece();
  await page.goto(`/es/piezas/${piece.slug_es}`);
  await expect(page).toHaveTitle(/SERTI/);
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
  const blocking = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  expect(blocking.map((v) => `${v.id}: ${v.nodes.length} × ${v.help}`)).toEqual([]);
});
