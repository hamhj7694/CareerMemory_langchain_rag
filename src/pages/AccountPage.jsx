import { useState } from 'react';
import { RECOVERY_QUESTIONS, recoveryQuestionLabel } from '../auth/recoveryQuestions.js';
import { useAuth } from '../auth/useAuth.js';
import '../styles/auth.css';

export function AccountPage() {
  const { user, claimGuest, updateProfile } = useAuth();
  const [claimForm, setClaimForm] = useState({
    identifier: '',
    pin: '',
    displayName: '',
    recoveryQuestion: RECOVERY_QUESTIONS[0].value,
    recoveryAnswer: '',
  });
  const [profileForm, setProfileForm] = useState({ display_name: user?.display_name || '' });
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const saveGuestRecord = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage('');
    setError('');
    try {
      await claimGuest({
        identifier: claimForm.identifier,
        pin: claimForm.pin,
        display_name: claimForm.displayName,
        recovery_question: claimForm.recoveryQuestion,
        recovery_answer: claimForm.recoveryAnswer,
      });
      setMessage('이제 이 아이디와 PIN으로 어디서든 기록을 이어볼 수 있어요.');
    } catch (requestError) {
      setError(requestError.message || '체험 기록을 저장하지 못했어요.');
    } finally {
      setBusy(false);
    }
  };

  const saveDisplayName = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage('');
    setError('');
    try {
      await updateProfile(profileForm);
      setMessage('화면에 표시할 이름을 저장했어요.');
    } catch (requestError) {
      setError(requestError.message || '이름을 저장하지 못했어요.');
    } finally {
      setBusy(false);
    }
  };

  if (user?.account_type === 'guest') {
    return (
      <section className="account-page">
        <div className="account-card account-card--highlight">
          <p className="auth-eyebrow">SAVE YOUR MEMORY</p>
          <h2>이 체험 기록을 계속 사용하시겠어요?</h2>
          <p>간단 아이디와 PIN, 닉네임, PIN 복구 질문을 정하면 지금까지의 대화와 경험을 그대로 이어볼 수 있어요.</p>
          <form className="auth-form" onSubmit={saveGuestRecord}>
            <label>간단 아이디<input autoComplete="username" required minLength="2" maxLength="20" pattern="[0-9A-Za-z가-힣_-]+" placeholder="한글·영문·숫자 2~20자" value={claimForm.identifier} onChange={(event) => setClaimForm({ ...claimForm, identifier: event.target.value })} /></label>
            <label>PIN<input type="password" inputMode="numeric" autoComplete="new-password" required minLength="6" maxLength="6" pattern="[0-9]{6}" placeholder="숫자 6자리" value={claimForm.pin} onChange={(event) => setClaimForm({ ...claimForm, pin: event.target.value.replace(/\D/g, '').slice(0, 6) })} /></label>
            <label>닉네임(호칭)<input autoComplete="name" required minLength="1" maxLength="40" placeholder="예: 커리어 탐험가" value={claimForm.displayName} onChange={(event) => setClaimForm({ ...claimForm, displayName: event.target.value })} /></label>
            <label>PIN 복구 질문<select value={claimForm.recoveryQuestion} onChange={(event) => setClaimForm({ ...claimForm, recoveryQuestion: event.target.value })}>{RECOVERY_QUESTIONS.map((question) => <option key={question.value} value={question.value}>{question.label}</option>)}</select></label>
            <label>복구 답변<input autoComplete="off" required minLength="2" maxLength="100" placeholder="내가 기억할 답변 2자 이상" value={claimForm.recoveryAnswer} onChange={(event) => setClaimForm({ ...claimForm, recoveryAnswer: event.target.value })} /></label>
            {message && <p className="auth-success" role="status">{message}</p>}
            {error && <p className="auth-error" role="alert">{error}</p>}
            <button className="ui-button" disabled={busy}>{busy ? '기록 저장 중…' : '이 기록 계속 사용하기'}</button>
          </form>
          <p className="start-pin-notice">PIN은 복구 질문으로 다시 설정할 수 있지만, 이메일을 받지 않으므로 아이디는 꼭 기억해 주세요.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="account-page">
      <div className="account-card">
        <p className="auth-eyebrow">MY MEMORY</p>
        <h2>내 기록</h2>
        <dl>
          <div><dt>간단 아이디</dt><dd>@{user?.username}</dd></div>
          <div><dt>닉네임(호칭)</dt><dd>{user?.display_name}</dd></div>
          <div><dt>PIN 복구 질문</dt><dd>{recoveryQuestionLabel(user?.recovery_question)}</dd></div>
          <div><dt>저장 방식</dt><dd>아이디와 PIN</dd></div>
        </dl>
      </div>
      <div className="account-card">
        <h2>닉네임 바꾸기</h2>
        <p>AI 대화와 화면에서 사용할 이름만 편하게 바꿀 수 있어요. 로그인 아이디는 그대로 유지됩니다.</p>
        <form className="auth-form" onSubmit={saveDisplayName}>
          <label>닉네임(호칭)<input autoComplete="name" required minLength="1" maxLength="40" value={profileForm.display_name} onChange={(event) => setProfileForm({ display_name: event.target.value })} /></label>
          {message && <p className="auth-success" role="status">{message}</p>}
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="ui-button" disabled={busy}>{busy ? '저장 중…' : '닉네임 저장'}</button>
        </form>
      </div>
      <div className="account-card account-card--notice">
        <h2>PIN을 잊었다면</h2>
        <p>시작 화면의 ‘PIN을 잊었어요’에서 저장한 질문에 답하고 새 PIN을 설정할 수 있습니다. 아이디는 별도로 기억해 주세요.</p>
      </div>
    </section>
  );
}
