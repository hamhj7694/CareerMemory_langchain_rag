const defaultEmptyText = '작성된 내용이 없습니다.';

function renderInline(text) {
  const nodes = [];
  const source = String(text ?? '');
  const pattern = /(\*\*.+?\*\*|\*.+?\*|`.+?`)/g;
  let lastIndex = 0;
  let match;
  while ((match = pattern.exec(source)) !== null) {
    const index = match.index;
    if (index > lastIndex) nodes.push(source.slice(lastIndex, index));
    const token = match[0];
    if (token.startsWith('**')) nodes.push(<strong key={`${index}-strong`}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith('*')) nodes.push(<em key={`${index}-em`}>{token.slice(1, -1)}</em>);
    else nodes.push(<code key={`${index}-code`}>{token.slice(1, -1)}</code>);
    lastIndex = index + token.length;
  }
  if (lastIndex < source.length) nodes.push(source.slice(lastIndex));
  return nodes;
}

function buildList(items) {
  const roots = [];
  const stack = [];
  const indentSize = 2;
  items.forEach((item, index) => {
    const level = Math.max(0, Math.floor(item.indent / indentSize));
    const node = { ...item, children: [], key: `${item.text}-${index}` };
    while (stack.length > level) stack.pop();
    if (stack.length === 0) roots.push(node);
    else stack[stack.length - 1].children.push(node);
    stack[level] = node;
    stack.length = level + 1;
  });

  const renderNodes = (nodes) => {
    if (!nodes.length) return null;
    const groups = [];
    nodes.forEach((node) => {
      const current = groups[groups.length - 1];
      if (!current || current.ordered !== node.ordered) groups.push({ ordered: node.ordered, nodes: [node] });
      else current.nodes.push(node);
    });
    return groups.map((group, groupIndex) => {
      const List = group.ordered ? 'ol' : 'ul';
      return (
        <List key={`${group.ordered ? 'ol' : 'ul'}-${groupIndex}`}>
          {group.nodes.map((node) => (
            <li key={node.key}>
              {renderInline(node.text)}
              {node.children.length ? renderNodes(node.children) : null}
            </li>
          ))}
        </List>
      );
    });
  };

  return renderNodes(roots);
}

export function ExperienceRichText({ text, empty = defaultEmptyText }) {
  const lines = String(text ?? '').split('\n');
  const blocks = [];
  let paragraph = [];
  let listItems = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(<p key={`p-${blocks.length}`}>{paragraph.map((line, index) => <span key={`${line}-${index}`}>{index > 0 && <br />}{renderInline(line)}</span>)}</p>);
    paragraph = [];
  };
  const flushList = () => {
    if (!listItems.length) return;
    blocks.push(<div key={`list-${blocks.length}`}>{buildList(listItems)}</div>);
    listItems = [];
  };

  lines.forEach((rawLine) => {
    const line = rawLine ?? '';
    if (!line.trim()) {
      flushParagraph();
      flushList();
      return;
    }
    const bulletMatch = line.match(/^(\s*)([-*+])\s+(.*)$/);
    const orderedMatch = line.match(/^(\s*)(\d+)[.)]\s+(.*)$/);
    if (bulletMatch || orderedMatch) {
      flushParagraph();
      listItems.push({
        indent: (bulletMatch ? bulletMatch[1] : orderedMatch[1]).length,
        text: bulletMatch ? bulletMatch[3] : orderedMatch[3],
        ordered: Boolean(orderedMatch),
      });
      return;
    }
    flushList();
    paragraph.push(line);
  });

  flushParagraph();
  flushList();
  return blocks.length ? blocks : <p>{empty}</p>;
}

export function ExperienceRichList({ items, empty = defaultEmptyText }) {
  return <ExperienceRichText text={(items ?? []).join('\n')} empty={empty} />;
}
