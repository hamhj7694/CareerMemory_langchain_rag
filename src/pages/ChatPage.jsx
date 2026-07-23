import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ChatComposer, ConversationSidebar, MessageThread } from '../features/chat/index.js';
import { jobApi, v2ChatApi } from '../api/index.js';
import { jobHistory } from '../features/jobs/jobHistory.js';
import '../styles/v2-chat.css';

const makeId = () => globalThis.crypto?.randomUUID?.() ?? `message-${Date.now()}`;

function toUiProposal(proposal) {
  if (!proposal) return null;
  if (proposal.type === 'analyze_job') return {
    id: proposal.id,
    version: proposal.version,
    kind: 'job',
    title: proposal.title,
    summary: proposal.summary,
    postingTitle: proposal.payload.job_draft?.posting_title ?? '',
    companyName: proposal.payload.job_draft?.company_name ?? '',
    roleName: proposal.payload.job_draft?.role_name ?? '',
    sourceUrl: proposal.payload.job_draft?.source_url ?? '',
    postingContent: proposal.payload.job_draft?.posting_content ?? '',
    rawPayload: proposal.payload,
  };
  const experience = proposal?.payload?.experiences?.[0];
  if (!experience) return null;
  return {
    id: proposal.id,
    version: proposal.version,
    kind: 'experience',
    title: experience.title,
    domain: proposal.payload.domain?.name ?? '',
    project: proposal.payload.project?.name ?? '',
    role: experience.role ?? '',
    summary: experience.summary ?? '',
    situation: experience.situation ?? '',
    actions: experience.actions ?? [],
    results: experience.results ?? [],
    facts: experience.facts ?? [],
    skills: experience.skills ?? [],
    evidenceCount: experience.source_ref_ids?.length ?? 0,
    needsConfirmation: Boolean(experience.missing_information?.length),
    rawPayload: proposal.payload,
  };
}

function toUiMessage(message) {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    attachments: message.attachment_ids ?? [],
    evidence: message.citations?.map((citation, index) => ({ id: citation.source_ref_id ?? `${message.id}-${index}`, label: String(index + 1) })) ?? [],
    proposalIds: message.proposal_ids ?? [],
  };
}

function applyPanelChanges(proposal, panel) {
  const payload = structuredClone(proposal.rawPayload);
  if (panel.kind === 'job') {
    payload.job_draft = {
      ...(payload.job_draft ?? {}),
      posting_title: panel.postingTitle,
      company_name: panel.companyName,
      role_name: panel.roleName,
      source_url: panel.sourceUrl,
      posting_content: panel.postingContent,
    };
    return payload;
  }
  payload.domain = { ...(payload.domain ?? {}), name: panel.domain };
  payload.project = { ...(payload.project ?? {}), name: panel.project };
  payload.experiences = [...(payload.experiences ?? [])];
  payload.experiences[0] = {
    ...(payload.experiences[0] ?? {}),
    title: panel.title,
    role: panel.role,
    summary: panel.summary,
    situation: panel.situation,
    actions: panel.actions,
    results: panel.results,
    facts: panel.facts,
    skills: panel.skills,
  };
  return payload;
}

