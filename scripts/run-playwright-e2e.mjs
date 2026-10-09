import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdirSync, rmSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const runtimeParent = path.join(repoRoot, 'data', 'playwright-e2e');
const runtimeRoot = path.join(
  runtimeParent,
  `run-${process.pid}-${Date.now()}`,
);
const playwrightCli = require.resolve('@playwright/test/cli');
const viteCli = path.join(repoRoot, 'node_modules', 'vite', 'bin', 'vite.js');
const backendPort = Number(process.env.E2E_BACKEND_PORT || 18100);
const frontendPort = Number(process.env.E2E_FRONTEND_PORT || 14173);
const backendUrl = `http://127.0.0.1:${backendPort}`;
const frontendUrl = `http://127.0.0.1:${frontendPort}`;
const sqlitePath = path.join(runtimeRoot, 'career-memory-e2e.db').replaceAll('\\', '/');
const pythonCommand = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

mkdirSync(runtimeRoot, { recursive: true });

const backend = spawn(
  pythonCommand,
  ['-m', 'uvicorn', 'e2e.support.e2e_server:app', '--host', '127.0.0.1', '--port', String(backendPort)],
  {
    cwd: repoRoot,
    env: {
      ...process.env,
      APP_ENV: 'development',
      DATABASE_URL: `sqlite:///${sqlitePath}`,
      ATTACHMENT_STORAGE_ROOT: path.join(runtimeRoot, 'attachments'),
      AI_EXPERIENCE_VECTOR_ROOT: path.join(runtimeRoot, 'vectors', 'experiences'),
      AI_EVIDENCE_VECTOR_ROOT: path.join(runtimeRoot, 'vectors', 'evidence'),
      E2E_AI_MODE: process.env.E2E_AI_MODE || 'stub',
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['ignore', 'inherit', 'inherit'],
    windowsHide: true,
  },
);

const frontend = spawn(
  process.execPath,
  [viteCli, '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort'],
  {
    cwd: repoRoot,
    env: {
      ...process.env,
      VITE_USE_MOCK: 'false',
      VITE_API_BASE_URL: 'same-origin',
      VITE_PROXY_TARGET: backendUrl,
    },
    stdio: ['ignore', 'inherit', 'inherit'],
    windowsHide: true,
  },
);

async function waitForUrl(url, label) {
  let lastError = '';
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`${label} 준비 시간 초과: ${lastError}`);
}

function runPlaywright() {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [playwrightCli, 'test', ...process.argv.slice(2)],
      {
        cwd: repoRoot,
        env: {
          ...process.env,
          E2E_RUNTIME_ROOT: runtimeRoot,
          E2E_BACKEND_PORT: String(backendPort),
          E2E_FRONTEND_PORT: String(frontendPort),
        },
        stdio: 'inherit',
        windowsHide: true,
      },
    );
    child.once('error', reject);
    child.once('close', (code) => resolve(code ?? 1));
  });
}

async function stopProcess(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  child.kill();
  await Promise.race([
    new Promise((resolve) => child.once('close', resolve)),
    new Promise((resolve) => setTimeout(resolve, 3_000)),
  ]);
  if (child.exitCode === null && child.signalCode === null && process.platform === 'win32') {
    spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {
      windowsHide: true,
      stdio: 'ignore',
    });
  }
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, () => {
    backend.kill();
    frontend.kill();
  });
}

let exitCode = 1;
try {
  await waitForUrl(`${backendUrl}/health`, '백엔드');
  await waitForUrl(frontendUrl, '프론트엔드');
  exitCode = await runPlaywright();
} finally {
  await Promise.all([stopProcess(frontend), stopProcess(backend)]);
}

const resolvedParent = `${path.resolve(runtimeParent)}${path.sep}`;
const resolvedRuntime = path.resolve(runtimeRoot);
if (
  resolvedRuntime.startsWith(resolvedParent)
  && path.basename(resolvedRuntime).startsWith('run-')
) {
  rmSync(resolvedRuntime, {
    recursive: true,
    force: true,
    maxRetries: 5,
    retryDelay: 200,
  });
}

process.exitCode = exitCode;
