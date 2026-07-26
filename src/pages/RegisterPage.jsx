import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth.js';
import { RECOVERY_QUESTIONS } from '../auth/recoveryQuestions.js';
import '../styles/auth.css';

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    display_name: '',
    username: '',
    email: '',
    password: '',
    password_confirm: '',
    recovery_question: RECOVERY_QUESTIONS[0].value,
    recovery_answer: '',
  });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);
  const change = (field) => (event) => setForm({ ...form, [field]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await register(form);
      navigate('/chat', { replace: true });
    } catch (requestError) {
      setError(requestError.message || '회원가입하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="register-title">
        <Link className="auth-brand" to="/login"><span>CM</span>Career Memory</Link>
        <div><p className="auth-eyebrow">CREATE ACCOUNT</p><h1 id="register-title">회원가입</h1><p>대화와 경험은 이 계정에 안전하게 구분하여 저장됩니다.</p></div>
        <form className="auth-form" onSubmit={submit}>
          <label>이름<input autoComplete="name" required maxLength="100" value={form.display_name} onChange={change('display_name')} /></label>
          <label>아이디<input autoComplete="username" required minLength="4" maxLength="30" pattern="[a-z0-9_]+" value={form.username} onChange={change('username')} /><small>영문 소문자, 숫자, 밑줄로 4~30자</small></label>
          <label>이메일<input type="email" autoComplete="email" required value={form.email} onChange={change('email')} /></label>
          <label>비밀번호<span className="auth-password-field"><input type={showPassword ? 'text' : 'password'} autoComplete="new-password" required minLength="6" maxLength="128" value={form.password} onChange={change('password')} /><button type="button" aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)}>{showPassword ? '숨기기' : '보기'}</button></span><small>6자 이상으로 입력해 주세요.</small></label>
          <label>비밀번호 확인<span className="auth-password-field"><input type={showPasswordConfirm ? 'text' : 'password'} autoComplete="new-password" required minLength="6" maxLength="128" value={form.password_confirm} onChange={change('password_confirm')} /><button type="button" aria-label={showPasswordConfirm ? '비밀번호 확인 값 숨기기' : '비밀번호 확인 값 보기'} aria-pressed={showPasswordConfirm} onClick={() => setShowPasswordConfirm((visible) => !visible)}>{showPasswordConfirm ? '숨기기' : '보기'}</button></span></label>
          <label>비밀번호 복구 질문<select value={form.recovery_question} onChange={change('recovery_question')}>{RECOVERY_QUESTIONS.map((question) => <option key={question.value} value={question.value}>{question.label}</option>)}</select></label>
          <label>복구 답변<input autoComplete="off" required minLength="2" maxLength="100" value={form.recovery_answer} onChange={change('recovery_answer')} /><small>다른 사람이 쉽게 추측할 수 없는 답변을 사용하세요. 답변은 해시로 저장되어 원문을 확인할 수 없습니다.</small></label>
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="ui-button" disabled={busy}>{busy ? '계정 생성 중…' : '회원가입'}</button>
        </form>
        <p className="auth-switch">이미 계정이 있나요? <Link to="/login">로그인</Link></p>
      </section>
    </main>
  );
}
