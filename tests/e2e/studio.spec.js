import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('studio loads, navigates and keeps dialogs keyboard-safe', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /direção clara/i })).toBeVisible();
  await expect(page.locator('#operation-title')).not.toHaveText('Verificando estúdio');

  await page.getByRole('link', { name: /produções/i }).click();
  await expect(page.locator('#production')).toBeInViewport();
  await page.getByRole('button', { name: /nova produção/i }).click();
  await expect(page.locator('#create-dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#create-dialog')).not.toBeVisible();
});

test('studio has no serious accessibility violations', async ({ page }) => {
  await page.goto('/');
  const results = await new AxeBuilder({ page }).disableRules(['color-contrast']).analyze();
  const serious = results.violations.filter(item => ['serious', 'critical'].includes(item.impact));
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});

test('mobile layout does not create horizontal overflow', async ({ page }) => {
  await page.goto('/#production');
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 1);
  await expect(page.getByRole('button', { name: /nova produção/i })).toBeVisible();
});

test('direct publishing link lands on the publishing center after data loads', async ({ page }) => {
  await page.goto('/#publishing');
  await expect(page.locator('#publishing')).toBeInViewport();
  await expect(page.getByRole('link', { name: /publicação/i })).toHaveAttribute('aria-current', 'page');
  await expect(page.locator('#publish-list')).not.toContainText(/\b(?:5|8|10|12|30)s\b/);
});
