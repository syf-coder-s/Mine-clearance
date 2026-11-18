/**
 * 系统状态服务
 */
import { isMockMode, apiClient } from './apiClient';
import { getMockHealth } from '../mocks/systemMock';
import type { SystemHealth } from '../mocks/systemMock';

interface LiveUpstream {
  mode?: string;
  base_url?: string;
  cap?: number;
  cost_budget_cny?: number;
  sessions?: number;
}

interface LiveHealth {
  status?: string;
  schema_version?: string;
  llm_provider?: string;
  mock_llm?: boolean;
  model_routes?: Record<string, unknown>;
  cost_known?: boolean;
  cost_note?: string;
  vendor_isolated?: boolean;
  calls_per_session_cap?: number;
  cost_budget_cny?: number;
  stage_limits?: Record<string, number>;
  probe?: string;
  rag?: { backend?: string } | string;
  upstream?: LiveUpstream | string;
  sessions?: number;
}

/** 健康检查（GET /v1/health），把后端字段适配成页面需要的 SystemHealth 形状 */
export async function getHealth(): Promise<SystemHealth> {
  if (isMockMode()) return getMockHealth();
  const raw = await apiClient.get<LiveHealth>('/v1/health');

  const cap = raw.calls_per_session_cap ?? 12;
  const reserve = ['judge_decision', 'judge_escalation', 'report'].reduce(
    (s, k) => s + (raw.stage_limits?.[k] ?? 0),
    0,
  );
  const release =
    typeof raw.rag === 'string'
      ? raw.rag
      : (raw.rag && raw.rag.backend) || 'unknown';
  const ragStub = /stub|contract/i.test(release);
  const upstreamFake =
    typeof raw.upstream === 'string'
      ? /fake/i.test(raw.upstream)
      : (raw.upstream?.mode ?? '') === 'fake';
  const upstreamLabel =
    typeof raw.upstream === 'string' ? raw.upstream : (raw.upstream?.mode ?? '-') + (raw.upstream?.base_url ? ` @ ${raw.upstream.base_url}` : '');

  return {
    mode: 'live',
    checked_at: new Date().toISOString(),
    schema_version: raw.schema_version ?? '-',
    services: [
      {
        name: 'API 服务',
        status: raw.status === 'ok' ? 'ok' : 'down',
        detail: `schema v${raw.schema_version ?? '-'} · ${raw.sessions ?? 0} 场会话`,
      },
      {
        name: '模型服务',
        status: raw.mock_llm ? 'degraded' : 'ok',
        detail: `${raw.llm_provider ?? '-'}${raw.mock_llm ? '（Mock 回退）' : ''} · 对抗/裁判隔离${raw.vendor_isolated ? '已启用' : '未启用'}`,
      },
      {
        name: '检索服务',
        status: ragStub ? 'degraded' : 'ok',
        detail: ragStub ? `本地桩 ${release}（未接真实判例库）` : `已对接 ${release}`,
      },
      {
        name: '裁决层',
        status: upstreamFake ? 'degraded' : 'ok',
        detail: `${upstreamLabel}${upstreamFake ? '（内存实现，未接后端裁决方）' : ''} · 探针 ${raw.probe ?? '-'}`,
      },
    ],
    vendor_isolated: !!raw.vendor_isolated,
    mock_llm: !!raw.mock_llm,
    stage_limits: { cap, reserve },
    recent_events: [
      {
        time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        text: raw.cost_known
          ? `价格已核定，单场上限 ¥${raw.cost_budget_cny ?? '-'}`
          : '金额单价未核定：cost_cny=0 表示未估价，调用次数上限仍有效',
      },
    ],
  };
}