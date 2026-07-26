import { describe, expect, it } from 'vitest';
import { getCanonicalDevelopmentUrl } from './developmentHost.js';

describe('개발 서버 로그인 주소 통일', () => {
  it('127.0.0.1 프론트 주소를 localhost로 바꾼다', () => {
    expect(getCanonicalDevelopmentUrl(
      'http://127.0.0.1:5173/chat?mode=auto',
      'http://localhost:8000',
    )).toBe('http://localhost:5173/chat?mode=auto');
  });

  it('이미 localhost이거나 운영 도메인이면 이동하지 않는다', () => {
    expect(getCanonicalDevelopmentUrl(
      'http://localhost:5173/chat',
      'http://localhost:8000',
    )).toBeNull();
    expect(getCanonicalDevelopmentUrl(
      'https://career.example.com/chat',
      'https://api.career.example.com',
    )).toBeNull();
  });
});
