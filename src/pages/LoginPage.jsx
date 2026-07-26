import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth.js';
import '../styles/auth.css';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ identifier: '', password: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await login(form);
      navigate(location.state?.from?.pathname || '/chat', { replace: true });
    } catch (requestError) {
      setError(requestError.message || '로그인하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-title">
        <Link className="auth-brand" to="/login"><span>CM</span>Career Memory</Link>
        <div><p className="auth-eyebrow">WELCOME BACK</p><h1 id="login-title">로그인</h1><p>저장한 대화와 커리어 기록을 이어서 확인하세요.</p></div>
        <form className="auth-form" onSubmit={submit}>
          <label>아이디<input autoComplete="username" required value={form.identifier} onChange={(event) => setForm({ ...form, identifier: event.target.value })} /></label>
          <label>비밀번호<input type="password" autoComplete="current-password" required value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="ui-button" disabled={busy}>{busy ? '로그인 중…' : '로그인'}</button>
        </form>
        <div className="auth-links"><Link to="/find-username">아이디 찾기</Link><Link to="/forgot-password">비밀번호 찾기</Link></div>
        <p className="auth-switch">처음이신가요? <Link to="/register">회원가입</Link></p>
      </section>
    </main>
  );
}
