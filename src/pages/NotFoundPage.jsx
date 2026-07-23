import { Link } from 'react-router-dom';
export function NotFoundPage() {
  return <section><h2>페이지를 찾을 수 없습니다</h2><p>주소를 다시 확인해 주세요.</p><Link to="/memory">경험 메모리로 돌아가기</Link></section>;
}
