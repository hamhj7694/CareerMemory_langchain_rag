import { useEffect, useMemo, useState } from 'react';
import { selectGuideSections } from './conversationGuideSections.js';

const CATEGORY_META = {
  general: { label: '일반 대화' },
  experience: { label: '경험 정리' },
  job: { label: '채용공고' },
  attachment: { label: '자료·첨부' },
};

function cleanPreview(value) {
  return String(value || '')
    .replace(/```[\s\S]*?```/g, ' 코드 ')
    .replace(/[#*_`>()]/g, '')
    .replaceAll('[', '')
    .replaceAll(']', '')
    .replace(/\s+/g, ' ')
    .trim();
}

function categoryFor(messages) {
  const intents = messages
    .flatMap((message) => message.resolvedIntents || [])
    .map((intent) => String(intent).toLowerCase());
  const joinedIntents = intents.join(' ');
  if (/job|posting/.test(joinedIntents)) return 'job';
  if (/experience|career/.test(joinedIntents)) return 'experience';

  const content = messages.map((message) => cleanPreview(message.content)).join(' ');
  if (/채용|공고|직무|지원서|면접|자격요건|우대사항|job|resume|interview/i.test(content)) return 'job';
  if (/경험|프로젝트|성과|경력|이력서|자소서|커리어|experience|project|achievement|career/i.test(content)) return 'experience';
  if (messages.some((message) => message.attachments?.length)) return 'attachment';
  return 'general';
}

function buildSections(messages) {
  const grouped = [];
  messages.forEach((message) => {
    if (message.role === 'user' || grouped.length === 0) {
      grouped.push({ id: String(message.id), messages: [message] });
    } else {
      grouped.at(-1).messages.push(message);
    }
  });

  return grouped.map((section, index) => {
    const firstUserMessage = section.messages.find((message) => message.role === 'user');
    const firstReadableMessage = firstUserMessage || section.messages.find((message) => cleanPreview(message.content));
    const category = categoryFor(section.messages);
    const preview = cleanPreview(firstReadableMessage?.content)
      || firstReadableMessage?.attachments?.[0]
      || `대화 구간 ${index + 1}`;
    return {
      id: section.id,
      index,
      category,
      label: CATEGORY_META[category].label,
      preview,
      hasAttachment: section.messages.some((message) => message.attachments?.length),
      hasProposal: section.messages.some((message) => (
        message.embeddedProposals?.length || message.jobAnalysisId
      )),
    };
  });
}

function findMessageElement(container, messageId) {
  return [...container.querySelectorAll('[data-message-id]')]
    .find((element) => element.dataset.messageId === String(messageId));
}

export function ConversationGuide({ messages, scrollRef }) {
  const sections = useMemo(() => buildSections(messages), [messages]);
  const guideSections = useMemo(() => selectGuideSections(sections), [sections]);
  const [activeId, setActiveId] = useState('');
  const [hasOverflow, setHasOverflow] = useState(false);

  useEffect(() => {
    const scrollArea = scrollRef.current;
    if (!scrollArea || sections.length < 2) {
      setHasOverflow(false);
      return undefined;
    }

    let animationFrame = 0;
    const update = () => {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(() => {
        const scrollable = scrollArea.scrollHeight > scrollArea.clientHeight + 24;
        setHasOverflow(scrollable);
        if (!scrollable) return;

        if (scrollArea.scrollTop + scrollArea.clientHeight >= scrollArea.scrollHeight - 16) {
          setActiveId(guideSections.at(-1).id);
          return;
        }

        const threshold = scrollArea.getBoundingClientRect().top + Math.min(120, scrollArea.clientHeight * 0.22);
        let currentId = sections[0].id;
        sections.forEach((section) => {
          const element = findMessageElement(scrollArea, section.id);
          if (element && element.getBoundingClientRect().top <= threshold) currentId = section.id;
        });
        const currentIndex = sections.findIndex((section) => section.id === currentId);
        const activeSection = guideSections.find((section) => (
          currentIndex >= section.rangeStart && currentIndex <= section.rangeEnd
        ));
        setActiveId(activeSection?.id || guideSections[0].id);
      });
    };

    update();
    scrollArea.addEventListener('scroll', update, { passive: true });
    const resizeObserver = globalThis.ResizeObserver ? new ResizeObserver(update) : null;
    resizeObserver?.observe(scrollArea);
    const messageList = scrollArea.querySelector('.v2-message-list');
    if (messageList) resizeObserver?.observe(messageList);

    return () => {
      window.cancelAnimationFrame(animationFrame);
      scrollArea.removeEventListener('scroll', update);
      resizeObserver?.disconnect();
    };
  }, [scrollRef, sections, guideSections]);

  if (sections.length < 2 || !hasOverflow) return null;

  const moveTo = (section) => {
    const scrollArea = scrollRef.current;
    const element = scrollArea && findMessageElement(scrollArea, section.id);
    if (!scrollArea || !element) return;
    const targetTop = element.getBoundingClientRect().top
      - scrollArea.getBoundingClientRect().top
      + scrollArea.scrollTop
      - 28;
    scrollArea.scrollTo({ top: Math.max(0, targetTop), behavior: 'smooth' });
    setActiveId(section.id);
  };

  const forwardWheel = (event) => {
    const scrollArea = scrollRef.current;
    if (!scrollArea) return;
    event.preventDefault();
    const multiplier = event.deltaMode === 1
      ? 16
      : event.deltaMode === 2 ? scrollArea.clientHeight : 1;
    scrollArea.scrollBy({ top: event.deltaY * multiplier, behavior: 'auto' });
  };

  return <nav
    className="v2-conversation-guide"
    style={{ '--guide-count': guideSections.length }}
    aria-label="대화 구간 빠른 이동"
    onWheel={forwardWheel}
  >
    <span className="v2-conversation-guide__track" aria-hidden="true" />
    {guideSections.map((section) => <button
      type="button"
      key={section.id}
      className={`v2-conversation-guide__item${activeId === section.id ? ' is-active' : ''}`}
      data-category={section.category}
      aria-current={activeId === section.id ? 'location' : undefined}
      aria-label={`${section.label}: ${section.preview}`}
      onClick={() => moveTo(section)}
    >
      <span className="v2-conversation-guide__marker" aria-hidden="true" />
      <span className="v2-conversation-guide__preview" role="tooltip">
        <strong>
          {section.label}
          {section.representedCount > 1 ? ` · ${section.representedCount}개 구간 대표` : ''}
        </strong>
        <span>{section.preview.slice(0, 84)}{section.preview.length > 84 ? '…' : ''}</span>
      </span>
    </button>)}
  </nav>;
}
