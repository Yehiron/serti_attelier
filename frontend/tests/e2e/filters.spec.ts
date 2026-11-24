import { expect, test, type Locator, type Page } from './fixtures';

/** The filter panel, unfolded from its capsule. */
async function filters(page: Page): Promise<Locator> {
  await page.goto('/es/joyeria');
  await expect(page.locator('main.listing-page')).toBeVisible();
  const panel = page.locator('details.filter-panel');
  await panel.locator('summary.filter-pill').click();
  await expect(panel).toHaveAttribute('open', '');
  return panel;
}

test('the filter capsule opens the panel and closes it on a second tap', async ({ page }) => {
  const panel = await filters(page);
  const pill = panel.locator('summary.filter-pill');
  await expect(panel.locator('.filter-form')).toBeVisible();
  await pill.click();
  await expect(panel).not.toHaveAttribute('open', '');
  await expect(panel.locator('.filter-form')).toBeHidden();
});

const row = (form: Locator, name: string) => form.locator('.filter-select', { hasText: name });

test('filter lists unfold in place, one at a time, and submit the chosen value', async ({ page }) => {
  const form = await filters(page);
  const category = row(form, 'Categoría');
  await expect(async () => {
    await category.locator('button').click();
    await expect(category.getByRole('listbox')).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 15_000 });
  await row(form, 'Material').locator('button').click();
  await expect(category.getByRole('listbox')).toBeHidden();
  await expect(row(form, 'Material').getByRole('listbox')).toBeVisible();
  await category.locator('button').click();
  await category.getByRole('option', { name: 'Anillos', exact: true }).click();
  await expect(category.locator('button')).toHaveText('Anillos');
  await expect(category.getByRole('listbox')).toBeHidden();
  await form.getByRole('button', { name: 'Aplicar filtros' }).click();
  await expect(page).toHaveURL(/category=anillos/);
});

test('filter lists work with the keyboard', async ({ page, isMobile }) => {
  test.skip(isMobile, 'Keyboard navigation is a desktop concern');
  const form = await filters(page);
  const sort = row(form, 'Ordenar').locator('button');
  await expect(async () => {
    await sort.focus();
    await page.keyboard.press('Enter');
    await expect(row(form, 'Ordenar').getByRole('listbox')).toBeFocused({ timeout: 1000 });
  }).toPass({ timeout: 15_000 });
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(sort).toHaveText(/mayor a menor/);
  await expect(sort).toBeFocused();
  await page.keyboard.press('Enter');
  await page.keyboard.press('Escape');
  await expect(row(form, 'Ordenar').getByRole('listbox')).toBeHidden();
});

test('the price slider filters in pesos and an untouched slider adds nothing', async ({ page }) => {
  const form = await filters(page);
  await form.getByRole('button', { name: 'Aplicar filtros' }).click();
  await expect(page).not.toHaveURL(/price_m(in|ax)/);
  const again = await filters(page);
  const [lo, hi] = [again.locator('.price-slider input').first(), again.locator('.price-slider input').last()];
  await expect(async () => {
    await lo.focus();
    await page.keyboard.press('ArrowRight');
    await expect(lo).not.toHaveValue(await lo.getAttribute('min') ?? '', { timeout: 1000 });
  }).toPass({ timeout: 15_000 });
  await hi.focus();
  await page.keyboard.press('ArrowLeft');
  const [min, max] = [Number(await lo.inputValue()), Number(await hi.inputValue())];
  expect(min % 50_000).toBe(0);
  expect(max % 50_000).toBe(0);
  await again.getByRole('button', { name: 'Aplicar filtros' }).click();
  await expect(page).toHaveURL(new RegExp(`price_min=${min}&price_max=${max}`));
  // Chips and the slider read pesos back, never the API's cents.
  await expect(page.locator('.active-filters')).toContainText(`Desde $ ${min.toLocaleString('es-CO')}`);
});
