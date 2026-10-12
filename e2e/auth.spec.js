import { expect, test } from '@playwright/test';

test('가입 없이 바로 체험하고 현재 기록을 간단 아이디로 저장한다', async ({ page }) => {
  await page.goto('/start');
  await page.getByRole('button', { name: '바로 체험하기' }).click();

  await expect(page).toHaveURL(/\/chat(?:\/|$)/);
  await expect(page.getByText('가입 없는 체험 중')).toBeVisible();

  await page.getByRole('link', { name: '이 기록 저장하기' }).click();
  await page.getByLabel('간단 아이디').fill('e2e_guest_saved');
  await page.getByLabel('PIN', { exact: true }).fill('123456');
  await page.getByLabel('닉네임(호칭)').fill('체험 저장 사용자');
  await page.getByLabel('PIN 복구 질문').selectOption('recovery_keyword');
  await page.getByLabel('복구 답변').fill('체험 복구 단어');
  await page.getByRole('button', { name: '이 기록 계속 사용하기' }).click();

  await expect(page.getByRole('status')).toContainText('어디서든 기록을 이어볼 수 있어요');
  await expect(
    page.getByRole('complementary', { name: '주 메뉴' }).getByText('@e2e_guest_saved')
  ).toBeVisible();
});

test('신규 아이디는 닉네임을 정하고 기존 아이디는 PIN으로 다시 연다', async ({ page }) => {
  await page.goto('/start');
  await page.getByLabel('간단 아이디').fill('e2e_simple');
  await page.getByLabel('PIN', { exact: true }).fill('654321');
  await page.getByRole('button', { name: '내 기록으로 시작하기' }).click();

  await expect(page.getByLabel('닉네임(호칭)')).toBeVisible();
  await page.getByLabel('닉네임(호칭)').fill('E2E 사용자');
  await page.getByLabel('PIN 복구 질문').selectOption('first_skill');
  await page.getByLabel('복구 답변').fill('Playwright');
  await page.getByRole('button', { name: '설정 저장하고 시작하기' }).click();

  await expect(page).toHaveURL(/\/chat(?:\/|$)/);
  await expect(page.getByText('@e2e_simple')).toBeVisible();
  await page.getByRole('button', { name: '나가기' }).click();
  await expect(page).toHaveURL(/\/start$/);

  await page.getByLabel('간단 아이디').fill('e2e_simple');
  await page.getByLabel('PIN', { exact: true }).fill('000000');
  await page.getByRole('button', { name: '내 기록으로 시작하기' }).click();

  await expect(page).toHaveURL(/\/start$/);
  await expect(page.getByRole('alert')).toContainText(
    '간단 아이디 또는 PIN이 올바르지 않아요. 다시 확인해 주세요.',
  );

  await page.getByLabel('PIN', { exact: true }).fill('654321');
  await page.getByRole('button', { name: '내 기록으로 시작하기' }).click();

  await expect(page).toHaveURL(/\/chat(?:\/|$)/);
  await expect(page.getByText('@e2e_simple')).toBeVisible();
});

test('저장한 질문과 답변으로 PIN을 새로 설정한다', async ({ page, request }) => {
  const created = await request.post('/api/v2/auth/simple', {
    data: {
      identifier: 'e2e_pin_recovery',
      pin: '123456',
      display_name: 'PIN 복구 사용자',
      recovery_question: 'favorite_work',
      recovery_answer: '어린 왕자',
    },
  });
  expect(created.status()).toBe(200);

  await page.goto('/start');
  await page.getByRole('link', { name: 'PIN을 잊었어요' }).click();
  await page.getByLabel('간단 아이디').fill('e2e_pin_recovery');
  await page.getByRole('button', { name: '복구 질문 확인하기' }).click();

  await expect(page.getByText('가장 좋아하는 책·영화·작품은?')).toBeVisible();
  await page.getByLabel('내가 설정한 답변').fill('어린 왕자');
  await page.getByLabel('새 PIN', { exact: true }).fill('654321');
  await page.getByLabel('새 PIN 확인').fill('654321');
  await page.getByRole('button', { name: '새 PIN으로 변경하기' }).click();

  await expect(page.getByRole('status')).toContainText('새 PIN으로 변경했어요');
  await page.getByRole('link', { name: '새 PIN으로 시작하기' }).click();
  await page.getByLabel('간단 아이디').fill('e2e_pin_recovery');
  await page.getByLabel('PIN', { exact: true }).fill('654321');
  await page.getByRole('button', { name: '내 기록으로 시작하기' }).click();
  await expect(page).toHaveURL(/\/chat(?:\/|$)/);
  await expect(page.getByText('@e2e_pin_recovery')).toBeVisible();
});
