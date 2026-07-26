import { useState } from 'react';
import { Link } from 'react-router-dom';
import { authApi } from '../api/authApi.js';
import { RECOVERY_QUESTIONS } from '../auth/recoveryQuestions.js';
import '../styles/auth.css';

export function AccountRecoveryPage() {
  const [form, setForm] = useState({
    email: '',
    username: '',
    recovery_question: RECOVERY_QUESTIONS[0].value,
    recovery_answer: '',
    password: '',
    password_confirm: '',
  });
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const response = await authApi.recoverPassword(form);
      setMessage(response.message);
    } catch (requestError) {
      setError(requestError.message || '요청을 처리하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="recovery-title">
        <Link className="auth-brand" to="/login"><span>CM</span>Career Memory</Link>
        <div>
          <p className="auth-eyebrow">ACCOUNT RECOVERY</p>
          <h1 id="recovery-title">비밀번호 찾기</h1>
          <p>가입 이메일과 복구 질문의 답변을 확인한 뒤 새 비밀번호를 설정합니다.</p>
        </div>
        <form className="auth-form" onSubmit={submit}>
          <label>이메일<input type="email" autoComplete="email" required value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
          <label>아이디<input autoComplete="username" required minLength="4" maxLength="30" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} /></label>
          <label>가입할 때 선택한 질문<select value={form.recovery_question} onChange={(event) => setForm({ ...form, recovery_question: event.target.value })}>{RECOVERY_QUESTIONS.map((question) => <option key={question.value} value={question.value}>{question.label}</option>)}</select></label>
          <label>복구 답변<input autoComplete="off" required minLength="2" maxLength="100" value={form.recovery_answer} onChange={(event) => setForm({ ...form, recovery_answer: event.target.value })} /></label>
          <label>새 비밀번호<input type="password" autoComplete="new-password" required minLength="6" maxLength="128" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
          <label>새 비밀번호 확인<input type="password" autoComplete="new-password" required minLength="6" maxLength="128" value={form.password_confirm} onChange={(event) => setForm({ ...form, password_confirm: event.target.value })} /></label>
          {message && <p className="auth-success" role="status">{message}</p>}
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="ui-button" disabled={busy || Boolean(message)}>{busy ? '확인 중…' : '새 비밀번호 설정'}</button>
        </form>
        <p className="auth-switch"><Link to="/login">로그인으로 돌아가기</Link></p>
      </section>
    </main>
  );
}
