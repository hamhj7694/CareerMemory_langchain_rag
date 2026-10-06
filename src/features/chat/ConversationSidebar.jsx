import { useEffect, useMemo, useState } from 'react';

export function ConversationSidebar({ conversations, activeId, open, onClose, onSelect, onCreate, onRename, onDelete, onSearch }) {
  const [query, setQuery] = useState('');
  const [searchResult, setSearchResult] = useState({ query: '', items: [], error: '' });
  const normalizedQuery = query.trim().toLocaleLowerCase();

  useEffect(() => {
    if (!normalizedQuery || !onSearch) return undefined;
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const items = await onSearch(query.trim());
        if (active) setSearchResult({ query: normalizedQuery, items, error: '' });
      } catch (error) {
        if (active) setSearchResult({
          query: normalizedQuery,
          items: [],
          error: error?.message || '대화 내용을 검색하지 못했습니다.',
        });
      }
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [normalizedQuery, onSearch, query]);

  const searching = Boolean(normalizedQuery && onSearch && searchResult.query !== normalizedQuery);
  const searchError = searchResult.query === normalizedQuery ? searchResult.error : '';
  const visible = useMemo(() => {
    let source = conversations;
    if (normalizedQuery) {
      source = onSearch
        ? (searchResult.query === normalizedQuery ? searchResult.items : [])
        : conversations.filter((item) => (
          `${item.title} ${item.last_message_preview || ''}`
            .toLocaleLowerCase()
            .includes(normalizedQuery)
        ));
    }
    return [...source].sort((a, b) => (
      Number(Boolean(b.pinned)) - Number(Boolean(a.pinned))
      || new Date(b.updated_at) - new Date(a.updated_at)
    ));
  }, [conversations, normalizedQuery, onSearch, searchResult]);

  return <aside className={`v2-session-panel ${open ? 'is-open' : ''}`} aria-label="대화 기록">
    <header><div><span className="v2-eyebrow">Conversation history</span><h2>대화 기록</h2></div><div className="v2-session-header-actions"><button type="button" onClick={onCreate}>새 대화</button><button type="button" className="v2-session-close" onClick={onClose} aria-label="대화 기록 닫기">×</button></div></header>
    <label className="v2-session-search"><span className="sr-only">대화 기록 검색</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="대화 제목·내용 검색" /></label>
    <div className="v2-session-list" aria-busy={searching}>
      {visible.map((conversation) => <article className={conversation.id === activeId ? 'is-active' : ''} key={conversation.id}>
        <button type="button" className="v2-session-main" onClick={() => onSelect(conversation.id)}>
          <strong>{conversation.title || '새 대화'}</strong>
          <span>{conversation.search_preview || conversation.last_message_preview || '아직 대화 내용이 없습니다.'}</span>
          <small><time dateTime={conversation.updated_at}>{new Intl.DateTimeFormat('ko-KR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(conversation.updated_at))}</time><em>{conversation.message_count || 0}개 메시지{conversation.pending_proposal_count ? ` · 초안 ${conversation.pending_proposal_count}` : ''}</em></small>
        </button>
        <details className="v2-session-menu"><summary aria-label={`${conversation.title || '새 대화'} 관리`}>···</summary><div><button type="button" onClick={() => onRename(conversation)}>제목 변경</button><button type="button" className="is-danger" onClick={() => onDelete(conversation)}>삭제</button></div></details>
      </article>)}
      {searching && <div className="v2-session-empty" role="status"><strong>대화 내용을 검색하고 있어요</strong><p>제목과 전체 메시지를 확인하는 중입니다.</p></div>}
      {!searching && searchError && <div className="v2-session-empty" role="alert"><strong>검색하지 못했어요</strong><p>{searchError}</p></div>}
      {!searching && !searchError && !visible.length && <div className="v2-session-empty"><strong>{conversations.length ? '검색 결과가 없어요' : '아직 대화 기록이 없어요'}</strong><p>{conversations.length ? '다른 검색어를 입력해 보세요.' : '새 대화를 시작하면 여기에 기록됩니다.'}</p></div>}
    </div>
  </aside>;
}
