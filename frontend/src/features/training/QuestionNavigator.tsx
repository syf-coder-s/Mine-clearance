import type { TrainingItem } from '../../types/training';
import { IconCheck } from '../../components/icons';

interface QuestionNavigatorProps {
  items: TrainingItem[];
  currentId: string;
  onSelect: (itemId: string) => void;
}

function itemState(item: TrainingItem, currentId: string): 'current' | 'done' | 'todo' {
  if (item.item_id === currentId) return 'current';
  if (item.rounds_done >= item.target_rounds) return 'done';
  return 'todo';
}

/** 左侧题目导航与训练进度 */
export function QuestionNavigator({ items, currentId, onSelect }: QuestionNavigatorProps) {
  const totalRounds = items.reduce((s, i) => s + i.target_rounds, 0);
  const doneRounds = items.reduce((s, i) => s + i.rounds_done, 0);
  const pct = totalRounds > 0 ? Math.round((doneRounds / totalRounds) * 100) : 0;

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: 16 }}>
      <div>
        <div className="micro">QUESTIONS</div>
        <div className="card-title" style={{ marginTop: 6 }}>题目导航</div>
        <div className="card-sub" style={{ marginTop: 3 }}>本次固定 {items.length} 题 · 每题最多 3 轮</div>
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 7 }}>
          <span className="micro">进度</span>
          <span className="mono" style={{ color: 'var(--text-secondary)' }}>
            {doneRounds} / {totalRounds}
          </span>
        </div>
        <div className="progress">
          <i style={{ width: `${pct}%` }} />
        </div>
      </div>

      <div className="qnav-list">
        {items.map((item, idx) => {
          const st = itemState(item, currentId);
          return (
            <button
              key={item.item_id}
              onClick={() => onSelect(item.item_id)}
              className={`qnav-item${st === 'current' ? ' is-current' : ''}${st === 'done' ? ' is-done' : ''}`}
            >
              <span className="qnav-mark" aria-hidden>
                {st === 'done' ? <IconCheck size={11} /> : idx + 1}
              </span>
              <span style={{ minWidth: 0, flex: 1 }}>
                <span
                  className="qnav-title"
                  style={{
                    display: 'block',
                    fontSize: 12.5,
                    fontWeight: 600,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {item.title}
                </span>
                <span
                  className="qnav-id"
                  style={{
                    display: 'block',
                    marginTop: 3,
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                  }}
                >
                  {item.item_id}
                </span>
                <span className="qnav-rounds" style={{ display: 'block', marginTop: 4, fontSize: 11 }}>
                  轮次 {item.rounds_done} / {item.target_rounds}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
