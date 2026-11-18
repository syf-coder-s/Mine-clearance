﻿﻿﻿import { DashboardLayout } from '../layouts/DashboardLayout';
import { PageHeader } from '../components/common/PageHeader';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { useHealth } from '../app/HealthProvider';
import { isMockMode } from '../services/apiClient';

const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  mock: { text: '模拟', cls: 'badge-warning' },
  ok: { text: '正常', cls: 'badge-success' },
  degraded: { text: '降级', cls: 'badge-warning' },
  down: { text: '不可用', cls: 'badge-danger' },
};

/** 系统状态页：真实状态来自全局健康检查（HealthProvider）；Mock 模式必须标注演示状态 */
export function SystemPage() {
  const { health, loading, error, refresh } = useHealth();
  const mock = isMockMode();

  const badge = mock
    ? { text: '演示状态（模拟数据）', cls: 'badge-warning' }
    : error
      ? { text: '后端不可达', cls: 'badge-danger' }
      : loading
        ? { text: '检查中', cls: 'badge-neutral' }
        : { text: '真实后端', cls: 'badge-success' };

  const cap = health?.stage_limits.cap ?? 0;
  const reserve = health?.stage_limits.reserve ?? 0;
  const adversarial = Math.max(0, cap - reserve);
  const advPct = cap > 0 ? (adversarial / cap) * 100 : 0;
  const resPct = cap > 0 ? (reserve / cap) * 100 : 0;

  return (
    <DashboardLayout>
      <div className="page">
        <PageHeader
          extra={
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                {health ? `最近检查：${new Date(health.checked_at).toLocaleString('zh-CN')}` : '正在检查…'}
              </span>
              <span className={`badge ${badge.cls}`}>{badge.text}</span>
              <button className="btn btn-outline btn-sm" onClick={refresh} disabled={loading}>
                {loading ? '刷新中…' : '刷新状态'}
              </button>
            </div>
          }
        />

        {error ? (
          <div className="card">
            <ErrorState
              title="无法获取服务状态"
              message={`${error}。请确认后端地址 VITE_API_BASE_URL 是否正确。`}
              onRetry={refresh}
            />
          </div>
        ) : !health ? (
          <div className="card">
            <LoadingState />
          </div>
        ) : (
          <>
            <div className="grid-2">
              {health.services.map((s) => {
                const st = STATUS_LABEL[s.status] ?? STATUS_LABEL.down;
                return (
                  <div key={s.name} className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span className="card-title">{s.name}</span>
                      <span className={`badge ${st.cls}`}>{st.text}</span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{s.detail}</div>
                  </div>
                );
              })}
            </div>

            <div className="grid-2">
              <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
                  <span className="card-title">预算规则</span>
                  <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>策略值，非实时余额</span>
                </div>
                <div style={{ display: 'flex', gap: 24, fontSize: 13 }}>
                  <span>上限 <strong>{cap}</strong> 次</span>
                  <span>对抗可用 ≤<strong>{adversarial}</strong> 次</span>
                  <span>结算预留 <strong>{reserve}</strong> 次</span>
                </div>
                <div style={{ display: 'flex', height: 6, borderRadius: 999, background: 'var(--bg-elev)', overflow: 'hidden' }}>
                  <div style={{ width: `${advPct}%`, height: '100%', background: 'var(--primary)' }} />
                  <div style={{ width: `${resPct}%`, height: '100%', background: 'var(--warning)' }} />
                </div>
                <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--text-tertiary)' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <span className="dot" style={{ background: 'var(--primary)' }} /> 对抗可用
                  </span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <span className="dot" style={{ background: 'var(--warning)' }} /> 结算预留
                  </span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  隔离保护（vendor_isolated）：{health.vendor_isolated ? '已启用' : '未启用'}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                  实时余量以训练页顶部进度为准；本页不保存会话状态。
                </div>
              </div>

              <div className="card card-pad" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div className="card-title">近期事件</div>
                {health.recent_events.map((ev, i) => (
                  <div key={i} style={{ display: 'flex', gap: 10, fontSize: 12 }}>
                    <span style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>{ev.time}</span>
                    <span style={{ color: 'var(--text-main)' }}>{ev.text}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
              Mock 模式下所有状态均为模拟数据；接入真实后端后，本页状态来自 GET /v1/health。
            </div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}

