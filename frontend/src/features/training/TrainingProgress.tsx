﻿﻿﻿import type { TrainingSession } from '../../types/training';

interface TrainingProgressBarProps {
  session: TrainingSession;
  currentIndex: number;
  onExit: () => void;
  onSettle: () => void;
  settling: boolean;
  submitting: boolean;
}

/** 训练工作台顶部状态栏：题号 / 轮次 / 预算 / 结算入口 */
export function TrainingProgressBar({
  session,
  currentIndex,
  onExit,
  onSettle,
  settling,
  submitting,
}: TrainingProgressBarProps) {
  const totalRounds = session.items.reduce((s, i) => s + i.target_rounds, 0);
  const doneRounds = session.items.reduce((s, i) => s + i.rounds_done, 0);
  const pct = totalRounds > 0 ? Math.round((doneRounds / totalRounds) * 100) : 0;
  const current = session.items[currentIndex];
  const budget = session.budget;

  const unverified = session.items.filter((i) => i.rounds_done < i.target_rounds).length;
  const allDone = unverified === 0;
  // 兜底：预算只够结算预留时，允许提前结算，未完成题目按当前进度评估
  const budgetLow = budget.remaining <= budget.reserve;
  const canSettle = allDone || budgetLow;

  const budgetCells = Array.from({ length: budget.cap }, (_, i) => {
    const used = budget.cap - budget.remaining;
    return i < used ? 'on' : '';
  });

  return (
    <div className="training-bar">
      <button className="btn btn-ghost btn-sm" onClick={onExit}>← 退出</button>

      <div className="topbar-sep" />

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
        <span className="micro">QUESTION</span>
        <span className="num" style={{ fontSize: 13, fontWeight: 600 }}>
          {currentIndex + 1} / {session.items.length}
        </span>
        <span
          style={{
            fontSize: 12.5,
            color: 'var(--text-secondary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {current?.title}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 160, maxWidth: 320 }}>
        <span className="micro" style={{ whiteSpace: 'nowrap' }}>ROUNDS {doneRounds}/{totalRounds}</span>
        <div className="progress" style={{ flex: 1 }}>
          <i style={{ width: `${pct}%` }} />
        </div>
      </div>

      <div
        style={{ display: 'flex', alignItems: 'center', gap: 10 }}
        title={`本场调用上限 ${budget.cap} 次，其中 ${budget.reserve} 次预留给结算`}
      >
        <span className="micro" style={{ whiteSpace: 'nowrap' }}>BUDGET {budget.remaining}/{budget.cap}</span>
        <div className={budgetLow ? 'budget low' : 'budget'}>
          {budgetCells.map((c, i) => (
            <i key={i} className={c} />
          ))}
        </div>
      </div>

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
        {!allDone && <span className="badge">{unverified} 题未完成</span>}
        {!allDone && budgetLow && <span className="badge badge-warning">预算不足</span>}
        <button
          className="btn btn-primary btn-sm"
          onClick={onSettle}
          disabled={settling || submitting || !canSettle}
          title={
            settling
              ? '结算中…'
              : submitting
                ? '正在提交审查意见…'
                : allDone
                  ? '全部题目完成，可结算'
                  : budgetLow
                    ? '预算只够结算，未完成题目将按当前进度评估'
                    : '完成全部题目轮次后才可结算'
          }
        >
          {settling ? '结算中…' : !allDone && budgetLow ? '预算不足，结算' : '结束并结算'}
        </button>
      </div>
    </div>
  );
}

