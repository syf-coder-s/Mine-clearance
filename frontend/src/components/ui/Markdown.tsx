import type { CSSProperties, ReactNode } from 'react';

/**
 * 极简 Markdown 渲染器（安全纯文本渲染，不使用 dangerouslySetInnerHTML）
 * 仅支持报告所需语法：# / ## / ### 标题（映射为 h3/h4/h5）、- / * 无序列表、
 * > 引用块、**粗体**、`行内代码`、空行分段；其余语法按普通文本原样显示。
 * 纯函数组件：无副作用、不读取 localStorage、不引入外部依赖。
 */

const INLINE_PATTERN = /(\*\*[^*]+\*\*|`[^`]+`)/g;
const BASE_BLOCK: CSSProperties = { fontSize: 13, lineHeight: 1.75, margin: 0 };
const CODE_STYLE: CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  background: 'var(--bg)',
  padding: '1px 5px',
  borderRadius: 'var(--radius-control)',
};

/** 行内格式：**粗体** → <strong>，`代码` → <code> */
function renderInline(text: string): ReactNode[] {
  return text
    .split(INLINE_PATTERN)
    .filter((part) => part.length > 0)
    .map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**') && part.length >= 4) {
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('`') && part.endsWith('`') && part.length >= 2) {
        return (
          <code key={i} style={CODE_STYLE}>
            {part.slice(1, -1)}
          </code>
        );
      }
      return <span key={i}>{part}</span>;
    });
}

export function Markdown({ content }: { content: string }) {
  const lines = (content ?? '').replace(/\r\n/g, '\n').split('\n');
  const blocks: ReactNode[] = [];
  let index = 0;
  let key = 0;
  let paragraph: string[] = [];

  const pushParagraph = () => {
    if (paragraph.length === 0) return;
    blocks.push(
      <p key={`p-${key++}`} style={BASE_BLOCK}>
        {paragraph.map((line, i) => (
          <span key={i}>
            {i > 0 && <br />}
            {renderInline(line)}
          </span>
        ))}
      </p>,
    );
    paragraph = [];
  };

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (trimmed === '') {
      pushParagraph();
      index += 1;
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      pushParagraph();
      const text = heading[2];
      if (heading[1] === '#') {
        blocks.push(
          <h3 key={`h-${key++}`} style={{ ...BASE_BLOCK, fontSize: 15, fontWeight: 700 }}>
            {renderInline(text)}
          </h3>,
        );
      } else if (heading[1] === '##') {
        blocks.push(
          <h4 key={`h-${key++}`} style={{ ...BASE_BLOCK, fontSize: 14, fontWeight: 600 }}>
            {renderInline(text)}
          </h4>,
        );
      } else {
        blocks.push(
          <h5 key={`h-${key++}`} style={{ ...BASE_BLOCK, fontSize: 13, fontWeight: 600 }}>
            {renderInline(text)}
          </h5>,
        );
      }
      index += 1;
      continue;
    }

    const listMatch = /^[-*]\s+(.+)$/.exec(trimmed);
    if (listMatch) {
      pushParagraph();
      const items: string[] = [];
      while (index < lines.length) {
        const m = /^[-*]\s+(.+)$/.exec(lines[index].trim());
        if (!m) break;
        items.push(m[1]);
        index += 1;
      }
      blocks.push(
        <ul key={`ul-${key++}`} style={{ margin: 0, paddingLeft: 20, ...BASE_BLOCK }}>
          {items.map((item, i) => (
            <li key={i}>{renderInline(item)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    if (/^>\s?/.test(trimmed)) {
      pushParagraph();
      const quoteLines: string[] = [];
      while (index < lines.length) {
        const m = /^>\s?(.*)$/.exec(lines[index].trim());
        if (!m) break;
        quoteLines.push(m[1]);
        index += 1;
      }
      blocks.push(
        <blockquote
          key={`q-${key++}`}
          style={{
            ...BASE_BLOCK,
            borderLeft: '2px solid var(--border)',
            background: 'var(--bg)',
            borderRadius: 'var(--radius-control)',
            padding: '6px 12px',
          }}
        >
          {quoteLines.map((q, i) => (
            <span key={i}>
              {i > 0 && <br />}
              {renderInline(q)}
            </span>
          ))}
        </blockquote>,
      );
      continue;
    }

    // 其他情况：按普通段落原样收集（不认识的语法不做特殊处理）
    paragraph.push(line);
    index += 1;
  }
  pushParagraph();

  if (blocks.length === 0) return null;

  return <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{blocks}</div>;
}