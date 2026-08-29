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

test('public production only offers 30 or 60 minutes and opens the music library', async ({ page }) => {
  await page.goto('/#production');
  await page.getByRole('button', { name: /nova produção/i }).click();
  const durations = await page.locator('#generate-form [name=duration] option').evaluateAll(
    options => options.map(option => option.value),
  );
  expect(durations).toEqual(['3600', '1800']);
  await expect(page.locator('#profiles input')).toHaveCount(1);
  await expect(page.locator('#profiles input')).toHaveAttribute('value', 'youtube_long');
  await page.keyboard.press('Escape');

  await page.getByRole('link', { name: /biblioteca/i }).click();
  await page.getByRole('button', { name: /importar músicas/i }).click();
  await expect(page.locator('#music-dialog')).toBeVisible();
  await expect(page.locator('#music-form [name=path]')).toBeEditable();
});

test('technical artifacts open as a readable summary instead of raw JSON', async ({ page }) => {
  await page.goto('/#production');
  const readyJob = page.locator('.production').filter({ has: page.locator('.status.awaiting_approval') }).first();
  await expect(readyJob).toBeVisible();
  await readyJob.getByRole('button', { name: /abrir detalhes/i }).click();
  await page.getByRole('button', { name: /resumo do vídeo/i }).click();
  await expect(page.locator('#artifact-dialog')).toBeVisible();
  await expect(page.locator('#artifact-detail')).toContainText(/leitura simplificada/i);
  await expect(page.locator('#artifact-detail pre')).toHaveCount(0);
});
