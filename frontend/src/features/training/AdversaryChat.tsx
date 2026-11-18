import { useEffect, useRef } from 'react';
import { IconBot } from '../../components/icons';
import { useTypewriter } from '../../hooks/useTypewriter';

export interface ChatMessage {
  role: 'user' | 'ai' | 'system';
  content: string;
  round?: number;
}

interface AdversaryChatProps {
  messages: ChatMessage[];
  loading?: boolean;
  title?: string;
}

/** AI 消息气泡：最新一条逐字输出（点击可跳过），历史消息直接显示 */
function StreamingBubble({ content, animate }: { content: string; animate: boolean }) {
  const { shown, done, skip } = useTypewriter(content, { step: 2, interval: 24, enabled: animate });
  return (
    <div
      className="chat-bubble"
      onClick={done ? undefined : skip}
      style={done ? undefined : { cursor: 'pointer' }}
      title={done ? undefined : '点击立即显示全部'}
    >
      {shown}
      {!done && <span className="type-cursor" aria-hidden />}
    </div>
  );
}

/** AI 对抗交互面板：展示用户提交与 AI 挑战，突出“对抗训练”而非普通聊天 */
export function AdversaryChat({ messages, loading = false, title = 'AI 对抗' }: AdversaryChatProps) {
  const endRef = useRef<HTMLDivElement>(null);
  // 只有最新一条 AI 消息播放打字机动画，历史消息直接显示
  const lastAiIndex = (() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === 'ai') return i;
    }
    return -1;
  })();

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, loading]);

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div className="card-head">
        <span
          style={{
            width: 26,
            height: 26,
            borderRadius: 8,
            display: 'grid',
            placeItems: 'center',
            background: 'var(--primary-soft)',
            border: '1px solid var(--primary-line)',
            color: 'var(--primary)',
          }}
          aria-hidden
        >
          <IconBot size={14} />
        </span>
        <div style={{ minWidth: 0 }}>
          <div className="card-title" style={{ lineHeight: 1.45, wordBreak: 'break-word' }}>
            {title}
          </div>
          <div className="micro" style={{ marginTop: 3 }}>Adversary · 不计分</div>
        </div>
        <div className="right">
          <span className="badge">每轮挑战不计分</span>
        </div>
      </div>

      <div className="chat-scroll">
        {messages.length === 0 && !loading && (
          <div className="chat-empty">
            阅读代码后，在下方提交你的审查意见，
            <br />
            AI 会针对你的结论发起质疑与追问。
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`chat-row${m.role === 'user' ? ' mine' : ''}`}>
            <div className="chat-ava" aria-hidden>
              {m.role === 'user' ? '我' : 'AI'}
            </div>
            <div className="chat-col">
              {m.round !== undefined && <div className="chat-round">第 {m.round} 轮</div>}
              {m.role === 'ai' ? (
                <StreamingBubble content={m.content} animate={i === lastAiIndex} />
              ) : (
                <div className={`chat-bubble${m.role === 'system' ? ' sys' : ''}`}>{m.content}</div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="chat-typing">
            <div className="chat-ava" aria-hidden>
              AI
            </div>
            <span>AI 正在推演你的意见</span>
            <span className="typing-dots" aria-hidden>
              <i />
              <i />
              <i />
            </span>
          </div>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
