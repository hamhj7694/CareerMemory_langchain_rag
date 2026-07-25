import { EVIDENCE_TYPES } from '../model/evidenceMapper.js';

export function EvidenceSourceIcon({ type, className = '' }) {
  const isFile = type === EVIDENCE_TYPES.FILE;
  const isConversation = type === EVIDENCE_TYPES.CONVERSATION;
  const label = isFile ? '파일 원본' : isConversation ? '대화 원본' : type === EVIDENCE_TYPES.TEXT ? '텍스트 원본' : '원본 정보 없음';
  return (
    <span className={className} title={label}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        {isFile
          ? <><path d="M6.5 3.5h7l4 4v13h-11z" /><path d="M13.5 3.5v4h4" /></>
          : <><path d="M5 5.5h14M5 9.5h14M5 13.5h10M5 17.5h8" /></>}
      </svg>
      <span className="sr-only">{label}</span>
    </span>
  );
}
