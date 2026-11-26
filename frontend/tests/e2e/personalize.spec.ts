import { test, expect } from './fixtures';

test('arma una idea y la prepara para WhatsApp', async ({ page }) => {
  await page.goto('/es/personaliza');
  const main = page.locator('main:visible');
  await expect(main.getByRole('heading', { level: 1, name: /Diseña la tuya/ })).toBeVisible();
  await expect(main.locator('.customize-timeline li')).toHaveCount(4);
  await expect(main.getByRole('heading', { name: 'Arma tu idea' })).toBeVisible();
  // The radio sits under its card, so pick it the way a visitor does: tapping the card.
  await main.locator('.customize-choice', { hasText: 'Aretes' }).click();
  await main.locator('.customize-choice', { hasText: 'Rubí' }).click();
  await expect(main.getByRole('radio', { name: 'Aretes' })).toBeChecked();
  await expect(main.locator('.customize-summary h3')).toHaveText(/aretes con rubí/i);
  const link = main.getByRole('link', { name: 'Enviar mi idea por WhatsApp' });
  await expect(link).toHaveAttribute('href', /aretes%20con%20rub%C3%AD/i);
  await expect(main.locator('.customize-faq')).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
