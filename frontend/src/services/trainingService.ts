/**
 * 训练服务：页面只依赖这里的接口，不感知 Mock / 真实后端。
 *
 * live 模式与真实后端的衔接口径：
 *  - 开局 POST /v1/sessions（后端用内置出题单，language/direction 仅前端记录展示）
 *  - GET /v1/sessions/{id} 只回进度不进题目，题目以开局响应为准 → 本地缓存承接
 *  - settle 一次性返回报告，后端不另存 → 本地缓存承接（见 reportService）
 */
import { isMockMode, apiClient } from './apiClient';
import {
  createMockSession,
  getMockSession,
  submitMockReview,
  settleMockSession,
} from '../mocks/trainingMock';
import { mockDb } from '../mocks/mockDb';
import { upsertHistory } from '../mocks/historyMock';
import { cacheLiveReport, normalizeReport } from './reportService';
import type { RawReport } from './reportService';
import type {
  BudgetInfo,
  Language,
  SubmitRequest,
  SubmitResponse,
  TrainingDirection,
  TrainingItem,
  TrainingSession,
} from '../types/training';
import type { SettleReport } from '../types/report';

/* ---------- live 模式的本地会话缓存 ---------- */

interface RawSession {
  session_id: string;
  schema_version?: string;
  unverified_items?: number;
  budget?: BudgetInfo;
  items?: TrainingItem[];
}

interface RawState {
  settled?: boolean;
  unverified_items?: number;
  budget?: BudgetInfo;
  items?: Array<{ item_id: string; rounds_done?: number; target_rounds?: number; finished?: boolean }>;
}

function loadSessions(): TrainingSession[] {
  return mockDb.read<TrainingSession[]>(mockDb.keys.sessions, []);
}

function saveSessions(list: TrainingSession[]): void {
  mockDb.write(mockDb.keys.sessions, list);
}

function adaptSession(raw: RawSession, language: Language, direction: TrainingDirection): TrainingSession {
  return {
    session_id: raw.session_id,
    schema_version: raw.schema_version ?? '',
    unverified_items: raw.unverified_items ?? 0,
    budget: raw.budget ?? { cap: 12, total: 0, remaining: 12, reserve: 3 },
    items: raw.items ?? [],
    language,
    direction,
    status: 'in_progress',
    settled: false,
  };
}

function writeHistory(session: TrainingSession, status: 'in_progress' | 'finished'): void {
  upsertHistory({
    session_id: session.session_id,
    created_at: new Date().toISOString(),
    direction: session.direction ?? 'random',
    language: session.language ?? 'python',
    status,
    summaries: session.items.map((it) => ({
      item_id: it.item_id,
      title: it.title,
      rounds_done: it.rounds_done,
      target_rounds: it.target_rounds,
    })),
  });
}

/* ---------- 对外接口 ---------- */

/** 创建训练会话（POST /v1/sessions）。live 模式语言/方向仅作本地展示记录。 */
export function createSession(
  language: Language,
  direction: TrainingDirection,
): Promise<TrainingSession> {
  if (isMockMode()) return createMockSession(language, direction);
  return apiClient.post<RawSession>('/v1/sessions', {}).then((raw) => {
    const session = adaptSession(raw, language, direction);
    const all = loadSessions();
    all.unshift(session);
    saveSessions(all);
    writeHistory(session, 'in_progress');
    return session;
  });
}

/** 获取训练会话（GET /v1/sessions/{id}）。live 模式以本地缓存的题目为准，用状态接口同步进度。 */
export async function getSession(sessionId: string): Promise<TrainingSession> {
  if (isMockMode()) return getMockSession(sessionId);
  const cached = loadSessions().find((s) => s.session_id === sessionId);
  if (!cached) {
    throw {
      status: 404,
      body: {
        code: 'SESSION_NOT_FOUND',
        message: '本机没有这场会话的记录：后端只按 ID 回进度、不回题目，请从「开始训练」创建会话（或沿用创建时的浏览器）',
      },
    };
  }
  // 用后端状态接口同步预算/轮次/结算状态；后端不可达时退化为本地记录
  try {
    const st = await apiClient.get<RawState>(`/v1/sessions/${sessionId}`);
    cached.budget = st.budget ?? cached.budget;
    cached.unverified_items = st.unverified_items ?? cached.unverified_items;
    cached.settled = !!st.settled;
    cached.status = st.settled ? 'finished' : 'in_progress';
    for (const it of cached.items) {
      const p = st.items?.find((x) => x.item_id === it.item_id);
      if (p) {
        it.rounds_done = p.rounds_done ?? it.rounds_done;
        it.target_rounds = p.target_rounds ?? it.target_rounds;
      }
    }
    saveSessions(loadSessions());
    writeHistory(cached, cached.status);
  } catch {
    /* 进度同步失败不阻断训练 */
  }
  return cached;
}

/** 提交审查意见（POST /v1/sessions/{id}/submit），请求体与后端 AnswerIn 完全一致 */
export function submitReview(sessionId: string, req: SubmitRequest): Promise<SubmitResponse> {
  if (isMockMode()) return submitMockReview(sessionId, req);
  return apiClient.post<SubmitResponse>(`/v1/sessions/${sessionId}/submit`, req);
}

/** 结算训练（POST /v1/sessions/{id}/settle），报告缓存到本地供报告页读取 */
export async function settleSession(sessionId: string): Promise<SettleReport> {
  if (isMockMode()) return settleMockSession(sessionId);
  const raw = await apiClient.post<RawReport>(`/v1/sessions/${sessionId}/settle`);
  const report = normalizeReport(raw);
  cacheLiveReport(sessionId, report);

  const all = loadSessions();
  const session = all.find((s) => s.session_id === sessionId);
  if (session) {
    // 结算后仍可读状态接口，用它同步每题的最终轮次，历史摘要与后端一致
    try {
      const st = await apiClient.get<RawState>(`/v1/sessions/${sessionId}`);
      for (const it of session.items) {
        const p = st.items?.find((x) => x.item_id === it.item_id);
        if (p) it.rounds_done = p.rounds_done ?? it.rounds_done;
      }
      session.budget = st.budget ?? session.budget;
    } catch {
      /* 同步不到就保留本地记录 */
    }
    session.status = 'finished';
    session.settled = true;
    saveSessions(all);
    writeHistory(session, 'finished');
  }
  return report;
}