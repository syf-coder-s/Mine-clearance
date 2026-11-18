﻿﻿﻿import { useEffect, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { DashboardLayout } from '../layouts/DashboardLayout';
import { PageHeader } from '../components/common/PageHeader';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { Markdown } from '../components/ui/Markdown';
import { useTypewriter } from '../hooks/useTypewriter';
import { getReport } from '../services/reportService';
import { getSession } from '../services/trainingService';
import { isMockMode } from '../services/apiClient';
import { directionLabel, LANGUAGE_LABELS } from '../mocks/historyMock';
import type { SettleReport, DefenseLevel } from '../types/report';
import type { TrainingSession } from '../types/training';

const LEVEL_STYLE: Record<DefenseLevel, { cls: string; desc: string }> = {
  L0: { cls: 'badge-danger', desc: '误报或错误归因' },
  L1: { cls: 'badge-warning', desc: '意识到可能存在问题' },
  L2: { cls: 'badge-primary', desc: '能定位问题' },
  L3: { cls: 'badge-success', desc: '能解释触发条件' },
  L4: { cls: 'badge-neutral', desc: '能给出可执行修复方案' },
};

/** 通用建议：仅在复盘文字缺失时展示，非本场生成 */
const GENERIC_TIPS = [
  '在提交意见前，先用最小输入样例验证可疑路径，避免误报（对应 L0 风险）。',
  '对定位到的问题，说明触发条件与影响范围，训练解释能力（对应 L2→L3）',
  '给出可执行的修复方案并说明回归验证方式（对应 L4）',
];

/** 训练报告页：总体概览 + 分题 L0–L4 卡片 + 复盘（不合成总分） */
export function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [report, setReport] = useState<SettleReport | null>(null);
  const [session, setSession] = useState<TrainingSession | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 只有刚结算跳转过来时复盘才播放逐字输出；从历史等入口进入直接显示全文
  const freshSettle = !!(location.state as { freshSettle?: boolean } | null)?.freshSettle;
  const markdownSource = report?.markdown ?? '';
  const { shown: shownMd, done: mdDone, skip: skipMd } = useTypewriter(markdownSource, {
    step: 8,
    interval: 16,
    enabled: freshSettle,
  });

  useEffect(() => {
    if (!id) return;
    let alive = true;
    Promise.all([getReport(id), getSession(id)]).then(
      ([r, s]) => {
        if (!alive) return;
        setReport(r);
        setSession(s);
      },
      (e) => alive && setError(e?.body?.message ?? '报告加载失败'),
    );
    return () => {
      alive = false;
    };
  }, [id]);

  if (error) {
    return (
      <DashboardLayout>
        <ErrorState title="报告加载失败" message={error} onRetry={() => window.location.reload()} />
      </DashboardLayout>
    );
  }
  if (!report || !session) {
    return (
      <DashboardLayout>
        <LoadingState text="正在生成训练报告…" full />
      </DashboardLayout>
    );
  }

  // 实际完成数：预算不足提前结算时可能小于题目总数
  const completedItems = session.items.filter((i) => i.rounds_done >= i.target_rounds).length;
  const incomplete = session.items.length - completedItems;

  return (
    <DashboardLayout>
      <div className="page">
        <PageHeader
          extra={
            <>
              <span style={{ fontSize: 12, color: 'var(--text-tertiary)', marginRight: 'auto' }}>
                训练 ID：{session.session_id} · {new Date().toLocaleString('zh-CN')} · 已结算
              </span>
              <button className="btn btn-outline" onClick={() => navigate('/history')}>
                查看历史
              </button>
              <button className="btn btn-primary" onClick={() => navigate('/training/setup')}>
                再训一场
              </button>
            </>
          }
        />

        {/* 总体概览 */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
          <div className="card card-pad">
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>完成题目</div>
            <div style={{ fontSize: 24, fontWeight: 700 }}>
              {incomplete > 0 ? `${completedItems} / ${session.items.length} 道` : `${session.items.length} 道`}
            </div>
          </div>
          <div className="card card-pad">
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>训练方向</div>
            <div style={{ fontSize: 15, fontWeight: 700, marginTop: 4 }}>{directionLabel(session.direction ?? 'random')}</div>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{LANGUAGE_LABELS[session.language ?? 'python']}</div>
          </div>
          <div className="card card-pad">
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>模型调用</div>
            <div style={{ fontSize: 24, fontWeight: 700 }}>
              {report.calls} <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>/ {session.budget.cap} 次</span>
            </div>
          </div>
          <div className="card card-pad">
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>估算费用</div>
            <div style={{ fontSize: 24, fontWeight: 700 }}>¥{report.cost_cny.toFixed(2)}</div>
            <div style={{ fontSize: 11, color: report.cost_known === false ? 'var(--warning)' : 'var(--text-tertiary)' }}>
              {isMockMode() ? '演示估算' : report.cost_known === false ? '单价未核定（cost=0 为未估价）' : '按核定价估算'}
            </div>
          </div>
        </div>

        {/* 预算不足提前结算提示 */}
        {incomplete > 0 && (
          <div
            className="card card-pad"
            style={{
              marginTop: 16,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              borderLeft: '3px solid var(--warning)',
            }}
          >
            <span style={{ fontSize: 13, color: 'var(--warning)', fontWeight: 600, lineHeight: 1.7 }}>
              本场为预算不足提前结算：完成 {completedItems} / {session.items.length} 题，未完成 {incomplete} 题。未完成题目按当前进度评估，报告不补分。
            </span>
          </div>
        )}

        {/* 分题结果 */}
        <h2 style={{ fontSize: 15, marginTop: 8 }}>分题评估（L0–L4）</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {report.verdicts.map((v) => {
            const item = session.items.find((i) => i.item_id === v.item_id);
            const itemIncomplete = item ? item.rounds_done < item.target_rounds : false;
            const st = LEVEL_STYLE[v.level] ?? LEVEL_STYLE.L2;
            return (
              <div key={v.item_id} className="card card-pad">
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <span className={`badge ${st.cls}`} style={{ fontSize: 13, padding: '4px 12px' }}>
                    {v.level}
                  </span>
                  {itemIncomplete && <span className="badge badge-warning">未完成题目</span>}
                  <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{st.desc}</span>
                  <span className="badge badge-neutral">
                    {v.label === 'defect_present' ? '缺陷存在' : '未发现缺陷'}
                  </span>
                  {v.escalated && <span className="badge badge-success">已晋级</span>}
                  <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-secondary)' }}>
                    置信度 {(v.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 10 }}>
                  {v.item_id} · {item?.title ?? ''}
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.7 }}>
                  {v.rationale}
                </div>
                {itemIncomplete && (
                  <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 6 }}>
                    本题未完成既定轮次，等级仅供参考。
                  </div>
                )}
                <div style={{ display: 'flex', gap: 10, marginTop: 10, fontSize: 11, color: 'var(--text-tertiary)', flexWrap: 'wrap' }}>
                  <span>
                    引用核验：精确 {Math.round(v.citation.precision * 100)}% · 召回 {Math.round(v.citation.recall * 100)}%
                  </span>
                  <span>交互轮次：{item?.rounds_done ?? 0} / {item?.target_rounds ?? 3}</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 10 }}>
                  {v.citation.supported.length > 0 && (
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
                        引用正确
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {v.citation.supported.map((evidenceId) => {
                          const ref = v.references.find((r) => r.evidence_id === evidenceId);
                          return (
                            <div
                              key={evidenceId}
                              style={{
                                display: 'flex',
                                gap: 8,
                                alignItems: 'flex-start',
                                padding: '8px 10px',
                                background: 'var(--bg)',
                                borderRadius: 'var(--radius-control)',
                              }}
                            >
                              <span
                                className="badge badge-neutral"
                                style={{ flexShrink: 0, fontFamily: 'var(--font-mono)' }}
                              >
                                {evidenceId}
                              </span>
                              {ref?.quote ? (
                                <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                                  {ref.quote.length > 180 ? `${ref.quote.slice(0, 180)}…` : ref.quote}
                                </span>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                  {v.citation.unsupported.length > 0 && (
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
                        引用未被支持
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {v.citation.unsupported.map((evidenceId) => (
                          <span key={evidenceId} className="badge badge-neutral" style={{ fontFamily: 'var(--font-mono)' }}>
                            {evidenceId}
                          </span>
                        ))}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
                        该引用未能在本题证据中得到支撑
                      </div>
                    </div>
                  )}
                  {v.citation.missing.length > 0 && (
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
                        本题漏引
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {v.citation.missing.map((evidenceId) => (
                          <span key={evidenceId} className="badge badge-neutral" style={{ fontFamily: 'var(--font-mono)' }}>
                            {evidenceId}
                          </span>
                        ))}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
                        本题要求引用的证据
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* 复盘：结算时后端返回的 Markdown（刚结算时逐字输出，点击可跳过） */}
        <div className="card card-pad">
          <div className="card-title">复盘</div>
          {(report.markdown ?? '').trim() !== '' ? (
            <div
              style={{ marginTop: 10, cursor: mdDone ? undefined : 'pointer' }}
              onClick={mdDone ? undefined : skipMd}
              title={mdDone ? undefined : '点击立即显示全部'}
            >
              <Markdown content={freshSettle ? shownMd : markdownSource} />
              {!mdDone && <span className="type-cursor" aria-hidden />}
            </div>
          ) : (
            <>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 10 }}>
                本场暂无复盘文字
              </div>
              <div className="card-sub" style={{ marginTop: 16 }}>通用建议（非本场生成）</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 10 }}>
                {GENERIC_TIPS.map((tip, i) => (
                  <div key={i} style={{ display: 'flex', gap: 10, fontSize: 13, alignItems: 'flex-start' }}>
                    <span
                      style={{
                        width: 20,
                        height: 20,
                        flexShrink: 0,
                        borderRadius: '50%',
                        background: 'var(--primary-soft)',
                        color: 'var(--primary)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 11,
                        fontWeight: 700,
                      }}
                    >
                      {i + 1}
                    </span>
                    <span style={{ lineHeight: 1.7 }}>{tip}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
          说明：L0–L4 为单题评估等级；本页不合成总分。
          {isMockMode() ? '费用与置信度为演示数据。' : report.cost_known === false ? '金额单价尚未核定，费用按 0 展示。' : ''}
        </div>
      </div>
    </DashboardLayout>
  );
}

