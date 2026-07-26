// 서버가 실제 완료율을 보내지 않으므로, 완료 전에는 92%를 넘지 않도록 한다.
// 이렇게 하면 처리 중인 요청을 100% 완료된 것처럼 오해하지 않는다.
export function getEstimatedProgress(elapsedSeconds) {
  if (elapsedSeconds < 3) return 12 + elapsedSeconds * 6;
  if (elapsedSeconds < 10) return 30 + (elapsedSeconds - 3) * 4;
  if (elapsedSeconds < 25) return 58 + (elapsedSeconds - 10) * 1.5;
  return Math.min(92, 80.5 + (elapsedSeconds - 25) * 0.25);
}
