/**
 * 训练历史 Mock（localStorage 持久化）
 */
import { mockDb, mockDelay } from './mockDb';
import type { Language, TrainingDirection } from '../types/training';

export interface HistoryItemSummary {
  item_id: string;
  title: string;
  rounds_done: number;
  target_rounds: number;
}

export interface HistoryRecord {
  session_id: string;
  created_at: string;
  direction: TrainingDirection;
  language: Language;
  status: 'in_progress' | 'finished';
  summaries: HistoryItemSummary[];
}

export interface HistoryListResult {
  items: HistoryRecord[];
  total: number;
}

const DIRECTION_LABELS: Record<TrainingDirection, string> = {
  random: '随机训练',
  logic_boundary: '逻辑与边界问题',
  api_usage: 'API 使用问题',
  security_performance: '安全与性能问题',
};

export const LANGUAGE_LABELS: Record<Language, string> = {
  python: 'Python',
  java: 'Java',
  c: 'C',
  cpp: 'C++',
};

export function directionLabel(d: TrainingDirection): string {
  return DIRECTION_LABELS[d] ?? d;
}

export function loadHistory(): HistoryRecord[] {
  return mockDb.read<HistoryRecord[]>(mockDb.keys.history, []);
}

/** 写入/更新一条历史记录 */
export function upsertHistory(record: HistoryRecord): void {
  const list = loadHistory();
  const idx = list.findIndex((r) => r.session_id === record.session_id);
  if (idx >= 0) list[idx] = record;
  else list.unshift(record);
  mockDb.write(mockDb.keys.history, list);
}

/** 查询历史（Mock 版，带搜索与状态筛选） */
export async function listMockHistory(opts: {
  search?: string;
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<HistoryListResult> {
  await mockDelay(350);
  let list = loadHistory();
  const search = (opts.search ?? '').trim().toLowerCase();
  if (search) {
    list = list.filter(
      (r) =>
        r.session_id.toLowerCase().includes(search) ||
        directionLabel(r.direction).includes(search) ||
        LANGUAGE_LABELS[r.language].toLowerCase().includes(search),
    );
  }
  if (opts.status && opts.status !== 'all') {
    list = list.filter((r) => r.status === opts.status);
  }
  const page = opts.page ?? 1;
  const size = opts.page_size ?? 10;
  const start = (page - 1) * size;
  return {
    total: list.length,
    items: list.slice(start, start + size),
  };
}