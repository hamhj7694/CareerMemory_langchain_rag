import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { RECOVERY_QUESTIONS } from '../auth/recoveryQuestions.js';
import { useAuth } from '../auth/useAuth.js';
import '../styles/auth.css';

export function LoginPage() {
  const { startGuest, startSimple } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({
    identifier: '',
    pin: '',
    displayName: '',
    recoveryQuestion: RECOVERY_QUESTIONS[0].value,
    recoveryAnswer: '',
  });
  const [profileRequired, setProfileRequired] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  const enterService = () => {
    navigate(location.state?.from?.pathname || '/chat', { replace: true });
  };

  const startExperience = async () => {
    setBusy('guest');
    setError('');
    try {
      await startGuest();
      enterService();
    } catch (requestError) {
      setError(requestError.message || '체험 공간을 준비하지 못했어요.');
    } finally {
      setBusy('');
    }
  };

  const startWithProfile = async (event) => {
    event.preventDefault();
    setBusy('simple');
    setError('');
    try {
      const result = await startSimple({
        identifier: form.identifier,
        pin: form.pin,
        ...(profileRequired ? {
          display_name: form.displayName,
          recovery_question: form.recoveryQuestion,
          recovery_answer: form.recoveryAnswer,
        } : {}),
      });
      if (result?.profile_required) {
        setProfileRequired(true);
        return;
      }
      enterService();
    } catch (requestError) {
      setError(requestError.message || '내 기록을 불러오지 못했어요.');
    } finally {
      setBusy('');
    }
  };

  const resetSimpleStart = () => {
    setForm({
      identifier: '',
      pin: '',
      displayName: '',
      recoveryQuestion: RECOVERY_QUESTIONS[0].value,
      recoveryAnswer: '',
    });
    setProfileRequired(false);
    setError('');
  };

  return (
    <main className="auth-page auth-page--start">
      <section className="start-card" aria-labelledby="start-title">
        <div className="start-intro">
          <Link className="auth-brand" to="/start"><span>CM</span>Career Memory</Link>
          <div>
            <p className="auth-eyebrow">YOUR CAREER, REMEMBERED</p>
            <h1 id="start-title">내 경험을 한곳에 모아,<br />필요할 때 꺼내 쓰는 AI</h1>
            <p className="start-description">대화와 파일에 흩어진 경험을 AI가 정리하고, 원문 근거와 함께 보관해요. 쌓아둔 경험을 채용공고 분석과 커리어 준비에 활용하세요.</p>
          </div>
          <ul className="start-features">
            <li><strong>원문 보존</strong><span>대화·문서·파일의 원본과 출처를 남겨요.</span></li>
            <li><strong>AI 경험 정리</strong><span>흩어진 경험을 구조화하고 확인 후 저장해요.</span></li>
            <li><strong>공고 매칭</strong><span>채용공고에 맞는 경험과 근거를 찾아요.</span></li>
          </ul>
          <p className="start-privacy">체험 모드의 텍스트에서는 이메일·전화번호·주소 등 감지 가능한 개인정보를 가리고 나머지를 분석합니다. 자동 감지에는 한계가 있으니 민감한 자료는 업로드하지 마세요. 일반 계정에서는 입력한 원문을 분석할 수 있습니다.</p>
        </div>

        <div className="start-actions">
          <div>
            <p className="auth-eyebrow">TRY IT NOW</p>
            <h2>가입 없이 바로 시작하세요</h2>
            <p>아무것도 입력하지 않고 Career Memory의 AI 기능을 확인할 수 있어요.</p>
          </div>
          <button className="ui-button start-guest-button" type="button" disabled={Boolean(busy)} onClick={startExperience}>
            {busy === 'guest' ? '체험 공간 준비 중…' : '바로 체험하기'}
          </button>

          <div className="start-divider"><span>또는 내 기록 이어보기</span></div>

          <form className="auth-form" onSubmit={startWithProfile}>
            {!profileRequired ? <>
              <label>
                간단 아이디
                <input
                  autoComplete="username"
                  required
                  minLength="2"
                  maxLength="20"
                  pattern="[0-9A-Za-z가-힣_-]+"
                  placeholder="한글·영문·숫자 2~20자"
                  value={form.identifier}
                  onChange={(event) => setForm({ ...form, identifier: event.target.value })}
                />
              </label>
              <label>
                PIN
                <input
                  type="password"
                  inputMode="numeric"
                  autoComplete="current-password"
                  required
                  minLength="6"
                  maxLength="6"
                  pattern="[0-9]{6}"
                  placeholder="숫자 6자리"
                  value={form.pin}
                  onChange={(event) => setForm({ ...form, pin: event.target.value.replace(/\D/g, '').slice(0, 6) })}
                />
              </label>
              <small className="start-profile-guide">기존 아이디는 바로 기록을 불러오고, 처음 쓰는 아이디는 닉네임을 한 번 더 정해요.</small>
            </> : <div className="start-nickname-step">
              <div>
                <p className="auth-eyebrow">NICE TO MEET YOU</p>
                <h3>어떻게 불러드릴까요?</h3>
                <p><strong>@{form.identifier}</strong>은 로그인 아이디로 사용합니다.</p>
              </div>
              <label>
                닉네임(호칭)
                <input
                  autoFocus
                  autoComplete="name"
                  required
                  minLength="1"
                  maxLength="40"
                  placeholder="예: 커리어 탐험가"
                  value={form.displayName}
                  onChange={(event) => setForm({ ...form, displayName: event.target.value })}
                />
              </label>
              <small>닉네임은 다른 사용자와 같아도 괜찮고, 나중에 내 기록에서 바꿀 수 있어요.</small>
              <label>
                PIN 복구 질문
                <select value={form.recoveryQuestion} onChange={(event) => setForm({ ...form, recoveryQuestion: event.target.value })}>
                  {RECOVERY_QUESTIONS.map((question) => <option key={question.value} value={question.value}>{question.label}</option>)}
                </select>
              </label>
              <label>
                복구 답변
                <input
                  autoComplete="off"
                  required
                  minLength="2"
                  maxLength="100"
                  placeholder="내가 기억할 답변 2자 이상"
                  value={form.recoveryAnswer}
                  onChange={(event) => setForm({ ...form, recoveryAnswer: event.target.value })}
                />
              </label>
              <small>PIN을 잊었을 때 선택한 질문과 답변으로 새 PIN을 설정할 수 있어요.</small>
            </div>}
            {error && <p className="auth-error" role="alert">{error}</p>}
            <button className="ui-button ui-button--secondary" disabled={Boolean(busy)}>
              {busy === 'simple'
                ? '확인 중…'
                : profileRequired ? '설정 저장하고 시작하기' : '내 기록으로 시작하기'}
            </button>
            {profileRequired && <button className="start-back-button" type="button" disabled={Boolean(busy)} onClick={resetSimpleStart}>아이디 다시 입력</button>}
            {!profileRequired && <Link className="start-recovery-link" to="/pin-recovery">PIN을 잊었어요</Link>}
          </form>
          <p className="start-pin-notice">PIN은 설정한 복구 질문으로 다시 만들 수 있어요. 이메일을 받지 않으므로 간단 아이디는 꼭 기억해 주세요.</p>
        </div>
      </section>
    </main>
  );
}
