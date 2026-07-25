import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ChatComposer, ConversationSidebar, MessageThread } from '../features/chat/index.js';
import { applyProposalPanelChanges, toProposalView } from '../features/chat/proposalMapper.js';
import { jobApi, v2ChatApi } from '../api/index.js';
import { jobHistory } from '../features/jobs/jobHistory.js';
import '../styles/v2-chat.css';

const makeId = () => globalThis.crypto?.randomUUID?.() ?? `message-${Date.now()}`;

function toUiMessage(message) {
  return {
    id: message.id,
    sequence: message.sequence,
    role: message.role,
    content: message.content,
    attachments: message.attachment_refs?.map((attachment) => attachment.filename || attachment.id) ?? message.attachment_ids ?? [],
    evidence: message.citations?.map((citation, index) => ({
      id: citation.source_ref_id ?? `${message.id}-${index}`,
      label: citation.label || String(index + 1),
    })) ?? [],
    proposalIds: message.proposal_ids ?? [],
  };
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
  const [extracting, setExtracting] = useState(false);
  const [extractionStatus, setExtractionStatus] = useState(null);
  const [notice, setNotice] = useState('');
  const [sessionsOpen, setSessionsOpen] = useState(false);

  const openEvidence = (evidence) => setNotice(`원본 근거 ‘${evidence.label}’가 이 답변과 연결되어 있습니다.`);

  const refreshConversations = async () => {
    try { setConversations((await v2ChatApi.listConversations()).items); }
    catch (error) { setNotice(error?.message ?? '대화 기록을 불러오지 못했습니다.'); }
  };
  const refreshExtractionStatus = async (targetConversationId = conversationId.current) => {
    if (!targetConversationId) {
      setExtractionStatus(null);
      return null;
    }
    try {
      const status = await v2ChatApi.getConversationExtractionStatus(targetConversationId);
      setExtractionStatus(status);
      return status;
    } catch {
      setExtractionStatus(null);
      return null;
    }
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
          if (['pending', 'edited'].includes(candidate.status) || (candidate.status === 'approved' && candidate.type === 'create_experiences')) {
            restoredProposals[proposalId] = toProposalView(candidate);
          }
        }
        if (active) {
          setProposals(restoredProposals);
          await refreshExtractionStatus(routeConversationId);
        }
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
    const submittedFiles = [...files];
    const attachments = files.map((file) => file.name);
    const userMessage = { id: makeId(), role: 'user', content: content || '첨부한 자료를 확인해 주세요.', attachments, status: 'sending' };
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
        response = {
          message: message.content,
          messageId: message.id,
          userMessageId: message.request_message_id,
          proposal: toProposalView(rawProposal),
          proposalIds: message.proposal_ids ?? [],
        };
        if (!routeConversationId) {
          movedToConversation = true;
          navigate(`/chat/${conversationId.current}`, { replace: true });
        }
      }
      if (movedToConversation) return;
      setMessages((current) => current.map((message) => message.id === userMessage.id
        ? { ...message, id: response.userMessageId || message.id, status: 'sent' }
        : message));
      const proposalIds = response.proposal ? [response.proposal.id] : (response.proposalIds ?? []);
      setMessages((current) => [...current, { id: response.messageId || makeId(), role: 'assistant', content: response.message, proposalIds }]);
      if (response.proposal) setProposals((current) => ({ ...current, [response.proposal.id]: response.proposal }));
      await refreshConversations();
      await refreshExtractionStatus();
    } catch (error) {
      setText((current) => current || content);
      setFiles((current) => current.length ? current : submittedFiles);
      setMessages((current) => current.map((message) => message.id === userMessage.id ? { ...message, status: 'failed' } : message));
      setMessages((current) => [...current, { id: makeId(), role: 'assistant', content: error?.message ?? '응답을 만들지 못했어요. 입력은 보존되었으니 다시 시도해 주세요.' }]);
    } finally { setBusy(false); setMode('auto'); }
  };

  const start = ({ mode: nextMode, title }) => { setMode(nextMode); setText(`${title}에 대해 도와줘.`); };
  const extractRecentConversation = async () => {
    if (!conversationId.current || extracting || busy || !extractionStatus?.unprocessed_message_count) return;
    setExtracting(true);
    setNotice('');
    try {
      const result = await v2ChatApi.extractConversationExperiences(conversationId.current, {
        client_request_id: globalThis.crypto?.randomUUID?.() ?? `extract-${Date.now()}`,
      });
      const proposal = toProposalView(result.proposal);
      setMessages((current) => [...current, toUiMessage(result.message)]);
      if (proposal) setProposals((current) => ({ ...current, [proposal.id]: proposal }));
      setNotice(`최근 대화 ${result.run.message_ids.length}개를 경험 초안으로 정리했습니다. 저장 전 내용을 확인해 주세요.`);
      await Promise.all([refreshConversations(), refreshExtractionStatus()]);
    } catch (error) {
      setNotice(error?.message ?? '최근 대화를 경험으로 정리하지 못했습니다.');
      await refreshExtractionStatus();
    } finally {
      setExtracting(false);
    }
  };
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
    const result = proposal?.id ? await v2ChatApi.approveProposal(proposal.id, { base_version: proposal.version, selection: proposal.selection }) : null;
    const nextProposal = toProposalView(result?.proposal);
    if (nextProposal) {
      setProposals((current) => ({ ...current, [nextProposal.id]: nextProposal }));
    }
    if (result?.proposal?.status !== 'approved') {
      setNotice('선택한 경험을 저장했습니다. 다른 초안도 계속 검토할 수 있습니다.');
      await refreshConversations();
      await refreshExtractionStatus();
      return nextProposal;
    } else {
      setNotice(proposal.kind === 'job' ? '공고 분석 제안을 확인했습니다.' : '경험으로 확정해 저장했습니다.');
    }
    await refreshConversations();
    await refreshExtractionStatus();
    return nextProposal;
  };
  const reject = async (proposal) => {
    if (proposal?.id) await v2ChatApi.rejectProposal(proposal.id, { base_version: proposal.version });
    setProposals((current) => { const next = { ...current }; delete next[proposal.id]; return next; });
    setNotice('초안을 삭제했습니다. 대화는 그대로 유지됩니다.');
    await refreshConversations();
    await refreshExtractionStatus();
  };
  const discardRemainingProposalExperiences = async (proposal) => {
    if (!proposal?.id) return null;
    const result = await v2ChatApi.discardUnapprovedProposalExperiences(proposal.id, { base_version: proposal.version });
    if (result.status === 'rejected') {
      setProposals((current) => { const next = { ...current }; delete next[proposal.id]; return next; });
      setNotice('저장하지 않은 초안을 모두 삭제했습니다.');
      await Promise.all([refreshConversations(), refreshExtractionStatus()]);
      return null;
    }
    const nextProposal = toProposalView(result);
    setProposals((current) => ({ ...current, [nextProposal.id]: nextProposal }));
    setNotice('저장한 경험은 유지하고, 저장하지 않은 초안만 삭제했습니다.');
    await Promise.all([refreshConversations(), refreshExtractionStatus()]);
    return nextProposal;
  };
  const updateProposal = async (panel) => {
    if (!panel?.id) {
      const id = makeId();
      setProposals((current) => ({ ...current, [id]: { ...panel, id } }));
      return panel;
    }
    const updated = await v2ChatApi.updateProposal(panel.id, {
      base_version: panel.version,
      payload: applyProposalPanelChanges(proposals[panel.id], panel),
    });
    const next = toProposalView(updated);
    setProposals((current) => ({ ...current, [next.id]: next }));
    setNotice('수정한 내용을 초안에 저장했습니다.');
    return next;
  };
  const removeProposalExperience = async (proposal, sourceIndex) => {
    if (!proposal?.id) return;
    const currentProposal = proposals[proposal.id] || proposal;
    const payload = structuredClone(currentProposal.rawPayload);
    payload.experiences = (payload.experiences || []).filter((_, index) => index !== sourceIndex);
    const approvedExperienceIndexes = (currentProposal.approvedExperienceIndexes || [])
      .filter((index) => index !== sourceIndex)
      .map((index) => (index > sourceIndex ? index - 1 : index));
    if (!payload.experiences.length) {
      await v2ChatApi.rejectProposal(proposal.id, { base_version: currentProposal.version });
      setProposals((current) => { const next = { ...current }; delete next[proposal.id]; return next; });
      setNotice('초안을 삭제했습니다.');
      await Promise.all([refreshConversations(), refreshExtractionStatus()]);
      return null;
    }
    const updated = await v2ChatApi.updateProposal(proposal.id, {
      base_version: currentProposal.version,
      payload,
      approved_experience_indexes: approvedExperienceIndexes,
    });
    const next = toProposalView(updated);
    setProposals((current) => ({ ...current, [next.id]: next }));
    setNotice('선택한 초안을 삭제했습니다.');
    return next;
  };

  const startNewConversation = () => {
    conversationId.current = null;
    setMessages([]); setProposals({}); setNotice(''); setMode('auto'); setExtractionStatus(null);
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
      <header className="v2-conversation__header">
        <div><span className="v2-eyebrow">Career workspace</span><h1>Career Memory와 대화하기</h1></div>
        <div className="v2-conversation__header-actions">
          <button
            type="button"
            className="v2-extract-conversation-button"
            disabled={!extractionStatus?.unprocessed_message_count || busy || extracting}
            onClick={extractRecentConversation}
            title={extractionStatus?.unprocessed_message_count ? '마지막 정리 이후의 대화와 파일만 경험 초안으로 만듭니다.' : '새로 정리할 대화가 없습니다.'}
          >
            <span className="v2-extract-label--full">{extracting ? '경험 정리 중…' : '대화내용으로 경험 정리하기'}</span>
            <span className="v2-extract-label--short">{extracting ? '정리 중…' : '최근 대화 정리'}</span>
            {!extracting && extractionStatus?.unprocessed_message_count > 0 && <em>{extractionStatus.unprocessed_message_count}</em>}
          </button>
          <button type="button" className="v2-mobile-session-button" onClick={() => setSessionsOpen(true)}>대화 기록</button>
        </div>
      </header>
      <div className="v2-conversation__scroll" ref={scrollArea}>
        <MessageThread messages={messages} proposals={proposals} busy={busy || extracting} busyLabel={extracting ? '최근 대화내용으로 경험을 정리하고 있어요.' : '답변을 준비하고 있어요.'} onStarter={start} onEvidence={openEvidence} onApproveProposal={approve} onRejectProposal={reject} onDiscardRemainingProposalExperiences={discardRemainingProposalExperiences} onChangeProposal={updateProposal} onRemoveProposalExperience={removeProposalExperience} />
      </div>
      {notice && <p className="v2-chat-notice" role="status">{notice}</p>}
      <ChatComposer mode={mode} onModeChange={setMode} text={text} onTextChange={setText} files={files} onFilesChange={setFiles} onSubmit={submit} busy={busy || extracting} />
    </section>
    <ConversationSidebar conversations={conversations} activeId={routeConversationId} open={sessionsOpen} onClose={() => setSessionsOpen(false)} onSelect={(id) => { setSessionsOpen(false); navigate(`/chat/${id}`); }} onCreate={() => { setSessionsOpen(false); startNewConversation(); }} onRename={renameConversation} onDelete={deleteConversation} />
  </div>;
}

export default ChatPage;
