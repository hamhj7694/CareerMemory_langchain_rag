// localhost와 127.0.0.1은 같은 PC를 가리키지만 브라우저 쿠키는 서로 공유하지 않는다.
// 개발 중 API가 localhost를 사용한다면 프론트 주소도 localhost로 통일한다.
export function getCanonicalDevelopmentUrl(currentUrl, apiBaseUrl) {
  const current = new URL(currentUrl);
  const api = new URL(apiBaseUrl);
  if (current.hostname !== '127.0.0.1' || api.hostname !== 'localhost') {
    return null;
  }
  current.hostname = 'localhost';
  return current.toString();
}
