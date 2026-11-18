/**
 * 系统状态 Mock（演示数据，必须标注“演示状态”）
 */
import { mockDelay } from './mockDb';

export interface HealthComponent {
  name: string;
  status: 'mock' | 'ok' | 'degraded' | 'down';
  detail: string;
}

export interface SystemHealth {
  mode: 'mock' | 'live';
  checked_at: string;
  schema_version: string;
  services: HealthComponent[];
  vendor_isolated: boolean;
  /** 后端是否在用内置演示模型（live 模式下为 true 说明模型密钥未接入） */
  mock_llm?: boolean;
  stage_limits: { cap: number; reserve: number };
  recent_events: { time: string; text: string }[];
}

/** Mock 版 GET /v1/health */
export async function getMockHealth(): Promise<SystemHealth> {
  await mockDelay(450);
  return {
    mode: 'mock',
    checked_at: new Date().toISOString(),
    schema_version: 'demo',
    services: [
      { name: 'API 服务', status: 'mock', detail: '演示模式：未连接真实后端' },
      { name: '检索服务', status: 'mock', detail: '演示模式：证据来自内置数据' },
      { name: '模型服务', status: 'mock', detail: '演示模式：AI 回复为内置剧本' },
      { name: '训练会话服务', status: 'mock', detail: '演示模式：会话保存在本地存储' },
    ],
    vendor_isolated: true,
    mock_llm: true,
    stage_limits: { cap: 12, reserve: 3 },
    recent_events: [
      { time: '10:24:11', text: '演示会话 sess-demo-01 创建（3 题 / 12 次预算）' },
      { time: '10:25:40', text: '演示会话 sess-demo-01 完成结算，消耗 9 次调用' },
      { time: '10:31:02', text: '演示会话 sess-demo-02 创建' },
    ],
  };
}