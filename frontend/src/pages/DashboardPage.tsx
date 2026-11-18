import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DashboardLayout } from '../layouts/DashboardLayout';
import { StatCard } from '../components/ui/StatCard';
import { EmptyState } from '../components/ui/EmptyState';
import { LoadingState } from '../components/ui/LoadingState';
import { SessionStatusBadge } from '../components/ui/StatusBadge';
import { IconPlus } from '../components/icons';
import { listHistory } from '../services/historyService';
import { isMockMode } from '../services/apiClient';
import { useHealth } from '../app/HealthProvider';
import { directionLabel, LANGUAGE_LABELS } from '../mocks/historyMock';
import type { HistoryRecord } from '../mocks/historyMock';
import { trackSpotlight } from '../utils/spotlight';

/** 首页 / 工作台：概览 + 开始训练 + 最近训练 */
export function DashboardPage() {
  const navigate = useNavigate();
  const mock = isMockMode();
  const { health, loading, error } = useHealth();
  const [history, setHistory] = useState<HistoryRecord[] | null>(null);

  const serviceStatus: {
    value: string;
    sub: string;
    tone: 'default' | 'success' | 'warning' | 'danger';
  } = mock
    ? { value: '演示模式', sub: '未连接真实后端', tone: 'warning' }
    : error
      ? { value: '不可达', sub: '请检查后端服务', tone: 'danger' }
      : loading || !health
        ? { value: '检查中', sub: '正在请求 /v1/health', tone: 'default' }
        : { value: '在线', sub: `schema v${health.schema_version}`, tone: 'success' };

  const SERVICE_BADGE: Record<string, string> = {
    default: 'badge-neutral',
    success: 'badge-success',
    warning: 'badge-warning',
    danger: 'badge-danger',
  };

  useEffect(() => {
    let alive = true;
    listHistory({ page: 1, page_size: 6 }).then(
      (res) => alive && setHistory(res.items),
      () => alive && setHistory([]),
    );
    return () => {
      alive = false;
    };
  }, []);

  const finishedCount = history?.filter((h) => h.status === 'finished').length ?? 0;
  const inProgress = history?.filter((h) => h.status === 'in_progress') ?? [];
  const reviewedItems =
    history?.reduce((sum, h) => sum + h.summaries.filter((s) => s.rounds_done > 0).length, 0) ?? 0;

  const fmtTime = (iso: string) => {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  return (
    <DashboardLayout>
      <div className="page">
        {/* 继续训练横幅 */}
        <div
          className="card card-spotlight"
          onMouseMove={trackSpotlight}
          style={{
            position: 'relative',
            overflow: 'hidden',
            padding: '20px 24px',
            display: 'flex',
            alignItems: 'center',
            gap: 20,
            background:
              'linear-gradient(112deg, #FFFFFF 0%, #F7F9FF 46%, #EEF2FE 100%)',
            borderColor: 'var(--primary-line)',
          }}
        >
          <div
            aria-hidden
            style={{
              position: 'absolute',
              right: -60,
              top: -80,
              width: 320,
              height: 260,
              background: 'radial-gradient(closest-side, rgba(49,87,221,.10), transparent 70%)',
              pointerEvents: 'none',
            }}
          />
          <div style={{ position: 'relative', minWidth: 0 }}>
            <div className="micro">SESSION · {inProgress.length > 0 ? '续练' : '新开'}</div>
            <h1 style={{ fontSize: 20, marginTop: 8, letterSpacing: '-0.02em' }}>
              {inProgress.length > 0 ? '继续上一场对抗训练' : '开始一场对抗训练'}
            </h1>
            <p style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginTop: 6 }}>
              {inProgress.length > 0 ? (
                <>
                  进行中：<span className="mono" style={{ color: 'var(--text-main)' }}>{inProgress[0].session_id}</span>
                  {' '}· 已完成 {inProgress[0].summaries.reduce((s, x) => s + x.rounds_done, 0)} 轮
                </>
              ) : (
                <>还没有进行中的训练，开始一场吧。</>
              )}
            </p>
          </div>

          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, position: 'relative' }}>
            {inProgress.length > 0 && (
              <button className="btn btn-outline" onClick={() => navigate(`/training/${inProgress[0].session_id}`)}>
                继续训练
              </button>
            )}
            <button className="btn btn-primary btn-lg" onClick={() => navigate('/training/setup')}>
              <IconPlus size={15} />
              开始新训练
            </button>
          </div>
        </div>

        {/* 概览 */}
        <div className="grid-4">
          <StatCard label="已完成训练" value={finishedCount} sub={mock ? '演示记录' : '本机记录'} demo={mock} />
          <StatCard label="已审查题目" value={reviewedItems} sub="累计已提交轮次" demo={mock} />
          <StatCard label="进行中训练" value={inProgress.length} sub="可随时续练" />
          <div
            className="card card-spotlight"
            onMouseMove={trackSpotlight}
            style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 6 }}
          >
            <div className="micro">服务状态</div>
            <div style={{ display: 'flex', alignItems: 'center', marginTop: 4, minHeight: 28 }}>
              <span className={`badge ${SERVICE_BADGE[serviceStatus.tone]}`} style={{ height: 20, fontSize: 11 }}>
                {serviceStatus.value}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, minHeight: 16 }}>
              <span style={{ fontSize: 11.5, color: 'var(--text-tertiary)' }}>{serviceStatus.sub}</span>
            </div>
          </div>
        </div>

        {/* 最近训练 + 规则 */}
        <div className="dash-grid">
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">最近训练</div>
                <div className="card-sub" style={{ marginTop: 2 }}>最近 6 场 · 本机记录</div>
              </div>
              <div className="right">
                <button className="btn btn-outline btn-sm" onClick={() => navigate('/history')}>
                  查看全部
                </button>
              </div>
            </div>

            {history === null ? (
              <LoadingState />
            ) : history.length === 0 ? (
              <EmptyState
                title="还没有训练记录"
                desc="点击「开始新训练」，完成第一场审查对抗后，记录会显示在这里。"
                action={
                  <button className="btn btn-primary btn-sm" onClick={() => navigate('/training/setup')}>
                    开始新训练
                  </button>
                }
              />
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>训练 ID</th>
                      <th>时间</th>
                      <th>方向</th>
                      <th>语言</th>
                      <th>状态</th>
                      <th style={{ textAlign: 'right' }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((h) => (
                      <tr key={h.session_id}>
                        <td className="mono">{h.session_id}</td>
                        <td style={{ color: 'var(--text-secondary)' }}>{fmtTime(h.created_at)}</td>
                        <td>{directionLabel(h.direction)}</td>
                        <td>{LANGUAGE_LABELS[h.language]}</td>
                        <td>
                          <SessionStatusBadge status={h.status} />
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          {h.status === 'in_progress' ? (
                            <button
                              className="btn btn-outline btn-sm"
                              onClick={() => navigate(`/training/${h.session_id}`)}
                            >
                              继续
                            </button>
                          ) : (
                            <button
                              className="btn btn-ghost btn-sm"
                              style={{ color: 'var(--primary)' }}
                              onClick={() => navigate(`/report/${h.session_id}`)}
                            >
                              报告
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="card card-spotlight" onMouseMove={trackSpotlight} style={{ padding: 20 }}>
            <div className="micro">PROTOCOL</div>
            <div className="card-title" style={{ marginTop: 6 }}>本场训练规则</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 16 }}>
              {[
                ['题量', '3 题', '固定题量，逐题结算'],
                ['对抗轮次', '最多 3 轮', '每题独立计轮'],
                ['调用预算', '12 次', '含 2 次结算预留'],
              ].map(([k, v, d], i) => (
                <div key={k} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                  <div
                    style={{
                      width: 22,
                      height: 22,
                      borderRadius: '50%',
                      flexShrink: 0,
                      display: 'grid',
                      placeItems: 'center',
                      background: 'var(--primary-soft)',
                      color: 'var(--primary)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      fontWeight: 600,
                    }}
                  >
                    {i + 1}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                      <span className="micro">{k}</span>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{v}</span>
                    </div>
                    <div style={{ fontSize: 11.5, color: 'var(--text-tertiary)', marginTop: 2 }}>{d}</div>
                  </div>
                </div>
              ))}
            </div>

            <hr className="divider" style={{ margin: '16px 0' }} />

            <div className="hint">
              结算后生成 L0–L4 等级报告：定位准确度、修复证据、对抗表现都会被计入。
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
