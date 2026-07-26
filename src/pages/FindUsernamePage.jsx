import { useState } from 'react';
import { Link } from 'react-router-dom';
import { authApi } from '../api/authApi.js';
import '../styles/auth.css';

export function FindUsernamePage() {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setUsername('');
    try {
      const response = await authApi.findUsername(email);
      setUsername(response.username);
    } catch (requestError) {
      setError(requestError.message || '아이디를 찾지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="find-username-title">
        <Link className="auth-brand" to="/login"><span>CM</span>Career Memory</Link>
        <div><p className="auth-eyebrow">FIND USERNAME</p><h1 id="find-username-title">아이디 찾기</h1><p>회원가입에 사용한 이메일을 입력해 주세요.</p></div>
        <form className="auth-form" onSubmit={submit}>
          <label>이메일<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          {username && <p className="auth-success" role="status">등록된 아이디는 <strong>{username}</strong>입니다.</p>}
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="ui-button" disabled={busy}>{busy ? '찾는 중…' : '아이디 찾기'}</button>
        </form>
        <p className="auth-switch"><Link to="/login">로그인으로 돌아가기</Link></p>
      </section>
    </main>
  );
}
