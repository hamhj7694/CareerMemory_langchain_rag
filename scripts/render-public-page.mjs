import dns from 'node:dns/promises';
import { existsSync } from 'node:fs';
import net from 'node:net';
import process from 'node:process';
import { chromium } from '@playwright/test';

const inputUrl = process.argv[2];
const timeoutMs = Math.max(5_000, Number(process.env.WEB_FETCH_TIMEOUT_SECONDS || 15) * 1_000);
const maxHtmlBytes = Math.max(1, Number(process.env.WEB_FETCH_MAX_MIB || 15)) * 1024 * 1024;
const executableCandidates = [
  process.env.PLAYWRIGHT_EXECUTABLE_PATH,
  process.platform === 'win32' ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' : '',
  process.platform === 'win32' ? 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe' : '',
  process.platform === 'linux' ? '/usr/bin/google-chrome' : '',
  process.platform === 'linux' ? '/usr/bin/chromium' : '',
].filter(Boolean);
const browserExecutable = executableCandidates.find((candidate) => existsSync(candidate));

function isPrivateAddress(address) {
  if (net.isIPv4(address)) {
    const parts = address.split('.').map(Number);
    return parts[0] === 10
      || parts[0] === 127
      || (parts[0] === 100 && parts[1] >= 64 && parts[1] <= 127)
      || (parts[0] === 169 && parts[1] === 254)
      || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31)
      || (parts[0] === 192 && parts[1] === 168)
      || (parts[0] === 192 && parts[1] === 0 && parts[2] === 0)
      || (parts[0] === 192 && parts[1] === 0 && parts[2] === 2)
      || (parts[0] === 198 && [18, 19].includes(parts[1]))
      || (parts[0] === 198 && parts[1] === 51 && parts[2] === 100)
      || (parts[0] === 203 && parts[1] === 0 && parts[2] === 113)
      || parts[0] === 0
      || parts[0] >= 224;
  }
  if (net.isIPv6(address)) {
    const value = address.toLowerCase();
    if (value.startsWith('::ffff:')) return isPrivateAddress(value.slice(7));
    return value === '::1'
      || value === '::'
      || value.startsWith('fc')
      || value.startsWith('fd')
      || value.startsWith('fe8')
      || value.startsWith('fe9')
      || value.startsWith('fea')
      || value.startsWith('feb')
      || value.startsWith('ff')
      || value.startsWith('2001:db8');
  }
  return true;
}

async function isPublicHttpUrl(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return false;
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) return false;
  if (parsed.username || parsed.password) return false;
  if (parsed.port && !['80', '443'].includes(parsed.port)) return false;
  const hostname = parsed.hostname.toLowerCase().replace(/\.$/, '');
  if (hostname === 'localhost' || hostname.endsWith('.local') || hostname.endsWith('.internal')) return false;
  try {
    const addresses = await dns.lookup(hostname, { all: true, verbatim: true });
    return addresses.length > 0 && addresses.every(({ address }) => !isPrivateAddress(address));
  } catch {
    return false;
  }
}

if (!inputUrl || !(await isPublicHttpUrl(inputUrl))) {
  process.stderr.write('Unsafe or invalid URL.');
  process.exit(2);
}

let browser;
try {
  browser = await chromium.launch({
    headless: true,
    ...(browserExecutable ? { executablePath: browserExecutable } : {}),
  });
  const context = await browser.newContext({
    acceptDownloads: false,
    serviceWorkers: 'block',
    userAgent: 'CareerMemory/1.0 (+user-requested public page reader)',
  });
  await context.route('**/*', async (route) => {
    const allowed = await isPublicHttpUrl(route.request().url());
    if (allowed) await route.continue();
    else await route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  await page.goto(inputUrl, { waitUntil: 'domcontentloaded', timeout: timeoutMs });
  await page.waitForLoadState('networkidle', { timeout: Math.min(5_000, timeoutMs) }).catch(() => {});
  const payload = {
    url: page.url(),
    title: await page.title(),
    html: await page.content(),
  };
  if (Buffer.byteLength(payload.html, 'utf8') > maxHtmlBytes) {
    throw new Error('Rendered page is too large.');
  }
  process.stdout.write(JSON.stringify(payload));
  await context.close();
} catch (error) {
  process.stderr.write(String(error?.message || error));
  process.exitCode = 1;
} finally {
  await browser?.close();
}
