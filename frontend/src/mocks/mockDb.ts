/**
 * Mock 数据本地持久化工具
 * 演示与真实两种数据模式共用本工具，本地数据按数据模式隔离存储：
 *   mc.mock.* —— 演示模式数据
 *   mc.live.* —— 真实后端模式下的本机数据
 * 切换模式不会串数据；旧版 key（mc.sessions.v1 等）不再读取，也不自动迁移或删除。
 */
import { DATA_MODE } from '../services/apiClient';

const DB_KEYS = {
  sessions: `mc.${DATA_MODE}.sessions.v1`,
  reports: `mc.${DATA_MODE}.reports.v1`,
  history: `mc.${DATA_MODE}.history.v1`,
} as const;

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function write<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* 存储失败不影响演示主流程 */
  }
}

export const mockDb = {
  keys: DB_KEYS,
  read,
  write,
};

/** 模拟网络延迟，让加载状态可见 */
export function mockDelay(ms = 400): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 生成演示用 ID */
export function genId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}