﻿﻿﻿import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import type { MouseEvent as ReactMouseEvent } from 'react';
import { TrainingLayout } from '../layouts/TrainingLayout';
import { TrainingProgressBar } from '../features/training/TrainingProgress';
import { QuestionNavigator } from '../features/training/QuestionNavigator';
import { CodePanel } from '../features/training/CodePanel';
import { AdversaryChat, type ChatMessage } from '../features/training/AdversaryChat';
import { ReviewForm } from '../features/training/ReviewForm';
import { EvidencePanel } from '../features/training/EvidencePanel';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { getSession, submitReview, settleSession } from '../services/trainingService';
import type { SubmitRequest, TrainingSession } from '../types/training';

/* ---------- 三栏栏宽（左/右可拖拽调节，中栏占剩余空间） ---------- */
type ColSide = 'left' | 'right';
const COL_MIN: Record<ColSide, number> = { left: 180, right: 340 };
const COL_MAX: Record<ColSide, number> = { left: 420, right: 760 };
const COL_DEFAULT: Record<ColSide, number> = { left: 232, right: 440 };
const COL_STORE_KEY = 'mc.training.colWidths.v1';

function loadColWidths(): Record<ColSide, number> {
  try {
    const raw = localStorage.getItem(COL_STORE_KEY);
    if (raw) {
      const p = JSON.parse(raw) as Partial<Record<ColSide, number>>;
      return {
        left: Math.min(Math.max(p.left ?? COL_DEFAULT.left, COL_MIN.left), COL_MAX.left),
        right: Math.min(Math.max(p.right ?? COL_DEFAULT.right, COL_MIN.right), COL_MAX.right),
      };
    }
  } catch {
    /* 损坏的本地记录按默认值处理 */
  }
  return { ...COL_DEFAULT };
}

/**
 * 训练工作台（核心页面）
 * 三栏：左题目导航 / 中代码阅读 / 右 AI 对抗；底部可折叠证据面板。
 */
