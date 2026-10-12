import { ExperienceRichList, ExperienceRichText } from './ExperienceRichText.jsx';
import './content-blocks.css';

const list = (value) => Array.isArray(value) ? value.filter(Boolean) : [];

function BlockEvidence({ block }) {
  const citations = list(block.citations);
  if (!citations.length && block.confidence == null && !block.review_status) return null;
  return (
    <footer className="content-block__meta">
      {citations.length > 0 && <details className="content-block__citations"><summary>원문 근거 {citations.length}개</summary>{citations.map((citation, index) => {
        const sourceId = citation.source_ref_id || citation.sourceRefId || citation.source_id || citation.sourceId || '';
        const locator = citation.locator || citation.source_locator || citation.sourceLocator || '';
        return <blockquote key={`${sourceId}-${citation.quote || index}`}><p>{citation.quote || '인용문이 없는 근거입니다.'}</p>{(sourceId || locator) && <small>{[sourceId, locator].filter(Boolean).join(' · ')}</small>}</blockquote>;
      })}</details>}
      {block.review_status === 'needs_review' && <span>확인 필요</span>}
      {block.review_status === 'stale' && <span>원문 변경 후 재검토 필요</span>}
      {block.confidence != null && <span>AI 참고 신뢰도 {Math.round(Number(block.confidence) * 100)}%</span>}
    </footer>
  );
}

function StructuredItems({ items }) {
  if (!list(items).length) return <p>작성된 내용이 없습니다.</p>;
  return (
    <div className="content-block__structured-list">
      {items.map((item, index) => {
        if (typeof item === 'string') return <span key={`${item}-${index}`}>{item}</span>;
        const raw = item.raw_text || item.raw_value || item.name || item.text || item.canonical_name || item.value;
        const detail = item.normalized_value ?? item.canonical_name ?? item.unit ?? '';
        return <span key={item.id || `${raw}-${index}`}><strong>{String(raw || '구조화 정보')}</strong>{detail !== '' && detail !== raw ? <small>{String(detail)}</small> : null}</span>;
      })}
    </div>
  );
}

function UnknownData({ data }) {
  const entries = Object.entries(data || {}).filter(([, value]) => value !== '' && value != null);
  if (!entries.length) return <p>내용이 없는 사용자 정의 블록입니다.</p>;
  return <dl className="content-block__unknown">{entries.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</dd></div>)}</dl>;
}

function FactItems({ data }) {
  const statuses = data.evidence_status || {};
  return <ul className="content-block__facts">{list(data.items).map((fact) => <li key={fact}><span>{fact}</span>{statuses[fact] === 'stale' && <em>재검토 필요</em>}{statuses[fact] === 'needs_evidence' && <em>근거 필요</em>}</li>)}</ul>;
}

export function ContentBlockRenderer({ block }) {
  if (!block || block.visibility === 'hidden') return null;
  const data = block.data || {};
  const type = block.type || block.block_type || 'custom';
  const title = data.title || ({
    summary: '요약', situation: '상황', list: '목록', role: '역할', skills: '역량',
    facts: '근거에서 확인된 내용', metrics: '수치 성과', period: '기간',
    callout: '확인이 필요한 정보', source_text: '원문', job_requirement: '요구사항',
    properties: '추가 정보',
  }[type] || '사용자 정의 정보');

  let body;
  if (['summary', 'situation', 'role', 'paragraph', 'source_text'].includes(type)) {
    body = <ExperienceRichText text={data.text || data.value || ''} />;
  } else if (type === 'facts') {
    body = <FactItems data={data} />;
  } else if (['list', 'callout'].includes(type)) {
    body = <ExperienceRichList items={data.items || []} />;
  } else if (type === 'skills') {
    body = <><StructuredItems items={data.items} />{list(data.groups).length > 0 && <details><summary>역량 그룹</summary><UnknownData data={{ groups: data.groups }} /></details>}{list(data.mentions).length > 0 && <details><summary>정규화된 기술 정보</summary><StructuredItems items={data.mentions} /></details>}</>;
  } else if (type === 'metrics') {
    body = <StructuredItems items={data.items} />;
  } else if (type === 'period') {
    const value = data.value || {};
    body = <p>{[value.start, value.end].filter(Boolean).join(' ~ ') || value.raw_text || '기간 정보가 없습니다.'}</p>;
  } else if (type === 'job_requirement') {
    body = <><ExperienceRichText text={data.summary || data.title || ''} /><StructuredItems items={data.skill_mentions || data.skillMentions} /><StructuredItems items={data.metrics} /></>;
  } else if (type === 'properties') {
    body = <UnknownData data={data.value || {}} />;
  } else {
    body = <UnknownData data={data} />;
  }

  return (
    <section className={`detail-card content-block content-block--${type}`} data-block-type={type}>
      <h3>{title}</h3>
      {body}
      <BlockEvidence block={block} />
    </section>
  );
}

export function ContentDocumentRenderer({ blocks = [] }) {
  const visibleBlocks = list(blocks).filter((block) => block.visibility !== 'hidden');
  if (!visibleBlocks.length) return null;
  return <div className="content-document">{visibleBlocks.map((block, index) => <ContentBlockRenderer key={block.id || `${block.type}-${index}`} block={block} />)}</div>;
}