export function ChatPage({ onSend }) {
  const { conversationId: routeConversationId } = useParams();
  const navigate = useNavigate();
  const conversationId = useRef(routeConversationId ?? null);
  const scrollArea = useRef(null);
  const [mode, setMode] = useState('auto');
  const [text, setText] = useState('');
  const [files, setFiles] = useState([]);
  const [messages, setMessages] = useState([]);
  const [proposals, setProposals] = useState({});
  const [conversations, setConversations] = useState([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [sessionsOpen, setSessionsOpen] = useState(false);

  const refreshConversations = async () => {
    try { setConversations((await v2ChatApi.listConversations()).items); }
    catch (error) { setNotice(error?.message ?? '대화 기록을 불러오지 못했습니다.'); }
  };
  useEffect(() => { refreshConversations(); }, []);

  useEffect(() => {
    const area = scrollArea.current;
    if (area) area.scrollTo({ top: area.scrollHeight, behavior: 'smooth' });
  }, [messages, busy]);

  useEffect(() => {
    conversationId.current = routeConversationId ?? null;
    if (!routeConversationId) return undefined;
    let active = true;
    const restore = async () => {
      setBusy(true);
      setNotice('');
      try {
        await v2ChatApi.getConversation(routeConversationId);
        const result = await v2ChatApi.listMessages(routeConversationId);
        if (!active) return;
        setMessages(result.items.map(toUiMessage));
        const proposalIds = result.items.flatMap((message) => message.proposal_ids ?? []).reverse();
        const restoredProposals = {};
        for (const proposalId of proposalIds) {
          const candidate = await v2ChatApi.getProposal(proposalId);
          if (['pending', 'edited'].includes(candidate.status)) {
            restoredProposals[proposalId] = toUiProposal(candidate);
          }
        }
        if (active) setProposals(restoredProposals);
      } catch (error) {
        if (active) {
          setMessages([]);
          setProposals({});
          if (error?.code === 'NOT_FOUND') {
            conversationId.current = null;
            setNotice('');
            navigate('/chat', { replace: true });
          } else {
            setNotice(error?.message ?? '기존 대화를 불러오지 못했습니다.');
          }
        }
      } finally {
        if (active) setBusy(false);
      }
      refreshConversations();
    };
    restore();
    return () => { active = false; };
  }, [routeConversationId, navigate]);

  const submit = async () => {
    const content = text.trim();
    if (busy || (!content && files.length === 0)) return;
    const attachments = files.map((file) => file.name);
    const userMessage = { id: makeId(), role: 'user', content: content || '첨부한 자료를 확인해 주세요.', attachments };
    setMessages((current) => [...current, userMessage]);
    setText(''); setFiles([]); setBusy(true); setNotice('');
    try {
      let response;
      let movedToConversation = false;
      if (onSend) {
        response = await onSend({ mode, content, files });
      } else {
        if (!conversationId.current) conversationId.current = (await v2ChatApi.createConversation({ title: (content || files[0]?.name || '새 대화').slice(0, 28) })).id;
        const uploaded = files.length ? await v2ChatApi.uploadAttachments(files) : [];
        const message = await v2ChatApi.sendMessage(conversationId.current, {
          content,
          intent: mode,
          attachment_ids: uploaded.map(({ id }) => id),
        });
        const rawProposal = message.proposal_ids?.[0] ? await v2ChatApi.getProposal(message.proposal_ids[0]) : null;
        response = { message: message.content, proposal: toUiProposal(rawProposal), proposalIds: message.proposal_ids ?? [] };
        if (!routeConversationId) {
          movedToConversation = true;
          navigate(`/chat/${conversationId.current}`, { replace: true });
        }
      }
      if (movedToConversation) return;
      const proposalIds = response.proposal ? [response.proposal.id] : (response.proposalIds ?? []);
      setMessages((current) => [...current, { id: makeId(), role: 'assistant', content: response.message, proposalIds }]);
      if (response.proposal) setProposals((current) => ({ ...current, [response.proposal.id]: response.proposal }));
      await refreshConversations();
    } catch (error) {
      setMessages((current) => [...current, { id: makeId(), role: 'assistant', content: error?.message ?? '응답을 만들지 못했어요. 입력은 보존되었으니 다시 시도해 주세요.' }]);
    } finally { setBusy(false); setMode('auto'); }
  };

  const start = ({ mode: nextMode, title }) => { setMode(nextMode); setText(`${title}에 대해 도와줘.`); };
  const approve = async (proposal) => {
    if (proposal?.kind === 'job') {
      const sourceUrl = proposal.sourceUrl?.trim();
      if (!proposal.postingContent?.trim()) throw new Error('채용공고 원문을 입력해 주세요.');
      if (sourceUrl && !/^https?:\/\/\S+$/i.test(sourceUrl)) throw new Error('공고 링크는 http:// 또는 https://로 시작해야 합니다.');
      const analyzed = await jobApi.analyze({
        postingTitle: proposal.postingTitle?.trim() || undefined,
        companyName: proposal.companyName?.trim() || undefined,
        roleName: proposal.roleName?.trim() || undefined,
        sourceUrl: sourceUrl || undefined,
        postingContent: proposal.postingContent.trim(),
        coverLetterQuestions: [],
      });
      const savedJob = jobHistory.save(analyzed, {
        postingTitle: proposal.postingTitle?.trim() || '',
        companyName: proposal.companyName?.trim() || '',
        roleName: proposal.roleName?.trim() || '',
        sourceUrl: sourceUrl || '',
        postingContent: proposal.postingContent.trim(),
      });
      if (proposal.id) await v2ChatApi.approveProposal(proposal.id, { base_version: proposal.version });
      setProposals((current) => { const next = { ...current }; delete next[proposal.id]; return next; });
      await refreshConversations();
      navigate(`/jobs/${savedJob.jobId}`, { state: { job: savedJob } });
      return;
    }
    if (proposal?.id) await v2ChatApi.approveProposal(proposal.id, { base_version: proposal.version });
    setProposals((current) => { const next = { ...current }; delete next[proposal.id]; return next; });
    setNotice(proposal.kind === 'job' ? '공고 분석 제안을 확인했습니다.' : '경험으로 확정해 저장했습니다.');
    await refreshConversations();
  };
  const reject = async (proposal) => {
    if (proposal?.id) await v2ChatApi.rejectProposal(proposal.id, { base_version: proposal.version });
    setProposals((current) => { const next = { ...current }; delete next[proposal.id]; return next; });
    setNotice('초안을 삭제했습니다. 대화는 그대로 유지됩니다.');
    await refreshConversations();
  };
  const updateProposal = async (panel) => {
    if (!panel?.id) {
      const id = makeId();
      setProposals((current) => ({ ...current, [id]: { ...panel, id } }));
      return panel;
    }
    const updated = await v2ChatApi.updateProposal(panel.id, {
      base_version: panel.version,
      payload: applyPanelChanges(proposals[panel.id], panel),
    });
    const next = toUiProposal(updated);
    setProposals((current) => ({ ...current, [next.id]: next }));
    setNotice('수정한 내용을 초안에 저장했습니다.');
    return next;
  };

  const startNewConversation = () => {
    conversationId.current = null;
    setMessages([]); setProposals({}); setNotice(''); setMode('auto');
    if (routeConversationId) navigate('/chat');
  };
  const renameConversation = async (conversation) => {
    const title = window.prompt('대화 제목 변경', conversation.title || '새 대화');
    if (!title?.trim() || title.trim() === conversation.title) return;
    await v2ChatApi.updateConversation(conversation.id, { title: title.trim() });
    await refreshConversations();
  };
  const deleteConversation = async (conversation) => {
    if (!window.confirm(`‘${conversation.title || '새 대화'}’ 대화를 삭제할까요?`)) return;
    await v2ChatApi.deleteConversation(conversation.id);
    if (conversation.id === conversationId.current) startNewConversation();
    await refreshConversations();
  };

  return <div className="v2-chat-page">
    <section className="v2-conversation" aria-label="Career Memory 대화">
      <header className="v2-conversation__header"><div><span className="v2-eyebrow">Career workspace</span><h1>Career Memory와 대화하기</h1></div><button type="button" className="v2-mobile-session-button" onClick={() => setSessionsOpen(true)}>대화 기록</button></header>
      <div className="v2-conversation__scroll" ref={scrollArea}>
        <MessageThread messages={messages} proposals={proposals} busy={busy} onStarter={start} onEvidence={() => setNotice('연결된 근거를 확인합니다.')} onApproveProposal={approve} onRejectProposal={reject} onChangeProposal={updateProposal} />
      </div>
      {notice && <p className="v2-chat-notice" role="status">{notice}</p>}
      <ChatComposer mode={mode} onModeChange={setMode} text={text} onTextChange={setText} files={files} onFilesChange={setFiles} onSubmit={submit} busy={busy} />
    </section>
    <ConversationSidebar conversations={conversations} activeId={routeConversationId} open={sessionsOpen} onClose={() => setSessionsOpen(false)} onSelect={(id) => { setSessionsOpen(false); navigate(`/chat/${id}`); }} onCreate={() => { setSessionsOpen(false); startNewConversation(); }} onRename={renameConversation} onDelete={deleteConversation} />
  </div>;
}

export default ChatPage;
