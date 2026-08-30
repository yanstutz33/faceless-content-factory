import { defineConfig, devices } from '@playwright/test';
import { existsSync } from 'node:fs';

const studioCommand = process.platform === 'win32' && existsSync('.\\.venv\\Scripts\\python.exe')
  ? '.\\.venv\\Scripts\\python.exe app.py serve'
  : 'python app.py serve';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  fullyParallel: false,
  retries: 1,
  reporter: 'line',
  use: {
    baseURL: 'http://127.0.0.1:8787',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop-chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'] } },
  ],
  webServer: {
    command: studioCommand,
    url: 'http://127.0.0.1:8787/api/health',
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
