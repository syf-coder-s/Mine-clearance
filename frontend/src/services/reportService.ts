/**
 * 报告服务
 * 真实后端只在 settle 响应里给一次报告，没有单独的 GET /report 端点，
 * 所以 live 模式由前端在结算后把报告缓存到本地（localStorage）承接刷新页面。
 */
import { isMockMode } from './apiClient';
import { getMockReport } from '../mocks/trainingMock';
import { mockDb } from '../mocks/mockDb';
import { levelShort } from '../types/report';
import type { CitationRef, SettleReport, Verdict } from '../types/report';

interface RawVerdict {
  item_id: string;
  label: 'defect_present' | 'no_defect';
  level: string;
  confidence: number;
  escalated: boolean;
  rationale: string;
  citation?: {
    precision?: number;
    recall?: number;
    supported?: string[];
    unsupported?: string[];
    missing?: string[];
  };
  references?: Array<Partial<CitationRef>>;
}

/** 真实后端 settle 响应的原始形状（字段按需声明，其余透传） */
export interface RawReport {
  session_id: string;
  verdicts?: RawVerdict[];
  calls?: number;
  cost_cny?: number;
  markdown?: string;
  latency_ms?: number;
  unverified_items?: number;
  cost_known?: boolean;
  report_fallback?: boolean;
  budget?: SettleReport['budget'];
  stage_calls?: Record<string, number>;
  rag_usage?: Record<string, unknown>;
  trace?: unknown[];
}

/** 把真实后端 settle 响应归一成前端 SettleReport（等级收敛 L0–L4、引用展开） */
export function normalizeReport(raw: RawReport): SettleReport {
  const verdicts: Verdict[] = (raw.verdicts ?? []).map((v) => ({
    item_id: v.item_id,
    label: v.label,
    level: levelShort(v.level),
    confidence: v.confidence ?? 0,
    escalated: !!v.escalated,
    rationale: v.rationale ?? '',
    citation: {
      precision: v.citation?.precision ?? 0,
      recall: v.citation?.recall ?? 0,
      supported: v.citation?.supported ?? [],
      unsupported: v.citation?.unsupported ?? [],
      missing: v.citation?.missing ?? [],
    },
    references: (v.references ?? []).map((r) => ({
      evidence_id: r.evidence_id ?? '',
      doc_id: r.doc_id ?? '',
      chunk_id: r.chunk_id ?? '',
      char_start: r.char_start ?? 0,
      char_end: r.char_end ?? 0,
      quote: r.quote ?? '',
    })),
  }));
  return {
    session_id: raw.session_id,
    verdicts,
    calls: raw.calls ?? 0,
    cost_cny: raw.cost_cny ?? 0,
    markdown: raw.markdown ?? '',
    latency_ms: raw.latency_ms,
    unverified_items: raw.unverified_items,
    cost_known: raw.cost_known,
    report_fallback: raw.report_fallback,
    budget: raw.budget,
    stage_calls: raw.stage_calls,
    rag_usage: raw.rag_usage,
    trace: raw.trace,
  };
}

/** live 模式：结算后把报告写入本地缓存 */
export function cacheLiveReport(sessionId: string, report: SettleReport): void {
  const reports = mockDb.read<Record<string, SettleReport>>(mockDb.keys.reports, {});
  reports[sessionId] = report;
  mockDb.write(mockDb.keys.reports, reports);
}

/** 获取训练报告：mock 读本地库；live 读 settle 时缓存的报告 */
export function getReport(sessionId: string): Promise<SettleReport> {
  if (isMockMode()) return getMockReport(sessionId);
  const reports = mockDb.read<Record<string, SettleReport>>(mockDb.keys.reports, {});
  const report = reports[sessionId];
  if (!report) {
    return Promise.reject({
      status: 404,
      body: { code: 'REPORT_NOT_FOUND', message: '本机没有这场训练的报告记录（后端不在 settle 之外单独保存报告）' },
    });
  }
  return Promise.resolve(report);
}