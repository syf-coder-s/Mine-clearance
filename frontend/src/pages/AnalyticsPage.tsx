import { useEffect, useState } from 'react';
import { DashboardLayout } from '../layouts/DashboardLayout';
import { LoadingState } from '../components/ui/LoadingState';
import { EmptyState } from '../components/ui/EmptyState';
import { mockDb } from '../mocks/mockDb';
import { loadHistory, directionLabel, type HistoryRecord } from '../mocks/historyMock';
import type { SettleReport, DefenseLevel } from '../types/report';

const LEVELS: DefenseLevel[] = ['L0', 'L1', 'L2', 'L3', 'L4'];
const LEVEL_COLOR: Record<DefenseLevel, string> = {
  L0: 'var(--danger)',
  L1: 'var(--warning)',
  L2: 'var(--primary)',
  L3: 'var(--success)',
  L4: 'var(--success-strong)',
};

interface Agg {
  levelCount: Record<DefenseLevel, number>;
  byDirection: Record<string, Record<DefenseLevel, number>>;
  trend: { label: string; l3Plus: number; total: number; verdictCount: number }[];
}

function aggregate(): Agg {
  const history = loadHistory().filter((h) => h.status === 'finished');
  const reports = mockDb.read<Record<string, SettleReport>>(mockDb.keys.reports, {});
  const levelCount: Record<DefenseLevel, number> = { L0: 0, L1: 0, L2: 0, L3: 0, L4: 0 };
  const byDirection: Record<string, Record<DefenseLevel, number>> = {};
  const trend: Agg['trend'] = [];

  history
    .slice()
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
    .forEach((h: HistoryRecord) => {
      const r = reports[h.session_id];
      if (!r) return;
      const dirKey = directionLabel(h.direction);
      if (!byDirection[dirKey]) byDirection[dirKey] = { L0: 0, L1: 0, L2: 0, L3: 0, L4: 0 };
      let l3Plus = 0;
      r.verdicts.forEach((v) => {
        levelCount[v.level] += 1;
        byDirection[dirKey][v.level] += 1;
        if (v.level === 'L3' || v.level === 'L4') l3Plus += 1;
      });
      const d = new Date(h.created_at);
      trend.push({
        label: `${d.getMonth() + 1}/${d.getDate()}`,
        l3Plus,
        total: r.verdicts.length,
        verdictCount: r.verdicts.length,
      });
    });

  return { levelCount, byDirection, trend };
}

