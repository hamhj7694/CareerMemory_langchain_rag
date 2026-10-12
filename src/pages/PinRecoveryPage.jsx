import { useState } from 'react';
import { Link } from 'react-router-dom';
import { authApi } from '../api/authApi.js';
import { recoveryQuestionLabel } from '../auth/recoveryQuestions.js';
import '../styles/auth.css';

export function PinRecoveryPage() {
  const [form, setForm] = useState({
    identifier: '',
    recoveryAnswer: '',
    pin: '',
    pinConfirm: '',
  });
  const [question, setQuestion] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const findQuestion = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const response = await authApi.getSimplePinRecoveryQuestion({
        identifier: form.identifier,
      });
      setQuestion(response.recovery_question);
    } catch (requestError) {
      setError(requestError.message || 'PIN 복구 질문을 불러오지 못했어요.');
    } finally {
      setBusy(false);
    }
  };

  const resetPin = async (event) => {
    event.preventDefault();
    setError('');
    setMessage('');
    if (form.pin !== form.pinConfirm) {
      setError('새 PIN과 PIN 확인이 일치하지 않아요.');
      return;
    }
    setBusy(true);
    try {
      const response = await authApi.resetSimplePin({
        identifier: form.identifier,
        recovery_answer: form.recoveryAnswer,
        pin: form.pin,
        pin_confirm: form.pinConfirm,
      });
      setMessage(response.message);
    } catch (requestError) {
      setError(requestError.message || 'PIN을 변경하지 못했어요.');
    } finally {
      setBusy(false);
    }
  };

  const restart = () => {
    setForm({ identifier: '', recoveryAnswer: '', pin: '', pinConfirm: '' });
    setQuestion('');
    setError('');
    setMessage('');
  };

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="pin-recovery-title">
        <Link className="auth-brand" to="/start"><span>CM</span>Career Memory</Link>
        <div>
          <p className="auth-eyebrow">PIN RECOVERY</p>
          <h1 id="pin-recovery-title">PIN을 다시 설정해요</h1>
          <p>원래 PIN은 확인할 수 없지만, 저장해 둔 질문에 답하면 새 PIN으로 바꿀 수 있어요.</p>
        </div>

        {!question ? <form className="auth-form" onSubmit={findQuestion}>
          <label>
            간단 아이디
            <input
              autoComplete="username"
              required
              minLength="2"
              maxLength="20"
              pattern="[0-9A-Za-z가-힣_-]+"
              value={form.identifier}
              onChange={(event) => setForm({ ...form, identifier: event.target.value })}
              placeholder="기록을 저장한 아이디"
            />
          </label>
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="ui-button" disabled={busy}>{busy ? '질문 확인 중…' : '복구 질문 확인하기'}</button>
        </form> : message ? <div className="auth-form">
          <p className="auth-success" role="status">{message}</p>
          <Link className="ui-button auth-primary-link" to="/start">새 PIN으로 시작하기</Link>
        </div> : <form className="auth-form" onSubmit={resetPin}>
          <div className="auth-recovery-question">
            <span>@{form.identifier}님의 PIN 복구 질문</span>
            <strong>{recoveryQuestionLabel(question)}</strong>
          </div>
          <label>
            내가 설정한 답변
            <input
              autoComplete="off"
              required
              minLength="2"
              maxLength="100"
              value={form.recoveryAnswer}
              onChange={(event) => setForm({ ...form, recoveryAnswer: event.target.value })}
            />
          </label>
          <label>
            새 PIN
            <input
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              required
              minLength="6"
              maxLength="6"
              pattern="[0-9]{6}"
              placeholder="숫자 6자리"
              value={form.pin}
              onChange={(event) => setForm({ ...form, pin: event.target.value.replace(/\D/g, '').slice(0, 6) })}
            />
          </label>
          <label>
            새 PIN 확인
            <input
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              required
              minLength="6"
              maxLength="6"
              pattern="[0-9]{6}"
              placeholder="한 번 더 입력"
              value={form.pinConfirm}
              onChange={(event) => setForm({ ...form, pinConfirm: event.target.value.replace(/\D/g, '').slice(0, 6) })}
            />
          </label>
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="ui-button" disabled={busy}>{busy ? 'PIN 변경 중…' : '새 PIN으로 변경하기'}</button>
          <button className="start-back-button" type="button" disabled={busy} onClick={restart}>다른 아이디 입력</button>
        </form>}

        <p className="start-pin-notice">아이디까지 잊은 경우에는 이메일·휴대폰 정보를 저장하지 않기 때문에 현재 방식으로 찾을 수 없어요.</p>
        <p className="auth-switch"><Link to="/start">시작 화면으로 돌아가기</Link></p>
      </section>
    </main>
  );
}
