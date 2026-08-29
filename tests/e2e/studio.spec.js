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

test('editorial theme preserves the supplied tokens and can be toggled', async ({ page }) => {
  await page.goto('/');
  const light = await page.locator('html').evaluate(element => {
    const style = getComputedStyle(element);
    return [style.getPropertyValue('--papel').trim(), style.getPropertyValue('--marca').trim(), style.getPropertyValue('--tinta').trim()];
  });
  expect(light).toEqual(['#f4efe4', '#7b5cff', '#141018']);

  const texture = await page.locator('body').evaluate(element => getComputedStyle(element).backgroundImage);
  expect(texture).toContain('radial-gradient');
  const card = await page.locator('.stat').first().evaluate(element => {
    const style = getComputedStyle(element);
    return [style.borderTopWidth, style.borderTopStyle, style.boxShadow];
  });
  expect(card[0]).toBe('2px');
  expect(card[1]).toBe('solid');
  expect(card[2]).toContain('rgb(123, 92, 255)');

  await page.getByRole('button', { name: /usar tema escuro/i }).click();
  const dark = await page.locator('html').evaluate(element => {
    const style = getComputedStyle(element);
    return [style.getPropertyValue('--papel').trim(), style.getPropertyValue('--marca').trim(), style.getPropertyValue('--tinta').trim()];
  });
  expect(dark).toEqual(['#141018', '#9c85ff', '#f4efe4']);
  await expect(page.getByRole('button', { name: /usar tema claro/i })).toHaveAttribute('aria-pressed', 'true');
});

test('direct library link stays anchored after asynchronous sections expand', async ({ page }) => {
  await page.goto('/#library');
  await page.waitForTimeout(2100);
  await expect(page.locator('#library')).toBeInViewport();
  await expect(page.getByRole('heading', { name: /biblioteca criativa/i })).toBeVisible();
  await expect(page.locator('#catalog-readiness')).toContainText(/lote piloto/i);
  await expect(page.locator('#catalog-readiness')).toContainText(/faixas lo-fi distintas/i);
  await expect(page.locator('#flow-music-guide')).toContainText(/Google Flow Music/i);
  await page.locator('#flow-music-guide details').click();
  await expect(page.locator('#flow-music-guide [data-copy-flow]')).toHaveCount(12);
  await page.getByRole('button', { name: /importar áudio baixado/i }).click();
  await expect(page.locator('#music-dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  const previews = page.locator('#music-grid audio source');
  if (await previews.count()) await expect(previews.first()).toHaveAttribute('src', /\/api\/music-assets\/\d+\/preview/);
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
  const job = {
    id: 'artifact-fixture', topic: 'Biblioteca noturna', profile: 'youtube_long', duration: 1800,
    status: 'awaiting_approval', progress: 100, quality_score: 100, events: [],
    metadata: {
      title: 'Biblioteca noturna — Lo-fi para foco', description: 'Pacote local validado.',
      files: { video: 'video.mp4', thumbnail: 'thumbnail.jpg' },
      verification: { passed: true, duration_seconds: 1800, size_bytes: 1024,
        video: { width: 1280, height: 720, codec: 'h264' }, audio: { codec: 'aac' } },
      quality: { warnings: [] },
    },
  };
  await page.route('**/api/dashboard', route => route.fulfill({ json: {
    summary: { total: 1, awaiting_approval: 1, in_progress: 0, average_quality: 100 },
    jobs: [job], recommendations: [], operation: { ok: true, free_gb: 10, queue: { active: [] } },
  } }));
  await page.route('**/api/jobs/artifact-fixture', route => route.fulfill({ json: job }));
  await page.route('**/api/jobs/artifact-fixture/artifacts/thumbnail.jpg', route =>
    route.fulfill({ status: 404, body: '' }));
  await page.route('**/api/jobs/artifact-fixture/artifacts/metadata.json', route => route.fulfill({ json: {
    title: job.metadata.title, duration: 1800,
    music: { style: 'licensed_music_library', track_name: 'Faixa original 01' },
    creative_fingerprint: { scene: 'biblioteca', motion_effect: 'chuva na janela', camera_motion: 'none' },
    quality_gate: { score: 100 },
  } }));
  await page.goto('/#production');
  const readyJob = page.locator('.production').filter({ has: page.locator('.status.awaiting_approval') }).first();
  await expect(readyJob).toBeVisible();
  await readyJob.getByRole('button', { name: /abrir detalhes/i }).click();
  await page.getByRole('button', { name: /resumo do vídeo/i }).click();
  await expect(page.locator('#artifact-dialog')).toBeVisible();
  await expect(page.locator('#artifact-detail')).toContainText(/leitura simplificada/i);
  await expect(page.locator('#artifact-detail pre')).toHaveCount(0);
});