export function TrainingPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [session, setSession] = useState<TrainingSession | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [currentId, setCurrentId] = useState<string>('');
  const [messages, setMessages] = useState<Record<string, ChatMessage[]>>({});
  const [citedIds, setCitedIds] = useState<string[]>([]);
  const [selectedContext, setSelectedContext] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);
  const [settling, setSettling] = useState(false);
  const [settleOpen, setSettleOpen] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // 「定位」按钮的临时高亮；引用勾选产生的高亮由 citedIds 派生
  const [locateHl, setLocateHl] = useState<{ start: number; end: number } | null>(null);
  // 左右栏宽：可拖拽调节并持久化，中栏占剩余空间，整体铺满窗口不留大白边
  const [colWidths, setColWidths] = useState<Record<ColSide, number>>(loadColWidths);
  const colRef = useRef(colWidths);
  useEffect(() => {
    colRef.current = colWidths;
  }, [colWidths]);

  const beginResize = useCallback((side: ColSide) => (e: ReactMouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = colRef.current[side];
    const onMove = (ev: MouseEvent) => {
      const dx = ev.clientX - startX;
      const w = side === 'left' ? startW + dx : startW - dx;
      setColWidths((prev) => ({
        ...prev,
        [side]: Math.min(Math.max(w, COL_MIN[side]), COL_MAX[side]),
      }));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      try {
        localStorage.setItem(COL_STORE_KEY, JSON.stringify(colRef.current));
      } catch {
        /* 存不上就下次用默认值 */
      }
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    getSession(id).then(
      (s) => {
        if (!alive) return;
        setSession(s);
        setCurrentId(s.items[0]?.item_id ?? '');
        // 会话已结算：直接引导到报告
        if (s.status === 'finished') navigate(`/report/${s.session_id}`, { replace: true });
      },
      (e) => alive && setLoadError(e?.body?.message ?? '会话加载失败'),
    );
    return () => {
      alive = false;
    };
  }, [id, navigate]);

  const current = session?.items.find((i) => i.item_id === currentId);

  const budgetInsufficient = session ? session.budget.remaining <= session.budget.reserve : false;

  // 勾选引用的证据自动高亮对应代码行（多条合并），叠加「定位」按钮的临时高亮
  const highlight = useMemo(() => {
    const ranges: Array<{ start: number; end: number }> = [];
    for (const ev of current?.evidence ?? []) {
      if (citedIds.includes(ev.evidence_id) && ev.line_start && ev.line_end) {
        ranges.push({ start: ev.line_start, end: ev.line_end });
      }
    }
    if (locateHl) ranges.push(locateHl);
    return ranges.length > 0 ? ranges : null;
  }, [current, citedIds, locateHl]);

  const toggleCite = useCallback((evidenceId: string) => {
    setCitedIds((prev) => (prev.includes(evidenceId) ? prev.filter((x) => x !== evidenceId) : [...prev, evidenceId]));
  }, []);

  const clearCited = useCallback(() => setCitedIds([]), []);

  const handleSubmit = async (req: SubmitRequest) => {
    if (!session || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    const round = (current?.rounds_done ?? 0) + 1;
    setMessages((m) => ({
      ...m,
      [req.item_id]: [
        ...(m[req.item_id] ?? []),
        { role: 'user', content: req.text + (selectedContext ? `\n\n【引用代码】\n${selectedContext}` : ''), round },
      ],
    }));
    try {
      const res = await submitReview(session.session_id, req);
      setSession((s) =>
        s
          ? {
              ...s,
              budget: res.budget,
              items: s.items.map((it) =>
                it.item_id === res.item_id ? { ...it, rounds_done: res.rounds_done } : it,
              ),
              unverified_items: s.items.filter(
                (it) => (it.item_id === res.item_id ? res.rounds_done : it.rounds_done) < it.target_rounds,
              ).length,
            }
          : s,
      );
      setMessages((m) => ({
        ...m,
        [res.item_id]: [...(m[res.item_id] ?? []), { role: 'ai', content: res.challenge, round: res.round }],
      }));
      if (res.reason === 'budget_guard') {
        setSubmitError('调用预算已不足，请尽快完成剩余题目或结算。');
      }
    } catch (e) {
      const msg = (e as { body?: { message?: string } })?.body?.message ?? '提交失败，请重试';
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const openSettle = () => {
    if (!session) return;
    const allDone = session.items.every((i) => i.rounds_done >= i.target_rounds);
    const budgetLow = session.budget.remaining <= session.budget.reserve;
    // 只有全部完成或预算不足兜底才允许打开结算确认框，不做任意提前结算入口
    if (!allDone && !budgetLow) return;
    setSettleOpen(true);
  };

  const doSettle = async () => {
    if (!session) return;
    setSettleOpen(false);
    setSettling(true);
    setSubmitError(null);
    try {
      await settleSession(session.session_id);
      // 携带 freshSettle 标记：报告页复盘走逐字输出
      navigate(`/report/${session.session_id}`, { replace: true, state: { freshSettle: true } });
    } catch (e) {
      const msg = (e as { body?: { message?: string } })?.body?.message ?? '结算失败，请重试';
      setSubmitError(msg);
      setSettling(false);
    }
  };

  if (loadError) {
    return (
      <TrainingLayout>
        <ErrorState
          title="训练会话加载失败"
          message={loadError}
          onRetry={() => window.location.reload()}
        />
      </TrainingLayout>
    );
  }

  if (!session || !current) {
    return (
      <TrainingLayout>
        <LoadingState text="正在进入训练工作台…" full />
      </TrainingLayout>
    );
  }

  const completedItems = session.items.filter((i) => i.rounds_done >= i.target_rounds).length;
  const hasIncomplete = completedItems < session.items.length;

  return (
    <TrainingLayout>
      <TrainingProgressBar
        session={session}
        currentIndex={session.items.findIndex((i) => i.item_id === currentId)}
        onExit={() => navigate('/dashboard')}
        onSettle={openSettle}
        settling={settling}
        submitting={submitting}
      />

      {/* 三栏主体：铺满窗口不留大白边；左右栏宽可拖拽调节（会记住），中栏占剩余空间 */}
      <div style={{ flex: 1, display: 'flex', padding: 16, minHeight: 0 }}>
        {/* 左：题目导航 */}
        <div style={{ width: colWidths.left, flexShrink: 0, overflowY: 'auto' }}>
          <QuestionNavigator
            items={session.items}
            currentId={currentId}
            onSelect={(itemId) => {
              setCurrentId(itemId);
              setCitedIds([]);
              setSelectedContext('');
              setSubmitError(null);
              setLocateHl(null);
            }}
          />
        </div>

        <div
          className="col-resizer"
          role="separator"
          aria-orientation="vertical"
          title="拖拽调节栏宽"
          onMouseDown={beginResize('left')}
        />

        {/* 中：代码阅读（含底部证据面板），占剩余宽度 */}
        <div
          style={{
            flex: '1 1 0',
            minWidth: 380,
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
          }}
        >
          <div className="card" style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
            <CodePanel
              item={current}
              onSelectLines={(_s, _e, snippet) => setSelectedContext(snippet)}
              highlight={highlight}
            />
          </div>
          <div className="card" style={{ marginTop: 16, overflow: 'hidden', maxWidth: '100%' }}>
            <EvidencePanel
              evidence={current.evidence}
              citedIds={citedIds}
              onToggleCite={toggleCite}
              onLocate={(ev) =>
                setLocateHl(
                  ev.line_start && ev.line_end ? { start: ev.line_start, end: ev.line_end } : null,
                )
              }
            />
          </div>
        </div>

        <div
          className="col-resizer"
          role="separator"
          aria-orientation="vertical"
          title="拖拽调节栏宽"
          onMouseDown={beginResize('right')}
        />

        {/* 右：AI 对抗 + 审查表单 */}
        <div
          style={{
            width: colWidths.right,
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
            minHeight: 0,
          }}
        >
          <div style={{ flex: 1, minHeight: 0 }}>
            <AdversaryChat
              messages={messages[currentId] ?? []}
              loading={submitting}
              title={`AI 对抗 · ${current.title}`}
            />
          </div>
          <ReviewForm
            key={currentId}
            itemId={currentId}
            roundsDone={current.rounds_done}
            targetRounds={current.target_rounds}
            disabled={budgetInsufficient || session.status === 'finished'}
            submitting={submitting}
            citedIds={citedIds}
            onClearCited={clearCited}
            onSubmit={handleSubmit}
          />
          {submitError && (
            <div style={{ fontSize: 12, color: 'var(--danger)', padding: '0 4px' }}>{submitError}</div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={settleOpen}
        title={hasIncomplete ? '预算不足，提前结算' : '结束训练并结算'}
        desc={
          <div style={{ lineHeight: 1.8 }}>
            {hasIncomplete && (
              <>
                <span style={{ color: 'var(--warning)' }}>
                  还有 {session.items.length - completedItems} 道题未完成。当前预算只够结算，未完成题目将按当前进度评估，报告会标注实际完成数。
                </span>
                <br />
              </>
            )}
            结算后将生成训练报告，剩余调用预算为 <b>{session.budget.remaining}</b> 次。
            <br />
            结算后本次训练不可再提交审查意见。
          </div>
        }
        confirmText={hasIncomplete ? '确认提前结算' : '确认结算'}
        danger={hasIncomplete}
        onConfirm={doSettle}
        onCancel={() => setSettleOpen(false)}
      />
    </TrainingLayout>
  );
}

