import { useState } from 'react';
import type { SubmitRequest } from '../../types/training';

interface ReviewFormProps {
  itemId: string;
  roundsDone: number;
  targetRounds: number;
  disabled: boolean;
  submitting: boolean;
  /** 已勾选引用的证据 ID（与 EvidencePanel 联动） */
  citedIds: string[];
  /** 清空全部已勾选证据（独立回调，不使用哨兵值） */
  onClearCited: () => void;
  onSubmit: (req: SubmitRequest) => void;
}

/** 审查意见提交表单 */
export function ReviewForm({
  itemId,
  roundsDone,
  targetRounds,
  disabled,
  submitting,
  citedIds,
  onClearCited,
  onSubmit,
}: ReviewFormProps) {
  const [text, setText] = useState('');
  const [fix, setFix] = useState('');

  const reachLimit = roundsDone >= targetRounds;

  const handleSubmit = () => {
    if (!text.trim() || disabled || submitting || reachLimit) return;
    // 题目切换时重置（由 key 控制，父页面用 itemId 作为 key）
    onSubmit({
      item_id: itemId,
      text: text.trim(),
      cited_evidence_ids: citedIds,
      proposed_fix: fix.trim(),
    });
    setText('');
    setFix('');
  };

  return (
    <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="card-title">提交审查意见</span>
        <span className="badge badge-neutral">
          第 {Math.min(roundsDone + 1, targetRounds)} / {targetRounds} 轮
        </span>
      </div>

      <textarea
        className="textarea"
        placeholder="描述你发现的问题：可疑代码位置、触发条件、影响后果…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled || submitting || reachLimit}
      />

      <div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
          引用证据（请在底部证据面板中勾选，随意见一并提交）
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
          {citedIds.length > 0 ? (
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--primary)' }}>
              {citedIds.join('、')}
            </span>
          ) : (
            '未引用证据'
          )}
        </div>
      </div>

      <textarea
        className="textarea"
        placeholder="修复建议（可选，可留空）"
        value={fix}
        onChange={(e) => setFix(e.target.value)}
        disabled={disabled || submitting || reachLimit}
        style={{ minHeight: 56 }}
      />

      {reachLimit ? (
        <div style={{ fontSize: 12, color: 'var(--success)' }}>
          本题已达成 {targetRounds} 轮对抗目标，可切换到下一题。
        </div>
      ) : disabled ? (
        <div style={{ fontSize: 12, color: 'var(--warning)' }}>
          预算不足或会话已结算，无法继续提交。
        </div>
      ) : null}

      <button
        className="btn btn-primary"
        onClick={handleSubmit}
        disabled={disabled || submitting || reachLimit || !text.trim()}
      >
        {submitting ? '提交中…' : '提交审查意见'}
      </button>
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        <button
          className="btn btn-ghost btn-sm"
          onClick={onClearCited}
          disabled={citedIds.length === 0}
          type="button"
        >
          清空引用
        </button>
      </div>
    </div>
  );
}