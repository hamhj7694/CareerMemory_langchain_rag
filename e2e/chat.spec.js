import { expect, test } from '@playwright/test';

const account = {
  identifier: 'e2e_browser',
  pin: '246810',
  display_name: 'E2E 브라우저',
  recovery_question: 'recovery_keyword',
  recovery_answer: 'e2e recovery answer',
};

async function login(page) {
  const browserErrors = [];
  page.on('pageerror', (error) => browserErrors.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') browserErrors.push(`console: ${message.text()}`);
  });
  page.on('requestfailed', (request) => {
    browserErrors.push(`requestfailed: ${request.url()} (${request.failure()?.errorText})`);
  });
  const response = await page.goto('/start', { waitUntil: 'domcontentloaded' });
  const username = page.getByLabel('간단 아이디', { exact: true });
  try {
    await expect(username).toBeVisible({ timeout: 10_000 });
  } catch (error) {
    throw new Error([
      `시작 화면을 렌더링하지 못했습니다: ${page.url()} (HTTP ${response?.status()})`,
      ...browserErrors,
      `body: ${(await page.locator('body').innerHTML()).slice(0, 1000)}`,
      `cause: ${error.message}`,
    ].join('\n'), { cause: error });
  }
  await username.fill(account.identifier);
  await page.getByLabel('PIN', { exact: true }).fill(account.pin);
  await Promise.all([
    page.waitForURL(/\/chat(?:\/|$)/),
    page.getByRole('button', { name: '내 기록으로 시작하기', exact: true }).click(),
  ]);
  await expect(page.getByRole('heading', { name: 'Career Memory와 대화하기' })).toBeVisible();
}

async function startNewConversation(page) {
  const attachmentButton = page.getByRole('button', { name: '파일 첨부' });
  await expect(attachmentButton).toBeEnabled({ timeout: 30_000 });
  const newConversation = page.getByRole('button', { name: '새 대화', exact: true });
  if (await newConversation.count()) {
    await newConversation.first().click();
  }
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.locator('textarea')).toBeVisible();
  await expect(attachmentButton).toBeEnabled({ timeout: 30_000 });
}

async function waitForReadyAttachment(page, filename) {
  const card = page.locator('.v2-attachments > li').filter({ hasText: filename });
  await expect(card).toContainText('분석 준비 완료', { timeout: 30_000 });
  return card;
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ request }) => {
  const response = await request.post('/api/v2/auth/simple', { data: account });
  expect(response.status()).toBe(200);
});

test.beforeEach(async ({ page }) => {
  await login(page);
});

test('간단 아이디로 시작한 뒤 채팅 스트리밍과 새로고침 복원이 동작한다', async ({ page }) => {
  await startNewConversation(page);
  const prompt = 'E2E 상태 확인입니다.';

  await page.locator('textarea').fill(prompt);
  await page.getByRole('button', { name: '메시지 보내기' }).click();

  await expect(page.locator('.v2-message--user').last()).toContainText(prompt);
  await expect(page.locator('.v2-message--assistant').last()).toContainText('채팅 응답 정상');
  await expect(page).toHaveURL(/\/chat\/CONV-/);

  await page.reload();
  await expect(page.locator('.v2-message--user').last()).toContainText(prompt);
  await expect(page.locator('.v2-message--assistant').last()).toContainText('채팅 응답 정상');
});

test('답변 생성 중 추가 메시지를 보내면 이전 답변을 취소하고 사용자 문장을 합친다', async ({ page }) => {
  await startNewConversation(page);
  const textarea = page.locator('textarea');
  const sendButton = page.getByRole('button', { name: '메시지 보내기' });

  await textarea.fill('안녕 나는 함');
  await sendButton.click();
  await expect(page.locator('.v2-message--user')).toHaveCount(1);

  await expect(textarea).toBeEnabled();
  await textarea.fill('형준이야.');
  await expect(sendButton).toBeEnabled();
  await sendButton.click();

  await expect(page.locator('.v2-message--user')).toHaveCount(2);
  await expect(page.locator('.v2-message--assistant')).toHaveCount(1);
  await expect(page.locator('.v2-message--assistant').last()).toContainText(
    '통합 프롬프트 확인: 안녕 나는 함형준이야.',
  );

  await page.reload();
  await expect(page.locator('.v2-message--user')).toHaveCount(2);
  await expect(page.locator('.v2-message--assistant')).toHaveCount(1);
  await expect(page.locator('.v2-message--assistant').last()).toContainText(
    '통합 프롬프트 확인: 안녕 나는 함형준이야.',
  );
});

