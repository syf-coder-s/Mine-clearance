import { useEffect, useMemo, useRef, useState } from 'react';
import type { TrainingItem } from '../../types/training';
import { useTypewriter } from '../../hooks/useTypewriter';

/* ---------- 简易 Python 语法着色（自研，替代 Monaco，降低依赖） ---------- */

const TOKEN_RE =
  /(#[^\n]*)|('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")|\b(def|return|if|elif|else|while|for|in|print|import|from|None|True|False|lambda|class|with|try|except|raise|break|continue|pass|and|or|not|is|yield|assert|global|del|async|await)\b|\b(\d+(?:\.\d+)?)\b/g;

interface Token {
  text: string;
  cls: string;
}

function tokenize(line: string): Token[] {
  const tokens: Token[] = [];
  let last = 0;
  TOKEN_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = TOKEN_RE.exec(line)) !== null) {
    if (m.index > last) tokens.push({ text: line.slice(last, m.index), cls: 'pln' });
    let cls = 'pln';
    if (m[1]) cls = 'com';
    else if (m[2]) cls = 'str';
    else if (m[3]) cls = 'kwd';
    else if (m[4]) cls = 'num';
    tokens.push({ text: m[0], cls });
    last = m.index + m[0].length;
  }
  if (last < line.length) tokens.push({ text: line.slice(last), cls: 'pln' });
  return tokens;
}

const CLS_COLOR: Record<string, string> = {
  pln: 'var(--code-ink)',
  com: 'var(--code-comment)',
  str: 'var(--code-string)',
  kwd: 'var(--code-keyword)',
  num: 'var(--code-number)',
};

interface CodePanelProps {
  item: TrainingItem;
  /** 选中的代码行（选中内容可作为审查上下文） */
  onSelectLines?: (start: number, end: number, snippet: string) => void;
  /** 证据高亮行段列表（1-based、闭区间，可多条）；null/空 表示无高亮 */
  highlight?: Array<{ start: number; end: number }> | null;
}

/** 代码阅读面板：只读、行号、简易高亮、支持选中行复制；出题时代码逐字打出（点击可跳过） */
export function CodePanel({ item, onSelectLines, highlight = null }: CodePanelProps) {
  const fullCode = useMemo(() => item.code.replace(/\r\n/g, '\n').replace(/\n$/, ''), [item.code]);
  const fullLineCount = useMemo(() => fullCode.split('\n').length, [fullCode]);
  // 出题打字机：整段代码到达后逐字放出，模拟 AI 生成；点击代码区可跳过
  const { shown: shownCode, done: codeDone, skip: skipCode } = useTypewriter(item.code, {
    step: 12,
    interval: 16,
  });
  const lines = useMemo(
    () => (codeDone ? fullCode : shownCode.replace(/\r\n/g, '\n').replace(/\n$/, '')).split('\n'),
    [codeDone, fullCode, shownCode],
  );
  const [selected, setSelected] = useState<[number, number] | null>(null);
  const lineRefs = useRef(new Map<number, HTMLDivElement>());

  const hlRanges: Array<[number, number]> = useMemo(
    () =>
      (highlight ?? [])
        .filter((r) => r.start >= 1 && r.end >= r.start)
        .map((r) => [r.start - 1, Math.min(r.end - 1, fullLineCount - 1)] as [number, number]),
    [highlight, fullLineCount],
  );

  useEffect(() => {
    if (hlRanges.length === 0) return;
    const target = lineRefs.current.get(Math.max(0, hlRanges[0][0]));
    target?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [hlRanges]);

  const handleMouseUp = () => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !onSelectLines) return;
    const container = sel.anchorNode?.parentElement?.closest('[data-code-container]');
    if (!container) return;
    const lineEls = Array.from(container.querySelectorAll<HTMLElement>('[data-line]'));
    const selLines = lineEls
      .map((el, idx) => ({ idx, el }))
      .filter(({ el }) => {
        const r = sel.getRangeAt(0);
        return r.intersectsNode(el);
      });
    if (selLines.length === 0) return;
    const start = selLines[0].idx;
    const end = selLines[selLines.length - 1].idx;
    setSelected([start, end]);
    onSelectLines(start + 1, end + 1, sel.toString());
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        flex: 1,
        minWidth: 0,
      }}
    >
      <div className="code-head">
        <span className="win-dots" aria-hidden>
          <i />
          <i />
          <i />
        </span>
        <div style={{ minWidth: 0, display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span className="code-file">{item.title}</span>
          <span className="code-meta">
            {item.item_id} · {item.language}
          </span>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {hlRanges.length > 0 && <span className="badge badge-danger">已定位证据</span>}
          {!codeDone ? (
            <span
              className="badge"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
              title="点击代码区可立即显示全部"
            >
              AI 出题中
              <span className="typing-dots" aria-hidden>
                <i />
                <i />
                <i />
              </span>
            </span>
          ) : (
            <span className="badge">只读</span>
          )}
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => navigator.clipboard?.writeText(item.code)}
            title="复制全部代码"
          >
            复制
          </button>
        </div>
      </div>

      <div
        className="code-body"
        data-code-container
        onMouseUp={handleMouseUp}
        onClick={codeDone ? undefined : skipCode}
        style={{ cursor: codeDone ? undefined : 'pointer' }}
      >
        <pre>
          {lines.map((line, i) => {
            const inSel = selected && i >= selected[0] && i <= selected[1];
            const inHl = hlRanges.some(([a, b]) => i >= a && i <= b);
            return (
              <div
                key={i}
                data-line
                ref={(el) => {
                  if (el) lineRefs.current.set(i, el);
                  else lineRefs.current.delete(i);
                }}
                className={`code-line${inSel ? ' is-sel' : ''}${inHl ? ' is-hl' : ''}`}
              >
                <span className="gutter">{i + 1}</span>
                <span className="src">
                  {tokenize(line).map((t, j) => (
                    <span
                      key={j}
                      style={{ color: CLS_COLOR[t.cls], fontStyle: t.cls === 'com' ? 'italic' : undefined }}
                    >
                      {t.text}
                    </span>
                  ))}
                </span>
              </div>
            );
          })}
          {!codeDone && (
            <div className="code-line" aria-hidden>
              <span className="gutter">{lines.length + 1}</span>
              <span className="src">
                <span className="type-cursor" />
              </span>
            </div>
          )}
        </pre>
      </div>
    </div>
  );
}