/** 能力分析页：L0–L4 分布 / 方向表现 / 趋势；指标口径明确标注，数据为演示数据 */
export function AnalyticsPage() {
  const [agg, setAgg] = useState<Agg | null>(null);

  useEffect(() => {
    setAgg(aggregate());
  }, []);

  if (!agg) {
    return (
      <DashboardLayout>
        <LoadingState />
      </DashboardLayout>
    );
  }

  const totalVerdicts = LEVELS.reduce((s, l) => s + agg.levelCount[l], 0);
  const maxLevelCount = Math.max(1, ...LEVELS.map((l) => agg.levelCount[l]));
  const directions = Object.keys(agg.byDirection);
  const maxDirTotal = Math.max(1, ...directions.map((d) => LEVELS.reduce((s, l) => s + agg.byDirection[d][l], 0)));

  // 趋势折线坐标（SVG）
  const W = 560;
  const H = 180;
  const PAD = 24;
  const trend = agg.trend;
  const pts =
    trend.length > 0
      ? trend.map((t, i) => {
          const x = trend.length === 1 ? W / 2 : PAD + (i * (W - PAD * 2)) / (trend.length - 1);
          const y = PAD + ((3 - Math.min(t.l3Plus, 3)) / 3) * (H - PAD * 2);
          return { x, y, ...t };
        })
      : [];

  return (
    <DashboardLayout>
      <div className="page">
        <div
          className="card card-pad"
          style={{ background: 'var(--warning-soft)', borderColor: 'var(--warning-line)', fontSize: 12, color: 'var(--warning)', lineHeight: 1.75 }}
        >
          口径说明：数据来自本机浏览器记录（历史/报告同源，非后端统计）；分布按「每题 L0–L4 结算等级」计数，趋势图按「单场 L3 及以上题目数」展示；本页不计算任何合成总分。
        </div>

        {/* L0-L4 分布 */}
        <div className="card card-pad">
          <div className="card-title">等级分布（按题目结算等级）</div>
          <div className="card-sub" style={{ marginTop: 4 }}>
            共 {totalVerdicts} 道已结算题目
          </div>
          {totalVerdicts === 0 ? (
            <EmptyState title="暂无结算数据" desc="完成一场训练并结算后，这里会展示等级分布。" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
              {LEVELS.map((l) => {
                const count = agg.levelCount[l];
                return (
                  <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ width: 28, fontSize: 13, fontWeight: 700, color: LEVEL_COLOR[l] }}>{l}</span>
                    <div style={{ flex: 1, height: 16, background: 'var(--bg-elev)', borderRadius: 6, overflow: 'hidden' }}>
                      <div
                        style={{
                          width: `${(count / maxLevelCount) * 100}%`,
                          height: '100%',
                          background: LEVEL_COLOR[l],
                          borderRadius: 6,
                          transition: 'width .4s',
                          minWidth: count > 0 ? 10 : 0,
                        }}
                      />
                    </div>
                    <span style={{ width: 70, fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>
                      {count} 题（{totalVerdicts > 0 ? Math.round((count / totalVerdicts) * 100) : 0}%）
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 方向表现 */}
        <div className="card card-pad">
          <div className="card-title">方向表现（各等级题目数堆叠）</div>
          {directions.length === 0 ? (
            <EmptyState title="暂无方向数据" desc="完成训练后可按训练方向查看分布。" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 14 }}>
              {directions.map((d) => {
                const dist = agg.byDirection[d];
                const total = LEVELS.reduce((s, l) => s + dist[l], 0);
                return (
                  <div key={d}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 5 }}>
                      <span style={{ fontWeight: 600 }}>{d}</span>
                      <span style={{ color: 'var(--text-secondary)' }}>{total} 道题目</span>
                    </div>
                    <div
                      style={{
                        height: 14,
                        background: 'var(--bg)',
                        borderRadius: 7,
                        overflow: 'hidden',
                        display: 'flex',
                        width: `${(total / maxDirTotal) * 100}%`,
                      }}
                    >
                      {LEVELS.map((l) =>
                        dist[l] > 0 ? (
                          <div
                            key={l}
                            style={{
                              width: `${(dist[l] / total) * 100}%`,
                              background: LEVEL_COLOR[l],
                            }}
                          />
                        ) : null,
                      )}
                    </div>
                  </div>
                );
              })}
              <div style={{ display: 'flex', gap: 12, marginTop: 6 }}>
                {LEVELS.map((l) => (
                  <span key={l} style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: LEVEL_COLOR[l] }} />
                    {l}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 趋势 */}
        <div className="card card-pad">
          <div className="card-title">趋势（单场 L3 及以上题目数，满分 3）</div>
          {trend.length === 0 ? (
            <EmptyState title="暂无趋势数据" desc="完成更多场训练后可见能力变化趋势。" />
          ) : (
            <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ marginTop: 8 }}>
              {[0, 1, 2, 3].map((g) => (
                <line
                  key={g}
                  x1={PAD}
                  x2={W - PAD}
                  y1={PAD + (g / 3) * (H - PAD * 2)}
                  y2={PAD + (g / 3) * (H - PAD * 2)}
                  stroke="var(--border)"
                  strokeDasharray="3 4"
                />
              ))}
              {pts.length > 1 && (
                <polyline
                  points={pts.map((p) => `${p.x},${p.y}`).join(' ')}
                  fill="none"
                  stroke="var(--primary)"
                  strokeWidth="2"
                />
              )}
              {pts.map((p, i) => (
                <g key={i}>
                  <circle cx={p.x} cy={p.y} r="4" fill="var(--primary)" />
                  <text x={p.x} y={H - 6} textAnchor="middle" fontSize="10" fill="var(--text-secondary)">
                    {p.label}
                  </text>
                  <text x={p.x} y={p.y - 10} textAnchor="middle" fontSize="10" fill="var(--text-main)" fontWeight="600">
                    {p.l3Plus}
                  </text>
                </g>
              ))}
            </svg>
          )}
        </div>

        <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
          本机数据 · 由前端在浏览器本地聚合，不跨设备、非后端统计；切换设备或清缓存后不保留。后端提供真实统计接口后再由 Service 层替换。
        </div>
      </div>
    </DashboardLayout>
  );
}

