import { expect, test } from '@playwright/test';

const account = {
  username: 'e2e_recovery',
  email: 'e2e.recovery@example.test',
  display_name: 'Recovery Tester',
  password: 'old-pass-123',
  password_confirm: 'old-pass-123',
  recovery_question: 'childhood_nickname',
  recovery_answer: '토리',
};

test.beforeAll(async ({ request }) => {
  const response = await request.post('/api/v2/auth/register', { data: account });
  expect(response.status()).toBe(201);
});

test('저장된 복구 질문 하나만 표시해 비밀번호를 재설정한다', async ({ page }) => {
  await page.goto('/forgot-password');
  await page.getByLabel('이메일').fill(account.email);
  await page.getByLabel('아이디').fill(account.username);
  await page.getByRole('button', { name: '복구 질문 확인' }).click();

  await expect(page.getByText('어릴 적 별명은?', { exact: true })).toBeVisible();
  await expect(page.locator('select')).toHaveCount(0);

  await page.getByLabel('복구 답변').fill(account.recovery_answer);
  await page.getByLabel('새 비밀번호', { exact: true }).fill('new-pass-456');
  await page.getByLabel('새 비밀번호 확인').fill('new-pass-456');
  await page.getByRole('button', { name: '새 비밀번호 설정' }).click();
  await expect(page.getByRole('status')).toContainText('비밀번호가 변경되었습니다.');

  await page.getByRole('link', { name: '로그인으로 돌아가기' }).click();
  await page.getByLabel('아이디', { exact: true }).fill(account.username);
  await page.getByLabel('비밀번호', { exact: true }).fill('new-pass-456');
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await expect(page).toHaveURL(/\/chat(?:\/|$)/);

  await page.goto('/account');
  await expect(page.getByRole('combobox', { name: '복구 질문' }))
    .toHaveValue('childhood_nickname');
});
