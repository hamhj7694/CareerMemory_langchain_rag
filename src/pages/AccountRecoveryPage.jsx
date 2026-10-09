import { useState } from 'react';
import { Link } from 'react-router-dom';
import { authApi } from '../api/authApi.js';
import { RECOVERY_QUESTIONS } from '../auth/recoveryQuestions.js';
import '../styles/auth.css';

export function AccountRecoveryPage() {
  const [form, setForm] = useState({
    email: '',
    username: '',
    recovery_answer: '',
    password: '',
    password_confirm: '',
  });
  const [recoveryQuestion, setRecoveryQuestion] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const changeIdentity = (field) => (event) => {
    setForm((current) => ({
      ...current,
      [field]: event.target.value,
      recovery_answer: '',
    }));
    setRecoveryQuestion('');
    setMessage('');
    setError('');
  };

  const loadQuestion = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const response = await authApi.getRecoveryQuestion({
        email: form.email,
        username: form.username,
      });
      setRecoveryQuestion(response.recovery_question);
    } catch (requestError) {
      setError(requestError.message || '복구 질문을 확인하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

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
        <form className="auth-form" onSubmit={recoveryQuestion ? submit : loadQuestion}>
          <label>이메일<input type="email" autoComplete="email" required value={form.email} onChange={changeIdentity('email')} /></label>
          <label>아이디<input autoComplete="username" required minLength="4" maxLength="30" pattern="[a-z0-9_]+" value={form.username} onChange={changeIdentity('username')} /></label>
          {recoveryQuestion && <>
            <div className="auth-recovery-question" aria-live="polite">
              <span>등록한 복구 질문</span>
              <strong>{RECOVERY_QUESTIONS.find((question) => question.value === recoveryQuestion)?.label || '등록한 복구 질문에 답해 주세요.'}</strong>
            </div>
            <label>복구 답변<input autoComplete="off" required minLength="2" maxLength="100" value={form.recovery_answer} onChange={(event) => setForm({ ...form, recovery_answer: event.target.value })} /></label>
            <label>새 비밀번호<input type="password" autoComplete="new-password" required minLength="6" maxLength="128" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
            <label>새 비밀번호 확인<input type="password" autoComplete="new-password" required minLength="6" maxLength="128" value={form.password_confirm} onChange={(event) => setForm({ ...form, password_confirm: event.target.value })} /></label>
          </>}
          {message && <p className="auth-success" role="status">{message}</p>}
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="ui-button" disabled={busy || Boolean(message)}>{busy ? '확인 중…' : recoveryQuestion ? '새 비밀번호 설정' : '복구 질문 확인'}</button>
        </form>
        <p className="auth-switch"><Link to="/login">로그인으로 돌아가기</Link></p>
      </section>
    </main>
  );
}
