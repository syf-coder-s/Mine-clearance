/**
 * 训练历史服务
 * 真实后端未开放会话列表接口（只有按 ID 读进度），
 * 所以 live 模式同样读本机维护的历史记录（localStorage）。
 */
import { listMockHistory, type HistoryListResult } from '../mocks/historyMock';
import type { PageQuery } from '../types/api';

export function listHistory(query: PageQuery): Promise<HistoryListResult> {
  // mock 与 live 共用的本地记录实现（后端没有 GET /v1/sessions 列表端点）
  return listMockHistory({
    search: query.search,
    status: query.status,
    page: query.page,
    page_size: query.page_size,
  });
}