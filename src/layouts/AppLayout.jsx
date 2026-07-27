import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth.js';

const PAGE_TITLES = [
  { pattern: /^\/chat(?:\/[^/]+)?$/, title: '커리어 챗' },
  { pattern: /^\/memory\/trash$/, title: '경험 휴지통' },
  { pattern: /^\/memory\/[^/]+$/, title: '경험 상세' },
  { pattern: /^\/memory$/, title: '경험 관리' },
  { pattern: /^\/jobs\/[^/]+$/, title: '공고 분석 결과' },
  { pattern: /^\/jobs$/, title: '채용공고 분석' },
  { pattern: /^\/documents\/[^/]+$/, title: '문서 편집' },
];

function getPageTitle(pathname) {
  return PAGE_TITLES.find(({ pattern }) => pattern.test(pathname))?.title ?? 'Career Memory';
}

export function AppLayout() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const signOut = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">본문으로 건너뛰기</a>
      <aside className="app-sidebar" aria-label="주 메뉴">
        <NavLink className="app-brand" to="/chat" aria-label="Career Memory 홈">
          <span className="app-brand__mark">CM</span>
          <span>Career Memory</span>
        </NavLink>
        <nav className="app-navigation">
          <NavLink to="/chat">커리어 챗</NavLink>
          <NavLink to="/memory">경험 관리</NavLink>
          <NavLink to="/jobs">채용공고 분석</NavLink>
        </nav>
        <div className="api-status" aria-label="API 연결 상태">
          <span aria-hidden="true">●</span>
          {import.meta.env.VITE_USE_MOCK !== 'false' ? 'Mock 데이터' : 'AI 엔진 연결'}
        </div>
        <div className="app-account">
          <strong>{user?.display_name}</strong>
          <span>{user?.username ? `@${user.username}` : user?.email}</span>
          <NavLink to="/account">계정 설정</NavLink>
          <button type="button" onClick={signOut}>로그아웃</button>
        </div>
      </aside>
      <section className="app-workspace">
        <header className="app-header">
          <h1>{getPageTitle(pathname)}</h1>
          <span className="app-header__context">대화를 커리어 자산으로</span>
        </header>
        <main id="main-content" tabIndex="-1">
          <Outlet />
        </main>
      </section>
    </div>
  );
}
