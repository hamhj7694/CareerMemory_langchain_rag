import { describe, expect, it } from 'vitest';
import {
  attachmentUnavailableMessage,
  toUserFacingAttachmentError,
  toUserFacingErrorMessage,
} from './userFacingError.js';

describe('사용자용 오류 문구', () => {
  it('네트워크 오류의 개발자 문구를 실행 상태 안내로 바꾼다', () => {
    expect(toUserFacingErrorMessage({
      code: 'NETWORK_ERROR',
      message: 'TypeError: Failed to fetch',
    })).toBe('서버에 연결하지 못했어요. 서버가 실행 중인지 확인한 뒤 다시 시도해 주세요.');
  });

  it('사용자가 이해할 수 있는 서버 문구는 유지한다', () => {
    expect(toUserFacingErrorMessage(
      { code: 'VALIDATION_ERROR', message: '파일은 최대 10개까지 선택할 수 있습니다.' },
    )).toBe('파일은 최대 10개까지 선택할 수 있습니다.');
  });

  it('잘못된 간편 로그인은 세션 만료가 아닌 입력 확인으로 안내한다', () => {
    expect(toUserFacingErrorMessage({
      code: 'SIMPLE_LOGIN_FAILED',
      message: '간단 아이디 또는 PIN이 올바르지 않습니다.',
    })).toBe('간단 아이디 또는 PIN이 올바르지 않아요. 다시 확인해 주세요.');
  });

  it('간편 로그인 잠금은 AI 사용 한도가 아닌 PIN 잠금으로 안내한다', () => {
    expect(toUserFacingErrorMessage({
      code: 'SIMPLE_LOGIN_LOCKED',
      message: 'PIN을 여러 번 잘못 입력했어요. 15분 뒤 다시 시도해 주세요.',
    })).toBe('PIN을 여러 번 잘못 입력했어요. 15분 뒤 다시 시도해 주세요.');
  });

  it('복구 답변 오류와 잠금을 사용자가 구분할 수 있게 안내한다', () => {
    expect(toUserFacingErrorMessage({
      code: 'SIMPLE_PIN_RECOVERY_FAILED',
      message: 'internal recovery error',
    })).toBe('복구 답변이 올바르지 않아요. 다시 확인해 주세요.');
    expect(toUserFacingErrorMessage({
      code: 'SIMPLE_PIN_RECOVERY_LOCKED',
      message: 'internal rate limit',
    })).toBe('복구 답변을 여러 번 잘못 입력했어요. 15분 뒤 다시 시도해 주세요.');
  });

  it('내부 구현 정보가 포함된 문구는 화면별 기본 안내로 숨긴다', () => {
    expect(toUserFacingErrorMessage(
      'SQLAlchemy OperationalError: sqlite database is locked',
      '목록을 불러오지 못했어요. 다시 시도해 주세요.',
    )).toBe('목록을 불러오지 못했어요. 다시 시도해 주세요.');
  });

  it('OCR 실행 환경 오류를 파일 해결 방법으로 바꾼다', () => {
    expect(toUserFacingAttachmentError(
      'Tesseract executable was not found.',
    )).toContain('더 선명한 이미지');
  });

  it('첨부 상태에 따라 전송할 수 없는 이유와 해결 방법을 안내한다', () => {
    expect(attachmentUnavailableMessage({
      name: 'capture.png',
      processingStatus: 'failed',
    })).toBe('‘capture.png’ 파일을 준비하지 못했어요. ‘재시도’를 누르거나 파일을 삭제해 주세요.');

    expect(attachmentUnavailableMessage({
      name: 'capture.png',
      processingStatus: 'processing',
    })).toBe('‘capture.png’ 파일의 내용을 확인하고 있어요. 처리가 끝난 뒤 다시 전송해 주세요.');
  });
});