test('사용자 말풍선의 텍스트를 마우스 드래그로 선택할 수 있다', async ({ page }) => {
  await startNewConversation(page);
  const prompt = '드래그해서 복사할 수 있는 사용자 메시지입니다.';

  await page.locator('textarea').fill(prompt);
  await page.getByRole('button', { name: '메시지 보내기' }).click();
  const userContent = page.locator('.v2-message--user .v2-message__content').last();
  await expect(userContent).toContainText(prompt);
  await expect(page.locator('.v2-message--assistant').last()).toContainText('채팅 응답 정상');
  await userContent.scrollIntoViewIfNeeded();
  // Select from actual glyphs; the paragraph's center may be between wrapped lines.
  const points = await userContent.evaluate((element) => {
    const text = element.firstChild;
    const range = document.createRange();
    range.setStart(text, 0);
    range.setEnd(text, 1);
    const first = range.getBoundingClientRect();
    range.setStart(text, text.length - 1);
    range.setEnd(text, text.length);
    const last = range.getBoundingClientRect();
    return { startX: first.left + 1, startY: first.top + first.height / 2,
      endX: last.right - 1, endY: last.top + last.height / 2 };
  });
  await page.mouse.move(points.startX, points.startY);
  await page.mouse.down();
  await page.mouse.move(points.endX, points.endY, { steps: 12 });
  await page.mouse.up();

  const selectedText = await page.evaluate(() => window.getSelection()?.toString() || '');
  expect(selectedText).toContain('복사할 수 있는 사용자 메시지');
});

test('파일 선택 첨부·파싱·전송과 원래 파일명 복원이 동작한다', async ({ page }) => {
  await startNewConversation(page);
  const filename = 'career-e2e.txt';
  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: '파일 첨부' }).click();
  const chooser = await chooserPromise;
  await chooser.setFiles({
    name: filename,
    mimeType: 'text/plain',
    buffer: Buffer.from('FastAPI 기반 API의 응답 시간을 50% 줄였습니다.', 'utf8'),
  });

  await waitForReadyAttachment(page, filename);
  await page.locator('textarea').fill('첨부 문서의 기술과 개선 수치를 알려주세요.');
  await page.getByRole('button', { name: '메시지 보내기' }).click();

  await expect(page.locator('.v2-message--assistant').last()).toContainText(
    'FastAPI 기반 API의 응답 시간을 50% 줄였습니다.',
  );
  await page.reload();
  const restored = page.locator('.v2-message--user').last();
  await expect(restored).toContainText(filename);
  await expect(restored).not.toContainText('ATT-');
});

test('클립보드 붙여넣기와 드래그앤드롭이 같은 첨부 파이프라인을 사용한다', async ({ page }) => {
  await startNewConversation(page);
  const textarea = page.locator('textarea');
  const composer = page.locator('.v2-composer');

  await textarea.evaluate((node) => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(
      ['paste E2E evidence 61%'],
      'paste-e2e.txt',
      { type: 'text/plain' },
    ));
    node.dispatchEvent(new ClipboardEvent('paste', {
      clipboardData: transfer,
      bubbles: true,
      cancelable: true,
    }));
  });
  await waitForReadyAttachment(page, 'paste-e2e.txt');
  await page.getByRole('button', { name: 'paste-e2e.txt 제거' }).click();

  await composer.evaluate((node) => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(
      ['# drop E2E evidence\nconversion 62%'],
      'drop-e2e.md',
      { type: 'text/markdown' },
    ));
    window.__careerMemoryE2ETransfer = transfer;
    node.dispatchEvent(new DragEvent('dragenter', {
      dataTransfer: transfer,
      bubbles: true,
      cancelable: true,
    }));
  });
  await expect(page.getByRole('status')).toContainText('여기에 놓아 첨부하세요');
  await composer.evaluate((node) => {
    node.dispatchEvent(new DragEvent('drop', {
      dataTransfer: window.__careerMemoryE2ETransfer,
      bubbles: true,
      cancelable: true,
    }));
    delete window.__careerMemoryE2ETransfer;
  });
  await waitForReadyAttachment(page, 'drop-e2e.md');
  await page.getByRole('button', { name: 'drop-e2e.md 제거' }).click();
  await expect(page.locator('.v2-attachments > li')).toHaveCount(0);
});

test('첨부 오류를 쉬운 문구로 안내하고 사용자가 닫을 수 있다', async ({ page }) => {
  await startNewConversation(page);
  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: '파일 첨부' }).click();
  const chooser = await chooserPromise;
  await chooser.setFiles({
    name: 'unsupported-e2e.exe',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('not an executable', 'utf8'),
  });

  const alert = page.getByRole('alert');
  await expect(alert).toContainText('지원하지 않는 형식의 파일 1개는 추가하지 않았습니다.');
  await page.getByRole('button', { name: '첨부 오류 닫기' }).click();
  await expect(alert).toHaveCount(0);
});

test('실제 모델 채팅 smoke test @live', async ({ page }) => {
  test.skip(process.env.E2E_AI_MODE !== 'live', '명시적인 실제 모델 실행에서만 수행합니다.');
  test.setTimeout(120_000);
  await startNewConversation(page);

  await page.locator('textarea').fill("'실제 모델 E2E 정상'을 포함해 한 문장으로 답해주세요.");
  await page.getByRole('button', { name: '메시지 보내기' }).click();

  const answer = page.locator('.v2-message--assistant').last();
  await expect(answer).toContainText('실제 모델 E2E 정상', { timeout: 100_000 });
  await expect(answer).not.toContainText('답변을 생성하지 못했습니다');
});
