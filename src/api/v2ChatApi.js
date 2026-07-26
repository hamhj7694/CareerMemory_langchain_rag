import { AppError } from './AppError.js';
import { apiConfig } from './config.js';
import { mockV2Store as store, nextId, resetMockV2Store, snapshot, timestamp } from './v2/mockV2Store.js';
import { v2ChatHttpApi } from './v2ChatHttpApi.js';
import { fingerprintFile, sha256ArrayBuffer } from '../utils/fileFingerprint.js';

const wait = (milliseconds = 80) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function fail(code, message, status = 400, details) {
  throw new AppError({ code, message, status, details, retryable: false });
}

function find(collection, resourceId, label) {
  const resource = collection.find((item) => item.id === resourceId);
  if (!resource) fail('NOT_FOUND', `${label} 항목을 찾을 수 없습니다.`, 404);
  return resource;
}

function resolveIntents(requestedIntent) {
  if (requestedIntent === 'experience' || requestedIntent === 'job') return [requestedIntent];
  return ['auto'];
}

const cleanText = (value) => String(value || '').replace(/\r\n/g, '\n').trim();
const firstMeaningfulLine = (value) => cleanText(value).split('\n').map((line) => line.trim()).find(Boolean) || '';
const cleanStructureName = (value) => String(value || '')
  .normalize('NFKC')
  .replace(/[\u200B-\u200D\uFEFF]/g, '')
  .trim()
  .replace(/\s+/g, ' ');
const structureNameKey = (value) => cleanStructureName(value).toLocaleLowerCase('ko-KR');

function reconcileStructureStore() {
  const domains = [];
  const domainByName = new Map();
  const domainIdMap = new Map();

  store.domains.forEach((source) => {
    const name = cleanStructureName(source.name) || '미분류 경험';
    const key = structureNameKey(name) || `id:${source.id}`;
    let domain = domainByName.get(key);
    if (!domain) {
      domain = { ...source, name };
      domains.push(domain);
      domainByName.set(key, domain);
    }
    domainIdMap.set(source.id, domain.id);
  });

  const projects = [];
  const projectByName = new Map();
  const projectIdMap = new Map();
  store.projects.forEach((source) => {
    const domainId = domainIdMap.get(source.domain_id) || source.domain_id;
    const name = cleanStructureName(source.name) || '프로젝트·활동 미분류';
    const key = `${domainId}:${structureNameKey(name) || `id:${source.id}`}`;
    let project = projectByName.get(key);
    if (!project) {
      project = { ...source, domain_id: domainId, name };
      projects.push(project);
      projectByName.set(key, project);
    }
    projectIdMap.set(source.id, project.id);
  });

  store.experiences.forEach((experience) => {
    const sourceProjectId = experience.project?.id || experience.project_id;
    const sourceDomainId = experience.domain?.id || experience.domain_id;
    const projectId = sourceProjectId ? (projectIdMap.get(sourceProjectId) || sourceProjectId) : '';
    const sourceDomainName = cleanStructureName(experience.domain?.name || experience.domain_name || experience.domainName);
    const sourceProjectName = cleanStructureName(experience.project?.name || experience.project_name || experience.projectName);
    let project = projects.find((item) => item.id === projectId);
    const domainId = project?.domain_id || (sourceDomainId ? (domainIdMap.get(sourceDomainId) || sourceDomainId) : '');
    let domain = domains.find((item) => item.id === domainId)
      || domainByName.get(structureNameKey(sourceDomainName));

    if (!domain) {
      const name = sourceDomainName || '미분류 경험';
      domain = {
        id: nextId('DOM'),
        name,
        created_at: experience.created_at || timestamp(),
        updated_at: timestamp(),
        version: 1,
      };
      domains.push(domain);
      domainByName.set(structureNameKey(name), domain);
    }

    const projectName = sourceProjectName || '프로젝트·활동 미분류';
    if (!project) {
      project = projectByName.get(`${domain.id}:${structureNameKey(projectName)}`);
    }
    if (!project) {
      project = {
        id: nextId('PROJ'),
        domain_id: domain.id,
        name: projectName,
        organization: experience.project?.organization || experience.organization || '',
        created_at: experience.created_at || timestamp(),
        updated_at: timestamp(),
        version: 1,
      };
      projects.push(project);
      projectByName.set(`${domain.id}:${structureNameKey(projectName)}`, project);
    } else if (project.domain_id !== domain.id && !domains.some((item) => item.id === project.domain_id)) {
      project.domain_id = domain.id;
    }

    if (sourceDomainId) domainIdMap.set(sourceDomainId, domain.id);
    if (sourceProjectId) projectIdMap.set(sourceProjectId, project.id);
    experience.domain = { id: domain.id, name: domain.name };
    experience.domain_id = domain.id;
    experience.project = { id: project.id, name: project.name, organization: project.organization || '' };
    experience.project_id = project.id;
  });

  store.domains = domains;
  store.projects = projects;
  return { domainIdMap, projectIdMap };
}

function splitExperienceBlocks(value) {
  const text = cleanText(value);
  if (!text) return [];
  const paragraphs = text.split(/\n\s*\n+/).map(cleanText).filter(Boolean);
  const experienceLikeParagraphs = paragraphs.filter((paragraph) => !/^(?:요약|상황|행동|결과|역할|역량|스킬|사실|확인된 사실|근거에서 확인된 내용)\s*[:：]/i.test(firstMeaningfulLine(paragraph)) && !/^(?:[-*•]|\d+[.)])\s+/.test(firstMeaningfulLine(paragraph)));
  if (paragraphs.length > 1 && experienceLikeParagraphs.length >= 2) return paragraphs;
  const lines = text.split('\n');
  const starts = lines.reduce((indexes, line, index) => {
    if (/^(?:#{1,3}\s+|(?:경험|사례|프로젝트|프로젝트·활동)\s*(?:\d+)?\s*[:：]|\d+[.)]\s+(?=경험|프로젝트|사례))/.test(line.trim())) indexes.push(index);
    return indexes;
  }, []);
  if (starts.length < 2) return [text];
  return starts.map((start, index) => cleanText(lines.slice(start, starts[index + 1] ?? lines.length).join('\n'))).filter(Boolean);
}

function parseField(text, labels) {
  const labelPattern = labels.join('|');
  const match = cleanText(text).match(new RegExp(`(?:^|\\n)\\s*(?:${labelPattern})\\s*[:：]\\s*([\\s\\S]*?)(?=\\n\\s*(?:요약|상황|행동|결과|역할|역량|스킬|사실|경험 분류|프로젝트·활동)\\s*[:：]|$)`, 'i'));
  return match?.[1]?.trim() || '';
}

function listField(value) {
  return cleanText(value).split('\n').map((line) => line.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, '').trim()).filter(Boolean);
}

