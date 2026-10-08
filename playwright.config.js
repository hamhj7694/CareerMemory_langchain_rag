import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';

const runtimeRoot = process.env.E2E_RUNTIME_ROOT;
if (!runtimeRoot) {
  throw new Error('Playwright E2E는 npm run test:e2e로 실행해 격리 경로를 먼저 생성해야 합니다.');
}

const frontendPort = Number(process.env.E2E_FRONTEND_PORT || 14173);
const frontendUrl = `http://127.0.0.1:${frontendPort}`;
const configuredExecutable = process.env.PLAYWRIGHT_EXECUTABLE_PATH;
const windowsChrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const browserExecutable = configuredExecutable
  || (process.platform === 'win32' && existsSync(windowsChrome) ? windowsChrome : undefined);

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.js',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  outputDir: 'test-results/e2e-artifacts',
  use: {
    baseURL: frontendUrl,
    channel: browserExecutable ? undefined : (process.env.PLAYWRIGHT_CHANNEL || 'chrome'),
    launchOptions: browserExecutable ? { executablePath: browserExecutable } : {},
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Playwright 전용 FFmpeg를 설치하지 않은 개발 PC에서도 기본 E2E가 동작해야 한다.
    video: process.env.E2E_VIDEO === '1' ? 'retain-on-failure' : 'off',
  },
});
