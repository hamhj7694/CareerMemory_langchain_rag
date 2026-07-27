import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ChatComposer, ConversationSidebar, MessageThread } from '../features/chat/index.js';
import { applyProposalPanelChanges, toProposalView } from '../features/chat/proposalMapper.js';
import { toEmbeddedProposalView, toUiMessage } from '../features/chat/chatMessageMapper.js';
import { chatExperienceApi, experienceTrashApi, jobApi, v2ChatApi } from '../api/index.js';
import { AnalysisProgress } from '../components/common/AnalysisProgress.jsx';
import '../styles/v2-chat.css';

const makeId = () => globalThis.crypto?.randomUUID?.() ?? `message-${Date.now()}`;

export function ChatPage({ onSend }) {
  const { conversationId: routeConversationId } = useParams();
  const navigate = useNavigate();
  const conversationId = useRef(routeConversationId ?? null);
  // 사용자가 새 대화를 직접 선택한 경우에는 최신 대화 자동 열기를 한 번 건너뛴다.
  const keepNewConversationOpen = useRef(false);
  const scrollArea = useRef(null);
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
  const extractionRequestInFlight = useRef(false);

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
  useEffect(() => {
    let active = true;

    const openLatestConversation = async () => {
      try {
        const items = (await v2ChatApi.listConversations()).items;
        if (!active) return;
        setConversations(items);

        // 주소에 대화 ID가 없는 최초 진입이라면 가장 최근 대화를 연다.
        // 저장된 대화가 없거나 사용자가 새 대화를 누른 경우에는 빈 채팅을 유지한다.
        if (!routeConversationId && keepNewConversationOpen.current) {
          keepNewConversationOpen.current = false;
          return;
        }
        if (!routeConversationId && items[0]?.id) {
          navigate(`/chat/${items[0].id}`, { replace: true });
        }
      } catch (error) {
        if (active) setNotice(error?.message ?? '대화 기록을 불러오지 못했습니다.');
      }
    };

    openLatestConversation();
    return () => { active = false; };
  }, [routeConversationId, navigate]);

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
        let result = await v2ChatApi.listMessages(routeConversationId);
        if (!active) return;
        const restoredMessages = result.items.map(toUiMessage);
        setMessages(restoredMessages);
        const proposalIds = restoredMessages
          .flatMap((message) => message.proposalIds || [])
          .reverse();
        const restoredProposals = Object.fromEntries(
          restoredMessages
            .flatMap((message) => message.embeddedProposals || [])
            .filter((proposal) => proposal.status !== 'rejected')
            .map((proposal) => [proposal.id, proposal]),
        );
        for (const proposalId of proposalIds) {
          if (restoredProposals[proposalId]) continue;
          const candidate = await v2ChatApi.getProposal(proposalId);
          if (['pending', 'edited'].includes(candidate.status) || (candidate.status === 'approved' && candidate.type === 'create_experiences')) {
            restoredProposals[proposalId] = toProposalView(candidate);
          }
        }
        if (active) {
          setProposals(restoredProposals);
          await refreshExtractionStatus(routeConversationId);
        }

        // 다른 화면에 있는 동안 생성 중이던 답변이 있다면
        // DB에 저장되는 중간 내용과 완료 상태를 주기적으로 다시 불러온다.
        const isGenerating = (message) => (
          message?.role === 'assistant'
          && ['queued', 'processing', 'streaming'].includes(message.status)
        );
        while (active && isGenerating(result.items.at(-1))) {
          await new Promise((resolve) => setTimeout(resolve, 750));
          result = await v2ChatApi.listMessages(routeConversationId);
          if (active) setMessages(result.items.map(toUiMessage));
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
    let submittedConversationId = conversationId.current;
    const submittedFiles = [...files];
    const attachments = files.map((file) => file.name);
    const userMessage = { id: makeId(), role: 'user', content: content || '첨부한 자료를 확인해 주세요.', attachments, status: 'sending' };
    setMessages((current) => [...current, userMessage]);
    setText(''); setFiles([]); setBusy(true); setNotice('');
    try {
      let response;
      let movedToConversation = false;
      if (onSend) {
        response = await onSend({ mode: 'auto', content, files });
      } else {
        if (!conversationId.current) conversationId.current = (await v2ChatApi.createConversation({ title: (content || files[0]?.name || '새 대화').slice(0, 28) })).id;
        submittedConversationId = conversationId.current;
        const uploaded = files.length ? await v2ChatApi.uploadAttachments(files) : [];
        let completedMessage = null;
        let streamedAssistantMessageId = null;
        for await (const event of v2ChatApi.streamMessage(conversationId.current, {
          content,
          intent: 'auto',
          attachment_ids: uploaded.map(({ id }) => id),
        })) {
          if (event.type === 'message.accepted') {
            streamedAssistantMessageId = event.assistant_message_id;
            if (conversationId.current === submittedConversationId) {
              setMessages((current) => [
                ...current.map((message) => message.id === userMessage.id
                  ? { ...message, id: event.user_message.id, status: 'sent' }
                  : message),
                {
                  id: event.assistant_message_id,
                  role: 'assistant',
                  content: '',
                  status: 'streaming',
                  proposalIds: [],
                },
              ]);
            }
          } else if (event.type === 'assistant.delta') {
            if (conversationId.current === submittedConversationId) {
              setMessages((current) => current.map((message) => (
                message.id === event.message_id
                  ? { ...message, content: `${message.content}${event.delta}` }
                  : message
              )));
            }
          } else if (event.type === 'proposal.created') {
            const streamedProposal = toEmbeddedProposalView(event.proposal, {
              messageId: streamedAssistantMessageId,
              conversationId: submittedConversationId,
            });
            if (streamedProposal && conversationId.current === submittedConversationId) {
              setProposals((current) => ({
                ...current,
                [streamedProposal.id]: streamedProposal,
              }));
            }
          } else if (event.type === 'message.completed') {
            completedMessage = event.message;
            const completedUiMessage = toUiMessage(event.message);
            if (conversationId.current === submittedConversationId) {
              setMessages((current) => current.map((message) => (
                message.id === event.message.id
                  ? { ...completedUiMessage, status: 'completed' }
                  : message
              )));
              setProposals((current) => completedUiMessage.embeddedProposals.reduce(
                (next, proposal) => ({ ...next, [proposal.id]: proposal }),
                current,
              ));
            }
          } else if (event.type === 'message.failed') {
            throw new Error(event.error?.message || 'AI 답변 생성에 실패했습니다.');
          }
        }
        if (!completedMessage) throw new Error('스트리밍이 완료되기 전에 연결이 종료되었습니다.');
        response = { streamed: true };
        if (!routeConversationId && conversationId.current === submittedConversationId) {
          movedToConversation = true;
          navigate(`/chat/${conversationId.current}`, { replace: true });
        }
      }
      if (movedToConversation) return;
      if (response.streamed) {
        await refreshConversations();
        await refreshExtractionStatus();
        return;
      }
      setMessages((current) => current.map((message) => message.id === userMessage.id
        ? { ...message, id: response.userMessageId || message.id, status: 'sent' }
        : message));
      const proposalIds = response.proposal ? [response.proposal.id] : (response.proposalIds ?? []);
      setMessages((current) => [...current, { id: response.messageId || makeId(), role: 'assistant', content: response.message, proposalIds }]);
      if (response.proposal) setProposals((current) => ({ ...current, [response.proposal.id]: response.proposal }));
      await refreshConversations();
      await refreshExtractionStatus();
    } catch (error) {
      if (conversationId.current === submittedConversationId) {
        setText((current) => current || content);
        setFiles((current) => current.length ? current : submittedFiles);
        setMessages((current) => current.map((message) => message.id === userMessage.id ? { ...message, status: 'failed' } : message));
        setMessages((current) => [...current, { id: makeId(), role: 'assistant', content: error?.message ?? '응답을 만들지 못했어요. 입력은 보존되었으니 다시 시도해 주세요.' }]);
      }
    } finally { setBusy(false); }
  };

  const start = ({ prompt }) => { setText(prompt); };
  const extractRecentConversation = async () => {
    if (!conversationId.current || extractionRequestInFlight.current || extracting || busy || !extractionStatus?.unprocessed_message_count) return;
    extractionRequestInFlight.current = true;
    setExtracting(true);
    setNotice('');
    try {
      const result = await v2ChatApi.extractConversationExperiences(conversationId.current, {
        client_request_id: globalThis.crypto?.randomUUID?.() ?? `extract-${Date.now()}`,
      });
      const resultMessage = toUiMessage(result.message);
      const proposal = resultMessage.embeddedProposals
        .find((item) => item.id === result.proposal?.id)
        ?? (result.proposal ? {
          ...toProposalView(result.proposal),
          chatMessageId: resultMessage.id,
          conversationId: conversationId.current,
        } : null);
      setMessages((current) => [...current, resultMessage]);
      if (proposal) setProposals((current) => ({ ...current, [proposal.id]: proposal }));
      const processedMessageCount = result.proposal?.analysis_scope?.message_count
        ?? result.run?.message_ids?.length
        ?? extractionStatus?.unprocessed_message_count
        ?? 0;
      setNotice(`최근 대화 ${processedMessageCount}개를 경험 초안으로 정리했습니다. 저장 전 내용을 확인해 주세요.`);
      await Promise.all([refreshConversations(), refreshExtractionStatus()]);
    } catch (error) {
      setNotice(error?.message ?? '최근 대화를 경험으로 정리하지 못했습니다.');
      await refreshExtractionStatus();
    } finally {
      extractionRequestInFlight.current = false;
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
      if (proposal.id) await v2ChatApi.approveProposal(proposal.id, { base_version: proposal.version });
      setProposals((current) => { const next = { ...current }; delete next[proposal.id]; return next; });
      await refreshConversations();
      navigate(`/jobs/${analyzed.jobId}`, { state: { job: analyzed } });
      return;
    }
    if (proposal?.chatMessageId) {
      const requestedDraftId = proposal.selection?.draft_id;
      const draftIndex = requestedDraftId
        ? proposal.experiences.findIndex((item) => item.draft_id === requestedDraftId)
        : -1;
      const index = draftIndex >= 0 ? draftIndex : (proposal.selection?.experience_indexes?.[0] ?? 0);
      const item = proposal.experiences[index];
      if (!item || item.approved) return proposal;
      const result = await chatExperienceApi.approveProposalExperience(
        proposal.conversationId,
        proposal.chatMessageId,
        {
          version: proposal.version,
          draftId: item.draft_id,
          experienceIndex: index,
        },
      );
      const nextProposal = {
        ...toProposalView(result.proposal),
        chatMessageId: proposal.chatMessageId,
        conversationId: proposal.conversationId,
      };
      setProposals((current) => ({ ...current, [nextProposal.id]: nextProposal }));
      const approvedCount = nextProposal.experiences.filter((entry) => entry.approved).length;
      setNotice(approvedCount === nextProposal.experiences.length
        ? '경험으로 확정해 저장했습니다.'
        : '선택한 경험을 저장했습니다. 다른 초안도 계속 검토할 수 있습니다.');
      return nextProposal;
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
    if (proposal?.kind === 'experience') {
      const pendingDrafts = (proposal.experiences || []).filter((item) => !item.approved);
      await Promise.all(pendingDrafts.map((draft) => experienceTrashApi.create({
        status: 'deleted',
        reason: '대화형 챗봇에서 삭제한 경험 초안',
        draft,
      })));
    }
    if (proposal?.chatMessageId) {
      await chatExperienceApi.updateProposal(proposal.conversationId, proposal.chatMessageId, {
        version: proposal.version,
        payload: proposal.rawPayload,
        approvedExperienceIndexes: proposal.approvedExperienceIndexes || [],
        status: 'rejected',
      });
    } else if (proposal?.id) {
      await v2ChatApi.rejectProposal(proposal.id, { base_version: proposal.version });
    }
    setProposals((current) => { const next = { ...current }; delete next[proposal.id]; return next; });
    setMessages((current) => current.map((message) => (
      message.proposalIds?.includes(proposal.id)
        ? {
          ...message,
          proposalIds: message.proposalIds.filter((proposalId) => proposalId !== proposal.id),
          embeddedProposals: (message.embeddedProposals || [])
            .filter((item) => item.id !== proposal.id),
        }
        : message
    )));
    setNotice('초안을 삭제했습니다. 대화는 그대로 유지됩니다.');
    await refreshConversations();
    await refreshExtractionStatus();
  };
  const discardRemainingProposalExperiences = async (proposal) => {
    if (!proposal?.id) return null;
    const pendingDrafts = (proposal.experiences || []).filter((item) => !item.approved);
    await Promise.all(pendingDrafts.map((draft) => experienceTrashApi.create({
      status: 'deleted',
      reason: '대화형 챗봇에서 나머지 초안을 삭제함',
      draft,
    })));
    if (proposal.chatMessageId) {
      const approvedDrafts = (proposal.experiences || []).filter((item) => item.approved);
      const payload = applyProposalPanelChanges(proposal, { ...proposal, experiences: approvedDrafts });
      const updated = await chatExperienceApi.updateProposal(proposal.conversationId, proposal.chatMessageId, {
        version: proposal.version,
        payload,
        approvedExperienceIndexes: approvedDrafts.map((_, index) => index),
        status: approvedDrafts.length ? 'approved' : 'rejected',
      });
      if (!approvedDrafts.length) {
        setProposals((current) => { const next = { ...current }; delete next[proposal.id]; return next; });
        return null;
      }
      const nextProposal = { ...toProposalView(updated), chatMessageId: proposal.chatMessageId, conversationId: proposal.conversationId };
      setProposals((current) => ({ ...current, [nextProposal.id]: nextProposal }));
      return nextProposal;
    }
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
    if (panel.chatMessageId) {
      const updated = await chatExperienceApi.updateProposal(panel.conversationId, panel.chatMessageId, {
        version: panel.version,
        payload: applyProposalPanelChanges(proposals[panel.id], panel),
        approvedExperienceIndexes: panel.approvedExperienceIndexes || [],
        status: 'edited',
      });
      const next = { ...toProposalView(updated), chatMessageId: panel.chatMessageId, conversationId: panel.conversationId };
      setProposals((current) => ({ ...current, [next.id]: next }));
      setNotice('수정한 내용을 초안에 저장했습니다.');
      return next;
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
    const removedDraft = (currentProposal.experiences || [])[sourceIndex];
    if (removedDraft && !removedDraft.approved) {
      await experienceTrashApi.create({
        status: 'deleted',
        reason: '대화형 챗봇에서 선택하여 삭제한 초안',
        draft: removedDraft,
      });
    }
    const payload = structuredClone(currentProposal.rawPayload);
    payload.experiences = (payload.experiences || []).filter((_, index) => index !== sourceIndex);
    const approvedExperienceIndexes = (currentProposal.approvedExperienceIndexes || [])
      .filter((index) => index !== sourceIndex)
      .map((index) => (index > sourceIndex ? index - 1 : index));
    if (!payload.experiences.length) {
      if (proposal.chatMessageId) {
        await chatExperienceApi.updateProposal(proposal.conversationId, proposal.chatMessageId, {
          version: currentProposal.version,
          payload,
          approvedExperienceIndexes: [],
          status: 'rejected',
        });
      } else {
        await v2ChatApi.rejectProposal(proposal.id, { base_version: currentProposal.version });
      }
      setProposals((current) => { const next = { ...current }; delete next[proposal.id]; return next; });
      setNotice('초안을 삭제했습니다.');
      await Promise.all([refreshConversations(), refreshExtractionStatus()]);
      return null;
    }
    const updated = proposal.chatMessageId
      ? await chatExperienceApi.updateProposal(proposal.conversationId, proposal.chatMessageId, {
          version: currentProposal.version,
          payload,
          approvedExperienceIndexes,
          status: 'edited',
        })
      : await v2ChatApi.updateProposal(proposal.id, {
          base_version: currentProposal.version,
          payload,
          approved_experience_indexes: approvedExperienceIndexes,
        });
    const next = {
      ...toProposalView(updated),
      ...(proposal.chatMessageId ? { chatMessageId: proposal.chatMessageId, conversationId: proposal.conversationId } : {}),
    };
    setProposals((current) => ({ ...current, [next.id]: next }));
    setNotice('선택한 초안을 삭제했습니다.');
    return next;
  };

  const startNewConversation = () => {
    conversationId.current = null;
    setMessages([]); setProposals({}); setNotice(''); setExtractionStatus(null);
    if (routeConversationId) {
      keepNewConversationOpen.current = true;
      navigate('/chat');
    }
  };
  const latestMessage = messages.at(-1);
  const showThinking = extracting || (
    busy
    && !(
      latestMessage?.role === 'assistant'
      && ['completed', 'failed'].includes(latestMessage.status)
    )
  );
  const renameConversation = async (conversation) => {
    const title = window.prompt('대화 제목 변경', conversation.title || '새 대화');
    if (!title?.trim() || title.trim() === conversation.title) return;
    await v2ChatApi.updateConversation(conversation.id, {
      title: title.trim(),
      base_version: conversation.version,
    });
    await refreshConversations();
  };
  const deleteConversation = async (conversation) => {
    if (!window.confirm(`‘${conversation.title || '새 대화'}’ 대화를 삭제할까요?`)) return;
    await v2ChatApi.deleteConversation(conversation.id, {
      version: conversation.version,
    });
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
        <MessageThread messages={messages} proposals={proposals} busy={showThinking} busyLabel={extracting ? '최근 대화내용으로 경험을 정리하고 있어요.' : '답변을 준비하고 있어요.'} onStarter={start} onEvidence={openEvidence} onOpenJobAnalysis={(jobId) => navigate(`/jobs/${jobId}`)} onApproveProposal={approve} onRejectProposal={reject} onDiscardRemainingProposalExperiences={discardRemainingProposalExperiences} onChangeProposal={updateProposal} onRemoveProposalExperience={removeProposalExperience} />
      </div>
      <div className="v2-analysis-progress">
        <AnalysisProgress
          active={extracting}
          hasFiles={false}
          kind="experience"
        />
      </div>
      {notice && <p className="v2-chat-notice" role="status">{notice}</p>}
      <ChatComposer text={text} onTextChange={setText} files={files} onFilesChange={setFiles} onSubmit={submit} busy={busy || extracting} />
    </section>
    <ConversationSidebar conversations={conversations} activeId={routeConversationId} open={sessionsOpen} onClose={() => setSessionsOpen(false)} onSelect={(id) => { setSessionsOpen(false); navigate(`/chat/${id}`); }} onCreate={() => { setSessionsOpen(false); startNewConversation(); }} onRename={renameConversation} onDelete={deleteConversation} />
  </div>;
}

export default ChatPage;
