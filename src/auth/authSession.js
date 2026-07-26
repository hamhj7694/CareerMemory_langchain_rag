// HttpOnly 로그인 쿠키는 JavaScript에서 읽지 않는다.
// 서버가 응답으로 준 CSRF 토큰만 메모리에 보관해 상태 변경 요청에 사용한다.
let csrfToken = '';
let currentUserId = '';

export function getCsrfToken() {
  return csrfToken;
}

export function setCsrfToken(value) {
  csrfToken = value || '';
}

export function clearCsrfToken() {
  csrfToken = '';
}

export function setCurrentUserId(value) {
  currentUserId = value || '';
}

export function clearCurrentUserId() {
  currentUserId = '';
}

export function getUserStorageKey(baseKey) {
  return currentUserId ? `${baseKey}.user.${currentUserId}` : `${baseKey}.anonymous`;
}
