import { useState } from 'react';
import { authApi } from '../api/authApi.js';
import { RECOVERY_QUESTIONS } from '../auth/recoveryQuestions.js';
import { useAuth } from '../auth/useAuth.js';
import '../styles/auth.css';

export function AccountPage() {
  const { user, setUsername, updateProfile } = useAuth();
  const [profileForm, setProfileForm] = useState({
    display_name: user?.display_name || '',
  });
  const [profileMessage, setProfileMessage] = useState('');
  const [profileError, setProfileError] = useState('');
  const [profileBusy, setProfileBusy] = useState(false);
  const [usernameForm, setUsernameForm] = useState({
    username: user?.username || '',
    current_password: '',
  });
  const [usernameMessage, setUsernameMessage] = useState('');
  const [usernameError, setUsernameError] = useState('');
  const [usernameBusy, setUsernameBusy] = useState(false);
  const [passwordForm, setPasswordForm] = useState({
    current_password: '',
    password: '',
    password_confirm: '',
  });
  const [passwordMessage, setPasswordMessage] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [form, setForm] = useState({
    current_password: '',
    recovery_question: RECOVERY_QUESTIONS[0].value,
    recovery_answer: '',
  });
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const response = await authApi.setRecoveryQuestion(form);
      setMessage(response.message);
      setForm((current) => ({
        ...current,
        current_password: '',
        recovery_answer: '',
      }));
    } catch (requestError) {
      setError(requestError.message || '복구 질문을 저장하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  const submitUsername = async (event) => {
    event.preventDefault();
    setUsernameBusy(true);
    setUsernameError('');
    setUsernameMessage('');
    try {
      await setUsername(usernameForm);
      setUsernameMessage('로그인 아이디가 저장되었습니다.');
      setUsernameForm((current) => ({
        ...current,
        current_password: '',
      }));
    } catch (requestError) {
      setUsernameError(requestError.message || '아이디를 저장하지 못했습니다.');
    } finally {
      setUsernameBusy(false);
    }
  };

  const submitProfile = async (event) => {
    event.preventDefault();
    setProfileBusy(true);
    setProfileError('');
    setProfileMessage('');
    try {
      await updateProfile(profileForm);
      setProfileMessage('이름이 변경되었습니다.');
    } catch (requestError) {
      setProfileError(requestError.message || '이름을 변경하지 못했습니다.');
    } finally {
      setProfileBusy(false);
    }
  };

  const submitPassword = async (event) => {
    event.preventDefault();
    setPasswordBusy(true);
    setPasswordError('');
    setPasswordMessage('');
    try {
      const response = await authApi.changePassword(passwordForm);
      setPasswordMessage(response.message);
      setPasswordForm({
        current_password: '',
        password: '',
        password_confirm: '',
      });
    } catch (requestError) {
      setPasswordError(requestError.message || '비밀번호를 변경하지 못했습니다.');
    } finally {
      setPasswordBusy(false);
    }
  };

  return (
    <section className="account-page">
      <div className="account-card">
        <p className="auth-eyebrow">ACCOUNT</p>
        <h2>계정 정보</h2>
        <dl><div><dt>이름</dt><dd>{user?.display_name}</dd></div><div><dt>아이디</dt><dd>{user?.username || '미설정'}</dd></div><div><dt>이메일</dt><dd>{user?.email}</dd></div></dl>
      </div>
      <div className="account-card">
        <h2>이름 변경</h2>
        <p>변경한 이름은 화면 표시와 AI의 맞춤형 대화에 사용됩니다.</p>
        <form className="auth-form" onSubmit={submitProfile}>
          <label>이름<input autoComplete="name" required minLength="1" maxLength="100" value={profileForm.display_name} onChange={(event) => setProfileForm({ display_name: event.target.value })} /></label>
          {profileMessage && <p className="auth-success" role="status">{profileMessage}</p>}
          {profileError && <p className="auth-error" role="alert">{profileError}</p>}
          <button className="ui-button" disabled={profileBusy}>{profileBusy ? '저장 중…' : '이름 저장'}</button>
        </form>
      </div>
      <div className="account-card">
        <h2>아이디 변경</h2>
        <p>아이디를 변경하면 다음 로그인부터 새로운 아이디를 사용합니다.</p>
        <form className="auth-form" onSubmit={submitUsername}>
          <label>새 아이디<input autoComplete="username" required minLength="4" maxLength="30" pattern="[a-z0-9_]+" value={usernameForm.username} onChange={(event) => setUsernameForm({ ...usernameForm, username: event.target.value })} /></label>
          <label>현재 비밀번호<input type="password" autoComplete="current-password" required value={usernameForm.current_password} onChange={(event) => setUsernameForm({ ...usernameForm, current_password: event.target.value })} /></label>
          {usernameMessage && <p className="auth-success" role="status">{usernameMessage}</p>}
          {usernameError && <p className="auth-error" role="alert">{usernameError}</p>}
          <button className="ui-button" disabled={usernameBusy}>{usernameBusy ? '저장 중…' : '아이디 저장'}</button>
        </form>
      </div>
      <div className="account-card">
        <h2>비밀번호 변경</h2>
        <p>현재 비밀번호를 확인한 후 6자 이상의 새 비밀번호로 변경할 수 있습니다.</p>
        <form className="auth-form" onSubmit={submitPassword}>
          <label>현재 비밀번호<input type="password" autoComplete="current-password" required value={passwordForm.current_password} onChange={(event) => setPasswordForm({ ...passwordForm, current_password: event.target.value })} /></label>
          <label>새 비밀번호<input type="password" autoComplete="new-password" required minLength="6" maxLength="128" value={passwordForm.password} onChange={(event) => setPasswordForm({ ...passwordForm, password: event.target.value })} /></label>
          <label>새 비밀번호 확인<input type="password" autoComplete="new-password" required minLength="6" maxLength="128" value={passwordForm.password_confirm} onChange={(event) => setPasswordForm({ ...passwordForm, password_confirm: event.target.value })} /></label>
          {passwordMessage && <p className="auth-success" role="status">{passwordMessage}</p>}
          {passwordError && <p className="auth-error" role="alert">{passwordError}</p>}
          <button className="ui-button" disabled={passwordBusy}>{passwordBusy ? '변경 중…' : '비밀번호 변경'}</button>
        </form>
      </div>
      <div className="account-card">
        <h2>비밀번호 복구 질문 변경</h2>
        <p>기존 계정은 여기에서 질문을 등록하거나 변경할 수 있습니다. 변경하려면 현재 비밀번호가 필요합니다.</p>
        <form className="auth-form" onSubmit={submit}>
          <label>현재 비밀번호<input type="password" autoComplete="current-password" required value={form.current_password} onChange={(event) => setForm({ ...form, current_password: event.target.value })} /></label>
          <label>복구 질문<select value={form.recovery_question} onChange={(event) => setForm({ ...form, recovery_question: event.target.value })}>{RECOVERY_QUESTIONS.map((question) => <option key={question.value} value={question.value}>{question.label}</option>)}</select></label>
          <label>복구 답변<input autoComplete="off" required minLength="2" maxLength="100" value={form.recovery_answer} onChange={(event) => setForm({ ...form, recovery_answer: event.target.value })} /><small>다른 사람이 쉽게 추측할 수 없는 답변을 사용하세요.</small></label>
          {message && <p className="auth-success" role="status">{message}</p>}
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="ui-button" disabled={busy}>{busy ? '저장 중…' : '복구 질문 저장'}</button>
        </form>
      </div>
    </section>
  );
}