function inferDomain(text) {
  const source = cleanText(text);
  const explicit = source.match(/(?:경험 분류|분류)\s*[:：]\s*([^\n]+)/);
  if (explicit?.[1]) return explicit[1].trim();
  if (/직장|회사|업무|서비스|운영|제품|전환|대시보드/.test(source)) return '직장 경험';
  if (/교육|학습|수업|분석 과정|강의|연구/.test(source)) return '교육·학습';
  if (/사이드|커뮤니티|개인 프로젝트|앱 출시/.test(source)) return '사이드 프로젝트';
  if (/멘토|봉사|대외|동아리/.test(source)) return '대외 활동';
  return '새 경험 분류';
}

function inferProject(text, index, filename = '') {
  const source = cleanText(text);
  const explicit = source.match(/(?:프로젝트·활동|프로젝트|활동)\s*[:：]\s*([^\n]+)/);
  if (explicit?.[1]) return explicit[1].trim();
  const title = firstMeaningfulLine(source).replace(/^(?:#{1,3}\s+|\d+[.)]\s+)/, '').trim();
  if (title && !/^(요약|상황|행동|결과|역할|역량|사실)\s*[:：]?$/i.test(title)) return title.slice(0, 48);
  if (filename) return filename.replace(/\.[^.]+$/, '').trim() || `새 프로젝트 ${index + 1}`;
  return `새 프로젝트 ${index + 1}`;
}

function sourceForMessage(messageId, content, attachmentIds) {
  const refs = [];
  if (cleanText(content)) {
    const id = `SRC-${messageId}`;
    const source = store.sources.find((item) => item.id === id)
      || { id, source_type: 'message_text', title: '대화 원문', message_id: messageId, text: cleanText(content), captured_at: timestamp(), linked_facts: [] };
    if (!store.sources.some((item) => item.id === id)) store.sources.push(source);
    refs.push(source);
  }
  attachmentIds.forEach((attachmentId) => {
    const attachment = store.attachments.find((item) => item.id === attachmentId);
    if (!attachment) return;
    const source = store.sources.find((item) => item.id === attachment.id) || {
      id: attachment.id,
      source_type: 'file',
      title: attachment.filename,
      filename: attachment.filename,
      mime_type: attachment.mime_type,
      size_bytes: attachment.size_bytes,
      content_hash: attachment.content_hash,
      original_attachment_id: attachment.original_attachment_id,
      raw_bytes: attachment.raw_bytes,
      text: attachment.raw_text || '',
      uploaded_at: attachment.created_at,
      captured_at: attachment.created_at,
      linked_facts: [],
    };
    if (!store.sources.some((item) => item.id === attachment.id)) store.sources.push(source);
    refs.push(source);
  });
  return refs;
}

function buildDraftsFromInputs(inputs, sources) {
  if (!inputs.length) inputs.push({ text: '', sourceIds: [] });
  const drafts = inputs.flatMap((input) => splitExperienceBlocks(input.text).map((text) => ({ text, sourceIds: input.sourceIds, filename: input.filename })));
  const normalized = drafts.length ? drafts : inputs;
  return normalized.map((input, index) => {
    const text = cleanText(input.text);
    const title = firstMeaningfulLine(text).replace(/^(?:#{1,3}\s+|\d+[.)]\s+)/, '').trim() || (input.filename ? input.filename.replace(/\.[^.]+$/, '') : `새 경험 ${index + 1}`);
    const summary = parseField(text, ['요약']) || text || `${input.filename || '입력 자료'}에서 추출한 경험입니다.`;
    const situation = parseField(text, ['상황']);
    const actions = listField(parseField(text, ['행동']));
    const results = listField(parseField(text, ['결과']));
    const facts = listField(parseField(text, ['사실', '확인된 사실', '근거에서 확인된 내용']));
    const role = parseField(text, ['역할']);
    const skills = listField(parseField(text, ['역량', '스킬'])).flatMap((item) => item.split(/[,，]/).map((skill) => skill.trim()).filter(Boolean));
    const linkedFacts = facts.map((fact) => ({ fact, quote: fact }));
    const mergeFacts = (current) => [...new Map([...current, ...linkedFacts].map((item) => [item.fact, item])).values()];
    const sourceRefs = sources.filter((source) => input.sourceIds.includes(source.id)).map((source) => ({ ...source, linked_facts: mergeFacts(source.linked_facts || []) }));
    sourceRefs.forEach((source) => {
      const storedSource = store.sources.find((item) => item.id === source.id);
      if (storedSource) storedSource.linked_facts = mergeFacts(storedSource.linked_facts || []);
    });
    return {
      draft_id: nextId('DRF'),
      title, summary, situation, actions, results, role, facts, skills,
      domain: { name: inferDomain(text || title) },
      project: { name: inferProject(text || title, index, input.filename) },
      missing_information: ['구체적인 역할과 정량 성과를 확인해 주세요.'],
      source_ref_ids: input.sourceIds,
      source_refs: sourceRefs,
      field_citations: {
        summary: input.sourceIds,
        situation: input.sourceIds,
        actions: input.sourceIds,
        results: input.sourceIds,
      facts: input.sourceIds,
      },
      confidence: text ? 0.68 : 0.35,
      skill_groups: [],
    };
  });
}

function buildExperienceDrafts(messageId, content, attachmentIds) {
  const sources = sourceForMessage(messageId, content, attachmentIds);
  const inputs = [];
  const fileSources = sources.filter((source) => source.source_type === 'file');
  const combinedText = [cleanText(content), ...fileSources.map((source) => cleanText(source.text))].filter(Boolean).join('\n\n');
  if (combinedText || sources.length) {
    inputs.push({
      text: combinedText,
      sourceIds: sources.map((source) => source.id),
      filename: !cleanText(content) && fileSources.length === 1 ? fileSources[0].filename : undefined,
    });
  }
  return buildDraftsFromInputs(inputs, sources);
}

function buildConversationExperienceDrafts(messages) {
  const sources = [];
  const attachmentIds = [...new Set(messages.flatMap((message) => message.attachment_ids || []))];
  messages.forEach((message) => {
    sourceForMessage(message.id, message.content, []).forEach((source) => {
      if (!sources.some((item) => item.id === source.id)) sources.push(source);
    });
  });
  attachmentIds.forEach((attachmentId) => {
    const attachmentMessage = messages.find((message) => message.attachment_ids?.includes(attachmentId));
    sourceForMessage(attachmentMessage?.id || 'conversation', '', [attachmentId]).forEach((source) => {
      if (!sources.some((item) => item.id === source.id)) sources.push(source);
    });
  });

  const inputs = [];
  const fileSources = sources.filter((source) => source.source_type === 'file');
  const conversationText = [
    messages.map((message) => cleanText(message.content)).filter(Boolean).join('\n'),
    ...fileSources.map((source) => cleanText(source.text)),
  ].filter(Boolean).join('\n\n');
  inputs.push({
    text: conversationText,
    sourceIds: sources.map((source) => source.id),
    filename: !messages.some((message) => cleanText(message.content)) && fileSources.length === 1 ? fileSources[0].filename : undefined,
  });
  return { experiences: buildDraftsFromInputs(inputs, sources), sources, attachmentIds };
}

function makeProposal(conversationId, messageId, content, intents, attachmentIds, options = {}) {
  if (!intents.some((intent) => ['experience', 'job'].includes(intent))) return null;
  const isJob = intents.includes('job');
  const jobSourceRefs = isJob ? sourceForMessage(messageId, content, attachmentIds) : [];
  const proposal = {
    id: nextId('PRP'),
    conversation_id: conversationId,
    originating_message_id: messageId,
    type: isJob ? 'analyze_job' : 'create_experiences',
    status: 'pending',
    title: isJob ? '채용공고 분석 제안' : '새 경험 정리 제안',
    summary: isJob ? '공고 요구사항을 경험과 비교할 준비가 되었습니다.' : '대화에서 경험 후보를 정리했습니다.',
    payload: isJob
      ? { job_draft: { posting_title: '', company_name: '', role_name: '', source_url: '', posting_content: [content, ...jobSourceRefs.filter((source) => source.source_type === 'file').map((source) => source.text)].filter(Boolean).join('\n\n') } }
      : (() => {
          const experiences = options.experiences || buildExperienceDrafts(messageId, content, attachmentIds);
          return { domain: experiences[0]?.domain || { name: '' }, project: experiences[0]?.project || { name: '' }, experiences };
        })(),
    source_refs: options.sourceRefs || (isJob ? jobSourceRefs : store.sources.filter((source) => source.id === `SRC-${messageId}` || attachmentIds.includes(source.id))),
    extraction_run_id: options.extractionRunId,
    analysis_scope: options.analysisScope,
    warnings: [],
    created_at: timestamp(),
    updated_at: timestamp(),
    version: 1,
  };
  store.proposals.push(proposal);
  return proposal;
}

function assistantText(intents, proposal) {
  if (proposal?.type === 'analyze_job') return '공고 내용을 확인했습니다. 요구사항과 저장된 경험을 비교할 수 있도록 분석 제안을 만들었어요.';
  if (proposal) return '말씀해 주신 내용을 경험 후보로 정리했습니다. 제안 카드를 확인하고 수정하거나 저장해 주세요.';
  return '말씀하신 내용을 바탕으로 함께 살펴볼게요. 더 구체적인 상황이나 원하는 도움을 알려주세요.';
}

export async function createConversation({ title = '새 대화' } = {}) {
  await wait();
  const conversation = {
    id: nextId('CONV'), title, status: 'active', message_count: 0,
    pending_proposal_count: 0, extracted_message_ids: [], last_successful_extraction_sequence: 0,
    created_at: timestamp(), updated_at: timestamp(), version: 1,
  };
  store.conversations.unshift(conversation);
  return snapshot(conversation);
}

export async function listConversations({ status = 'active' } = {}) {
  await wait();
  const items = store.conversations.filter((item) => !status || item.status === status);
  return { items: snapshot(items), total_count: items.length };
}

export async function getConversation(conversationId) {
  await wait();
  return snapshot(find(store.conversations, conversationId, '대화'));
}

export async function updateConversation(conversationId, inputChanges) {
  const item = find(store.conversations, conversationId, '대화');
  const changes = { ...inputChanges };
  delete changes.base_version;
  delete changes.client_request_id;
  Object.assign(item, changes, { updated_at: timestamp(), version: item.version + 1 });
  await wait();
  return snapshot(item);
}

export async function deleteConversation(conversationId) {
  find(store.conversations, conversationId, '대화');
  store.conversations = store.conversations.filter((item) => item.id !== conversationId);
  store.messages = store.messages.filter((item) => item.conversation_id !== conversationId);
  store.proposals = store.proposals.filter((item) => item.conversation_id !== conversationId);
  store.extractionRuns = store.extractionRuns.filter((item) => item.conversation_id !== conversationId);
  await wait();
  return { deleted_id: conversationId };
}

export async function listMessages(conversationId) {
  find(store.conversations, conversationId, '대화');
  await wait();
  const items = store.messages.filter((item) => item.conversation_id === conversationId);
  return { items: snapshot(items), total_count: items.length };
}

export async function preflightAttachments(descriptors) {
  const items = Array.from(descriptors || []).map((descriptor) => {
    const exact = store.attachments.find((item) => item.content_hash && item.content_hash === descriptor.content_hash);
    if (exact) return { client_id: descriptor.client_id, status: 'exact_duplicate', existing_attachment: snapshot(exact) };
    const sameName = store.attachments.find((item) => item.filename?.normalize('NFKC').toLocaleLowerCase('ko-KR') === descriptor.filename?.normalize('NFKC').toLocaleLowerCase('ko-KR'));
    if (sameName) return { client_id: descriptor.client_id, status: 'same_name_different_content', existing_attachment: snapshot(sameName) };
    return { client_id: descriptor.client_id, status: 'new_file', existing_attachment: null };
  });
  await wait(40);
  return { items };
}

export async function uploadAttachments(files) {
  const input = Array.from(files || []);
  if (input.length > 5) fail('VALIDATION_ERROR', '파일은 최대 5개까지 올릴 수 있습니다.', 422);
  const total = input.reduce((sum, file) => sum + (file.size || 0), 0);
  if (total > 100 * 1024 * 1024) fail('FILE_TOO_LARGE', '전체 파일 크기는 100MiB 이하여야 합니다.', 413);
  const attachments = await Promise.all(input.map(async (selection) => {
    if (selection.existingAttachmentId) {
      return { ...snapshot(find(store.attachments, selection.existingAttachmentId, '첨부 파일')), reused: true };
    }
    const file = selection.file || selection;
    if ((selection.size || file.size || 0) > 25 * 1024 * 1024) fail('FILE_TOO_LARGE', `${selection.name || file.name}은 25MiB를 초과합니다.`, 413);
    const isText = file.type === 'text/plain' || file.name?.toLowerCase().endsWith('.txt');
    const rawText = isText && typeof file.text === 'function' ? await file.text() : '';
    const rawBytes = typeof file.arrayBuffer === 'function' ? await file.arrayBuffer() : null;
    const contentHash = selection.contentHash || (rawBytes ? await sha256ArrayBuffer(rawBytes) : await fingerprintFile(file));
    const exact = store.attachments.find((item) => item.content_hash === contentHash);
    if (exact) return { ...snapshot(exact), reused: true };
    const sameName = store.attachments.find((item) => item.filename?.normalize('NFKC').toLocaleLowerCase('ko-KR') === file.name?.normalize('NFKC').toLocaleLowerCase('ko-KR'));
    const attachment = {
      id: nextId('ATT'), filename: file.name, mime_type: file.type || 'text/plain', size_bytes: file.size || 0,
      kind: file.type === 'application/pdf' || file.name?.toLowerCase().endsWith('.pdf') ? 'pdf' : 'text',
      status: 'ready', created_at: timestamp(), raw_text: rawText, raw_bytes: rawBytes, content_hash: contentHash,
      original_attachment_id: selection.previousAttachmentId || sameName?.id || null,
    };
    store.attachments.push(attachment);
    return attachment;
  }));
  await wait(120);
  return snapshot(attachments);
}

export async function deleteAttachment(attachmentId) {
  find(store.attachments, attachmentId, '첨부 파일');
  store.attachments = store.attachments.filter((item) => item.id !== attachmentId);
  await wait();
  return { deleted_id: attachmentId };
}

function createMessagePair(conversationId, input) {
  const conversation = find(store.conversations, conversationId, '대화');
  const content = input.content?.trim() || '';
  const attachmentIds = input.attachment_ids || [];
  if (!content && !attachmentIds.length) fail('VALIDATION_ERROR', '메시지나 파일을 입력해 주세요.', 422);
  attachmentIds.forEach((attachmentId) => find(store.attachments, attachmentId, '첨부 파일'));
  const intents = resolveIntents(input.intent || 'auto');
  const userMessage = {
    id: nextId('MSG'), conversation_id: conversationId, role: 'user', status: 'completed', content,
    sequence: conversation.message_count + 1,
    requested_intent: input.intent || 'auto', resolved_intents: intents, attachment_ids: attachmentIds,
    attachment_refs: attachmentIds.map((attachmentId) => {
      const attachment = find(store.attachments, attachmentId, '첨부 파일');
      return { id: attachment.id, filename: attachment.filename, mime_type: attachment.mime_type, size_bytes: attachment.size_bytes };
    }),
    citations: [], proposal_ids: [], actions: [], created_at: timestamp(), completed_at: timestamp(),
  };
  const proposal = makeProposal(conversationId, userMessage.id, content, intents, attachmentIds);
  const response = assistantText(intents, proposal);
  const assistantMessage = {
    id: nextId('MSG'), conversation_id: conversationId, role: 'assistant', status: 'completed', content: response,
    sequence: conversation.message_count + 2,
    requested_intent: 'auto', resolved_intents: intents, attachment_ids: [], citations: [],
    proposal_ids: proposal ? [proposal.id] : [],
    actions: proposal ? [{ type: 'review_proposal', label: '정리 제안 확인', target_id: proposal.id }] : [],
    created_at: timestamp(), completed_at: timestamp(),
  };
  store.messages.push(userMessage, assistantMessage);
  const extractedMessageIds = new Set(conversation.extracted_message_ids || []);
  if (proposal?.type === 'create_experiences') extractedMessageIds.add(userMessage.id);
  Object.assign(conversation, {
    message_count: conversation.message_count + 2,
    pending_proposal_count: conversation.pending_proposal_count + (proposal ? 1 : 0),
    extracted_message_ids: [...extractedMessageIds],
    last_successful_extraction_sequence: proposal?.type === 'create_experiences'
      ? Math.max(conversation.last_successful_extraction_sequence || 0, userMessage.sequence)
      : conversation.last_successful_extraction_sequence || 0,
    last_message_preview: response,
    updated_at: timestamp(),
    version: conversation.version + 1,
  });
  return { userMessage, assistantMessage, proposal, intents };
}

export async function sendMessage(conversationId, input) {
  await wait(160);
  const result = createMessagePair(conversationId, input);
  return snapshot({ ...result.assistantMessage, request_message_id: result.userMessage.id });
}

export async function getConversationExtractionStatus(conversationId) {
  const conversation = find(store.conversations, conversationId, '대화');
  const extracted = new Set(conversation.extracted_message_ids || []);
  const pendingMessages = store.messages.filter((message) => message.conversation_id === conversationId && message.role === 'user' && !extracted.has(message.id));
  const attachmentIds = [...new Set(pendingMessages.flatMap((message) => message.attachment_ids || []))];
  await wait();
  return {
    conversation_id: conversationId,
    unprocessed_message_count: pendingMessages.length,
    unprocessed_attachment_count: attachmentIds.length,
    last_successful_extraction_sequence: conversation.last_successful_extraction_sequence || 0,
    last_extraction_at: conversation.last_extraction_at || null,
  };
}

export async function extractConversationExperiences(conversationId, { client_request_id: clientRequestId } = {}) {
  const conversation = find(store.conversations, conversationId, '대화');
  const previousRun = clientRequestId && store.extractionRuns.find((item) => item.client_request_id === clientRequestId && item.status === 'succeeded');
  if (previousRun) {
    return snapshot({
      run: previousRun,
      message: find(store.messages, previousRun.assistant_message_id, '메시지'),
      proposal: find(store.proposals, previousRun.proposal_id, '정리 제안'),
      conversation,
    });
  }

  const extracted = new Set(conversation.extracted_message_ids || []);
  const messages = store.messages.filter((message) => message.conversation_id === conversationId && message.role === 'user' && !extracted.has(message.id));
  if (!messages.length) fail('NO_NEW_CONTENT', '새로 정리할 대화나 파일이 없습니다.', 409);

  const fromSequence = Math.min(...messages.map((message) => message.sequence || 0));
  const toSequence = Math.max(...messages.map((message) => message.sequence || 0));
  const run = {
    id: nextId('RUN'),
    conversation_id: conversationId,
    from_sequence: fromSequence,
    to_sequence: toSequence,
    message_ids: messages.map((message) => message.id),
    attachment_ids: [...new Set(messages.flatMap((message) => message.attachment_ids || []))],
    status: 'running',
    model_version: 'mock-experience-structurer-v1',
    prompt_version: 'experience-flow-v1',
    schema_version: 'experience-draft-v1',
    client_request_id: clientRequestId || nextId('REQ'),
    started_at: timestamp(),
  };
  store.extractionRuns.unshift(run);

  try {
    const built = buildConversationExperienceDrafts(messages);
    const analysisScope = {
      message_count: messages.length,
      attachment_count: built.attachmentIds.length,
      from_sequence: fromSequence,
      to_sequence: toSequence,
    };
    const proposal = makeProposal(
      conversationId,
      messages.at(-1).id,
      messages.map((message) => message.content).filter(Boolean).join('\n'),
      ['experience'],
      built.attachmentIds,
      { experiences: built.experiences, sourceRefs: built.sources, extractionRunId: run.id, analysisScope },
    );
    const assistantMessage = {
      id: nextId('MSG'), conversation_id: conversationId, role: 'assistant', status: 'completed',
      content: `최근 대화 ${messages.length}개와 파일 ${built.attachmentIds.length}개에서 경험 초안 ${built.experiences.length}개를 정리했습니다.`,
      sequence: conversation.message_count + 1,
      requested_intent: 'experience', resolved_intents: ['experience'], attachment_ids: [],
      citations: built.sources.map((source) => ({
        source_ref_id: source.id,
        source_type: source.source_type,
        message_id: source.message_id,
        label: source.filename || source.title || '원본 근거',
      })),
      proposal_ids: [proposal.id],
      actions: [{ type: 'review_proposal', label: '경험 초안 확인', target_id: proposal.id }],
      created_at: timestamp(), completed_at: timestamp(),
    };
    store.messages.push(assistantMessage);
    messages.forEach((message) => extracted.add(message.id));
    Object.assign(conversation, {
      message_count: conversation.message_count + 1,
      pending_proposal_count: conversation.pending_proposal_count + 1,
      extracted_message_ids: [...extracted],
      last_successful_extraction_sequence: toSequence,
      last_extraction_at: timestamp(),
      last_message_preview: assistantMessage.content,
      updated_at: timestamp(),
      version: conversation.version + 1,
    });
    Object.assign(run, {
      status: 'succeeded',
      proposal_id: proposal.id,
      assistant_message_id: assistantMessage.id,
      completed_at: timestamp(),
    });
    await wait(180);
    return snapshot({ run, message: assistantMessage, proposal, conversation });
  } catch (error) {
    Object.assign(run, { status: 'failed', completed_at: timestamp(), error: { message: error?.message || '경험 구조화에 실패했습니다.' } });
    throw error;
  }
}

export async function* streamMessage(conversationId, input) {
  const result = createMessagePair(conversationId, input);
  let sequence = 1;
  yield { type: 'message.accepted', sequence: sequence++, user_message: snapshot(result.userMessage), assistant_message_id: result.assistantMessage.id };
  yield { type: 'intent.resolved', sequence: sequence++, intents: result.intents };
  const words = result.assistantMessage.content.split(' ');
  for (const word of words) {
    await wait(25);
    yield { type: 'assistant.delta', sequence: sequence++, message_id: result.assistantMessage.id, delta: `${word} ` };
  }
  if (result.proposal) yield { type: 'proposal.created', sequence: sequence++, proposal: snapshot(result.proposal) };
  yield { type: 'message.completed', sequence, message: snapshot(result.assistantMessage) };
}

export async function getProposal(proposalId) {
  await wait();
  return snapshot(find(store.proposals, proposalId, '정리 제안'));
}

export async function updateProposal(proposalId, { base_version: baseVersion, payload, approved_experience_indexes: approvedExperienceIndexes }) {
  const proposal = find(store.proposals, proposalId, '정리 제안');
  if (proposal.version !== baseVersion) fail('VERSION_CONFLICT', '다른 변경 사항이 있습니다. 최신 내용을 확인해 주세요.', 409, { current: snapshot(proposal) });
  if (proposal.status === 'approved' || proposal.status === 'rejected') fail('INVALID_STATE', '처리가 끝난 제안은 수정할 수 없습니다.', 409);
  proposal.payload = snapshot(payload);
  if (Array.isArray(approvedExperienceIndexes)) proposal.approved_experience_indexes = [...approvedExperienceIndexes].sort((a, b) => a - b);
  proposal.status = 'edited';
  proposal.updated_at = timestamp();
  proposal.version += 1;
  await wait();
  return snapshot(proposal);
}

function ensureProposalStructure(draft) {
  reconcileStructureStore();
  const domainName = cleanStructureName(draft.domain?.name) || '새 경험 분류';
  let domain = store.domains.find((item) => structureNameKey(item.name) === structureNameKey(domainName));
  if (!domain) {
    domain = { id: nextId('DOM'), name: domainName, created_at: timestamp(), updated_at: timestamp(), version: 1 };
    store.domains.push(domain);
  }
  const projectName = cleanStructureName(draft.project?.name) || '새 프로젝트';
  let project = store.projects.find((item) => item.domain_id === domain.id && structureNameKey(item.name) === structureNameKey(projectName));
  if (!project) {
    project = { id: nextId('PROJ'), domain_id: domain.id, name: projectName, organization: draft.project?.organization?.trim() || '', created_at: timestamp(), updated_at: timestamp(), version: 1 };
    store.projects.push(project);
  }
  return { domain: domainRef(domain.id), project: projectRef(project.id) };
}

export async function approveProposal(proposalId, { base_version: baseVersion, selection } = {}) {
  const proposal = find(store.proposals, proposalId, '정리 제안');
  if (baseVersion != null && proposal.version !== baseVersion) fail('VERSION_CONFLICT', '제안 버전이 변경되었습니다.', 409, { current: snapshot(proposal) });
  if (proposal.status === 'rejected') fail('INVALID_STATE', '거절한 제안은 승인할 수 없습니다.', 409);
  const createdIds = [];
  if (proposal.type !== 'analyze_job' && proposal.status !== 'approved') {
    const alreadyApproved = new Set(proposal.approved_experience_indexes || []);
    const indexes = selection?.experience_indexes || proposal.payload.experiences.map((_, index) => index);
    for (const index of indexes) {
      if (alreadyApproved.has(index)) continue;
      const draft = proposal.payload.experiences[index];
      if (!draft) continue;
      const structure = ensureProposalStructure(draft);
      const experience = {
        ...snapshot(draft), id: nextId('EXP'), ...structure, domain_id: structure.domain.id, project_id: structure.project.id, evidence_count: draft.source_ref_ids?.length || 0,
        evidence_status: draft.source_ref_ids?.length ? 'verified' : 'missing',
        source_ids: draft.source_ref_ids || [], source_refs: draft.source_refs || [], created_at: timestamp(), updated_at: timestamp(), version: 1,
      };
      store.experiences.unshift(experience);
      createdIds.push(experience.id);
      alreadyApproved.add(index);
    }
    proposal.approved_experience_indexes = [...alreadyApproved].sort((a, b) => a - b);
  }
  const allExperiencesApproved = proposal.type === 'analyze_job' || proposal.approved_experience_indexes?.length >= proposal.payload.experiences.length;
  if (proposal.status !== 'approved' && allExperiencesApproved) {
    proposal.status = 'approved'; proposal.updated_at = timestamp(); proposal.version += 1;
    const conversation = store.conversations.find((item) => item.id === proposal.conversation_id);
    if (conversation) conversation.pending_proposal_count = Math.max(0, conversation.pending_proposal_count - 1);
  } else if (proposal.status !== 'approved') {
    proposal.status = 'edited'; proposal.updated_at = timestamp(); proposal.version += 1;
  }
  await wait(100);
  return { proposal: snapshot(proposal), created: { experience_ids: createdIds, job_id: null }, updated: { experience_ids: [] }, approved_at: timestamp() };
}

export async function discardUnapprovedProposalExperiences(proposalId, { base_version: baseVersion } = {}) {
  const proposal = find(store.proposals, proposalId, '정리 제안');
  if (baseVersion != null && proposal.version !== baseVersion) fail('VERSION_CONFLICT', '제안 버전이 변경되었습니다.', 409);
  if (proposal.type === 'analyze_job') fail('INVALID_STATE', '채용공고 제안에는 이 작업을 사용할 수 없습니다.', 409);
  if (proposal.status === 'rejected') fail('INVALID_STATE', '삭제된 제안입니다.', 409);

  const approvedIndexes = new Set(proposal.approved_experience_indexes || []);
  const approvedDrafts = (proposal.payload.experiences || []).filter((_, index) => approvedIndexes.has(index));
  if (!approvedDrafts.length) return rejectProposal(proposalId, { base_version: baseVersion });

  proposal.payload.experiences = approvedDrafts;
  proposal.approved_experience_indexes = approvedDrafts.map((_, index) => index);
  proposal.status = 'approved';
  proposal.updated_at = timestamp();
  proposal.version += 1;
  const conversation = store.conversations.find((item) => item.id === proposal.conversation_id);
  if (conversation) conversation.pending_proposal_count = Math.max(0, conversation.pending_proposal_count - 1);
  await wait();
  return snapshot(proposal);
}

export async function rejectProposal(proposalId, { base_version: baseVersion } = {}) {
  const proposal = find(store.proposals, proposalId, '정리 제안');
  if (baseVersion != null && proposal.version !== baseVersion) fail('VERSION_CONFLICT', '제안 버전이 변경되었습니다.', 409);
  if (proposal.status === 'approved') fail('INVALID_STATE', '승인한 제안은 거절할 수 없습니다.', 409);
  proposal.status = 'rejected'; proposal.updated_at = timestamp(); proposal.version += 1;
  const conversation = store.conversations.find((item) => item.id === proposal.conversation_id);
  if (conversation) {
    conversation.pending_proposal_count = Math.max(0, conversation.pending_proposal_count - 1);
    if (proposal.type === 'create_experiences') {
      const run = proposal.extraction_run_id && store.extractionRuns.find((item) => item.id === proposal.extraction_run_id);
      const releasedMessageIds = run?.message_ids || [proposal.originating_message_id];
      const released = new Set(releasedMessageIds);
      conversation.extracted_message_ids = (conversation.extracted_message_ids || []).filter((id) => !released.has(id));
      const remainingSequences = store.messages
        .filter((message) => conversation.extracted_message_ids.includes(message.id))
        .map((message) => message.sequence || 0);
      conversation.last_successful_extraction_sequence = remainingSequences.length ? Math.max(...remainingSequences) : 0;
      if (run) run.status = 'rejected';
    }
  }
  await wait();
  return snapshot(proposal);
}

export async function listExperiences(filters = {}) {
  const query = filters.query?.trim().toLowerCase();
  let items = store.experiences.filter((item) => {
    if (query && !`${item.title} ${item.summary} ${(item.skills || []).join(' ')}`.toLowerCase().includes(query)) return false;
    if (filters.skill && !item.skills.includes(filters.skill)) return false;
    if (filters.evidence_status && item.evidence_status !== filters.evidence_status) return false;
    return true;
  });
  await wait();
  items = items.map((item) => ({ ...item, missing_information_count: item.missing_information?.length || 0 }));
  return { items: snapshot(items), total_count: items.length };
}

function assertVersion(resource, version, label) {
  if (version != null && resource.version !== version) fail('VERSION_CONFLICT', `${label} 버전이 변경되었습니다.`, 409, { current: snapshot(resource) });
}

function domainRef(domainId) {
  const domain = find(store.domains, domainId, '경험 분류');
  return { id: domain.id, name: domain.name };
}

function projectRef(projectId) {
  const project = find(store.projects, projectId, '프로젝트·활동');
  return { id: project.id, name: project.name, organization: project.organization || '' };
}

export async function listDomains() {
  reconcileStructureStore();
  await wait();
  const items = store.domains.map((domain) => ({
    ...domain,
    project_count: store.projects.filter((project) => project.domain_id === domain.id).length,
    experience_count: store.experiences.filter((experience) => experience.domain?.id === domain.id).length,
  }));
  return { items: snapshot(items), total_count: items.length };
}

export async function listStructure() {
  reconcileStructureStore();
  const domains = store.domains.map((domain) => ({
    ...domain,
    projects: store.projects.filter((project) => project.domain_id === domain.id).map((project) => ({
      ...project,
      experiences: store.experiences.filter((experience) => experience.project?.id === project.id),
    })),
  }));
  await wait();
  return { domains: snapshot(domains), total_count: domains.length };
}

export async function createDomain(input) {
  reconcileStructureStore();
  const name = cleanStructureName(input?.name);
  if (!name) fail('VALIDATION_ERROR', '경험 분류 이름을 입력해 주세요.', 422);
  if (store.domains.some((domain) => structureNameKey(domain.name) === structureNameKey(name))) fail('DUPLICATE_RESOURCE', '같은 이름의 경험 분류가 이미 있습니다.', 409);
  const domain = { id: nextId('DOM'), name, created_at: timestamp(), updated_at: timestamp(), version: 1 };
  store.domains.push(domain);
  await wait();
  return snapshot(domain);
}

export async function updateDomain(domainId, { base_version: baseVersion, changes = {}, name } = {}) {
  reconcileStructureStore();
  const domain = find(store.domains, domainId, '경험 분류');
  assertVersion(domain, baseVersion, '경험 분류');
  if (name != null) changes = { ...changes, name };
  const nextName = changes?.name != null ? cleanStructureName(changes.name) : domain.name;
  if (!nextName) fail('VALIDATION_ERROR', '경험 분류 이름을 입력해 주세요.', 422);
  if (store.domains.some((item) => item.id !== domainId && structureNameKey(item.name) === structureNameKey(nextName))) fail('DUPLICATE_RESOURCE', '같은 이름의 경험 분류가 이미 있습니다.', 409);
  Object.assign(domain, snapshot(changes), { name: nextName, updated_at: timestamp(), version: domain.version + 1 });
  store.experiences.filter((item) => item.domain?.id === domainId).forEach((item) => { item.domain.name = domain.name; item.updated_at = timestamp(); });
  await wait();
  return snapshot(domain);
}

export async function listProjects({ domain_id: domainId } = {}) {
  const { domainIdMap } = reconcileStructureStore();
  domainId = domainIdMap.get(domainId) || domainId;
  await wait();
  const items = store.projects.filter((project) => !domainId || project.domain_id === domainId).map((project) => ({
    ...project, experience_count: store.experiences.filter((experience) => experience.project?.id === project.id).length,
  }));
  return { items: snapshot(items), total_count: items.length };
}

export async function createProject(input) {
  const { domainIdMap } = reconcileStructureStore();
  const domainId = domainIdMap.get(input.domain_id) || input.domain_id;
  const name = cleanStructureName(input?.name);
  if (!name) fail('VALIDATION_ERROR', '프로젝트·활동 이름을 입력해 주세요.', 422);
  find(store.domains, domainId, '경험 분류');
  if (store.projects.some((project) => project.domain_id === domainId && structureNameKey(project.name) === structureNameKey(name))) fail('DUPLICATE_RESOURCE', '이 경험 분류에 같은 이름의 프로젝트·활동이 이미 있습니다.', 409);
  const project = { id: nextId('PROJ'), domain_id: domainId, name, organization: input.organization?.trim() || '', created_at: timestamp(), updated_at: timestamp(), version: 1 };
  store.projects.push(project);
  await wait();
  return snapshot(project);
}

export async function updateProject(projectId, { base_version: baseVersion, changes = {}, ...directChanges }) {
  reconcileStructureStore();
  const project = find(store.projects, projectId, '프로젝트·활동');
  assertVersion(project, baseVersion, '프로젝트·활동');
  changes = { ...changes, ...Object.fromEntries(Object.entries(directChanges).filter(([key]) => ['name', 'organization', 'domain_id'].includes(key))) };
  if (changes?.domain_id) find(store.domains, changes.domain_id, '경험 분류');
  const nextDomainId = changes?.domain_id || project.domain_id;
  const nextName = changes?.name != null ? cleanStructureName(changes.name) : project.name;
  if (!nextName) fail('VALIDATION_ERROR', '프로젝트·활동 이름을 입력해 주세요.', 422);
  if (store.projects.some((item) => item.id !== projectId && item.domain_id === nextDomainId && structureNameKey(item.name) === structureNameKey(nextName))) fail('DUPLICATE_RESOURCE', '이 경험 분류에 같은 이름의 프로젝트·활동이 이미 있습니다.', 409);
  Object.assign(project, snapshot(changes), { domain_id: nextDomainId, name: nextName, updated_at: timestamp(), version: project.version + 1 });
  const domain = domainRef(project.domain_id);
  store.experiences.filter((item) => item.project?.id === projectId).forEach((item) => { item.project = projectRef(projectId); item.domain = domain; item.updated_at = timestamp(); });
  await wait();
  return snapshot(project);
}

export async function getStructureDeletionImpact(type, resourceId) {
  const isDomain = type === 'domain';
  find(isDomain ? store.domains : store.projects, resourceId, isDomain ? '경험 분류' : '프로젝트·활동');
  const projectIds = isDomain ? store.projects.filter((item) => item.domain_id === resourceId).map((item) => item.id) : [resourceId];
  const experiences = store.experiences.filter((item) => projectIds.includes(item.project?.id));
  await wait();
  return { type, id: resourceId, project_count: isDomain ? projectIds.length : 0, experience_count: experiences.length, linked_source_count: experiences.reduce((sum, item) => sum + (item.source_ids?.length || 0), 0), recoverable: true };
}

export const getDomainDeletionImpact = (domainId) => getStructureDeletionImpact('domain', domainId);
export const getProjectDeletionImpact = (projectId) => getStructureDeletionImpact('project', projectId);

function softDelete(collection, resource, type) {
  const deleted = { ...snapshot(resource), deleted_at: timestamp() };
  store.deleted[type].push(deleted);
  store[collection] = store[collection].filter((item) => item.id !== resource.id);
}

export async function deleteProject(projectId, { version, confirm, strategy, target_project_id: targetProjectId, cascade = false } = {}) {
  const project = find(store.projects, projectId, '프로젝트·활동');
  if (!confirm) fail('CONFIRMATION_REQUIRED', '삭제 확인이 필요합니다.', 422);
  assertVersion(project, version, '프로젝트·활동');
  const ids = store.experiences.filter((item) => item.project?.id === projectId).map((item) => item.id);
  cascade = cascade || strategy === 'cascade';
  if (ids.length && !targetProjectId && !cascade) fail('DELETE_STRATEGY_REQUIRED', '경험 이동 또는 함께 삭제를 선택해 주세요.', 422);
  if (targetProjectId) await bulkMoveExperiences({ experience_ids: ids, target_project_id: targetProjectId });
  if (cascade) await bulkDeleteExperiences({ experience_ids: ids, confirm: true });
  softDelete('projects', project, 'projects');
  await wait();
  return { deleted_id: projectId, affected_experience_count: ids.length, recoverable: true };
}

export async function deleteDomain(domainId, { version, confirm, strategy, target_domain_id: targetDomainId, cascade = false } = {}) {
  const domain = find(store.domains, domainId, '경험 분류');
  if (!confirm) fail('CONFIRMATION_REQUIRED', '삭제 확인이 필요합니다.', 422);
  assertVersion(domain, version, '경험 분류');
  const projects = store.projects.filter((item) => item.domain_id === domainId);
  cascade = cascade || strategy === 'cascade';
  if (projects.length && !targetDomainId && !cascade) fail('DELETE_STRATEGY_REQUIRED', '하위 항목 이동 또는 함께 삭제를 선택해 주세요.', 422);
  if (targetDomainId) {
    find(store.domains, targetDomainId, '대상 경험 분류');
    for (const project of projects) await updateProject(project.id, { base_version: project.version, changes: { domain_id: targetDomainId } });
  } else if (cascade) {
    for (const project of [...projects]) await deleteProject(project.id, { version: project.version, confirm: true, cascade: true });
  }
  softDelete('domains', domain, 'domains');
  await wait();
  return { deleted_id: domainId, affected_project_count: projects.length, recoverable: true };
}

export async function bulkMoveExperiences({ experience_ids: experienceIds = [], target_domain_id: targetDomainId, target_project_id: targetProjectId }) {
  const project = find(store.projects, targetProjectId, '대상 프로젝트·활동');
  if (targetDomainId && project.domain_id !== targetDomainId) fail('VALIDATION_ERROR', '대상 프로젝트가 선택한 경험 분류에 속하지 않습니다.', 422);
  const domain = domainRef(project.domain_id);
  const updated = experienceIds.map((experienceId) => {
    const experience = find(store.experiences, experienceId, '경험');
    experience.domain = domain; experience.project = projectRef(project.id); experience.updated_at = timestamp(); experience.version += 1;
    return experience;
  });
  await wait();
  return { items: snapshot(updated), total_count: updated.length };
}

export async function bulkDeleteExperiences({ experience_ids: experienceIds = [], confirm } = {}) {
  if (!confirm) fail('CONFIRMATION_REQUIRED', '삭제 확인이 필요합니다.', 422);
  const items = experienceIds.map((experienceId) => find(store.experiences, experienceId, '경험'));
  items.forEach((item) => softDelete('experiences', item, 'experiences'));
  await wait();
  return { deleted_ids: items.map((item) => item.id), recoverable: true };
}

export async function restoreDeleted(type, resourceId) {
  const collectionByType = { domain: 'domains', project: 'projects', experience: 'experiences' };
  const collection = collectionByType[type];
  if (!collection) fail('VALIDATION_ERROR', '복원할 자원 유형이 올바르지 않습니다.', 422);
  const resource = find(store.deleted[collection], resourceId, '삭제된 항목');
  const { deleted_at: deletedAt, ...restored } = resource;
  void deletedAt;
  restored.updated_at = timestamp(); restored.version += 1;
  store[collection].push(restored);
  store.deleted[collection] = store.deleted[collection].filter((item) => item.id !== resourceId);
  await wait();
  return snapshot(restored);
}

export const restoreExperience = (experienceId) => restoreDeleted('experience', experienceId);

export async function getExperience(experienceId) {
  await wait();
  return snapshot(find(store.experiences, experienceId, '경험'));
}

export async function createExperience(input) {
  const { projectIdMap } = reconcileStructureStore();
  let domain = input.domain;
  let project = input.project;
  if (input.project_id) {
    const projectId = projectIdMap.get(input.project_id) || input.project_id;
    project = projectRef(projectId);
    domain = domainRef(find(store.projects, projectId, '프로젝트·활동').domain_id);
  } else if (typeof domain === 'object' && domain?.name && typeof project === 'object' && project?.name) {
    const domainName = cleanStructureName(domain.name);
    const projectName = cleanStructureName(project.name);
    let storedDomain = store.domains.find((item) => structureNameKey(item.name) === structureNameKey(domainName));
    if (!storedDomain) {
      storedDomain = { id: nextId('DOM'), name: domainName, created_at: timestamp(), updated_at: timestamp(), version: 1 };
      store.domains.push(storedDomain);
    }
    let storedProject = store.projects.find((item) => item.domain_id === storedDomain.id && structureNameKey(item.name) === structureNameKey(projectName));
    if (!storedProject) {
      storedProject = { id: nextId('PROJ'), domain_id: storedDomain.id, name: projectName, organization: project.organization?.trim() || '', created_at: timestamp(), updated_at: timestamp(), version: 1 };
      store.projects.push(storedProject);
    }
    domain = domainRef(storedDomain.id);
    project = projectRef(storedProject.id);
  }
  const experience = {
    ...snapshot(input), domain, project, domain_id: domain?.id || '', project_id: project?.id || '', id: nextId('EXP'), evidence_count: input.source_ids?.length || 0,
    evidence_status: input.source_ids?.length ? 'verified' : 'missing',
    source_refs: input.source_refs || [],
    created_at: timestamp(), updated_at: timestamp(), version: 1,
  };
  store.experiences.unshift(experience);
  await wait();
  return snapshot(experience);
}

export async function updateExperience(experienceId, { base_version: baseVersion, changes }) {
  const experience = find(store.experiences, experienceId, '경험');
  if (experience.version !== baseVersion) fail('VERSION_CONFLICT', '경험이 다른 곳에서 수정되었습니다.', 409, { current: snapshot(experience) });
  Object.assign(experience, snapshot(changes), { updated_at: timestamp(), version: experience.version + 1 });
  await wait();
  return snapshot(experience);
}

export async function getExperienceDeletionImpact(experienceId) {
  const experience = find(store.experiences, experienceId, '경험');
  await wait();
  return { experience_id: experienceId, linked_source_count: experience.source_ids?.length || 0, affected_documents: 0, recoverable: true };
}

export async function deleteExperience(experienceId, { version, confirm } = {}) {
  const experience = find(store.experiences, experienceId, '경험');
  if (!confirm) fail('CONFIRMATION_REQUIRED', '삭제 확인이 필요합니다.', 422);
  if (version != null && experience.version !== version) fail('VERSION_CONFLICT', '경험 버전이 변경되었습니다.', 409);
  softDelete('experiences', experience, 'experiences');
  await wait();
  return { deleted_id: experienceId, recoverable: true };
}

// 일반 채팅의 실제 HTTP 전환 대상이다.
// 경험정리·공고분석·첨부·경험관리 기능은 구현이 끝날 때까지 기존 Mock을 유지한다.
const activeConversationApi = apiConfig.useMock
  ? { createConversation, listConversations, getConversation, updateConversation, deleteConversation, listMessages, sendMessage }
  : v2ChatHttpApi;

export const v2ChatApi = {
  createConversation, listConversations, getConversation, updateConversation, deleteConversation,
  listMessages, sendMessage, streamMessage, getConversationExtractionStatus, extractConversationExperiences,
  preflightAttachments, uploadAttachments, deleteAttachment,
  getProposal, updateProposal, approveProposal, discardUnapprovedProposalExperiences, rejectProposal,
  listExperiences, getExperience, createExperience, updateExperience,
  getExperienceDeletionImpact, deleteExperience,
  listStructure, listDomains, createDomain, updateDomain, deleteDomain,
  listProjects, createProject, updateProject, deleteProject,
  getStructureDeletionImpact, getDomainDeletionImpact, getProjectDeletionImpact,
  bulkMoveExperiences, bulkDeleteExperiences, restoreDeleted, restoreExperience,
  reset: resetMockV2Store,
  ...activeConversationApi,
};

export { resetMockV2Store };
