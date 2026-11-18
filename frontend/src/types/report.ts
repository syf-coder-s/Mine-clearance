/**
 * 训练报告相关类型（与真实后端 settle 响应对齐）
 * 注意：L0–L4 等级按项目正式定义展示，前端不自行合成总分。
 */

export type DefectLabel = 'defect_present' | 'no_defect';

/** 防御等级（L0–L4 短值；后端原始值为 L0_false_alarm ~ L4_repair） */
export type DefenseLevel = 'L0' | 'L1' | 'L2' | 'L3' | 'L4';

/** 后端等级原始值 → 前端短等级。拿不到前缀时保守落到 L2。 */
export function levelShort(raw: string): DefenseLevel {
  const m = /^L([0-4])/.exec(raw ?? '');
  return (m ? m[0] : 'L2') as DefenseLevel;
}

/** 引用核验（后端 CitationReport） */
export interface CitationMeta {
  precision: number;
  recall: number;
  supported: string[];
  unsupported: string[];
  missing: string[];
}

/** 证据原文引用（后端 EvidenceSpan；结算后才下发 quote） */
export interface CitationRef {
  evidence_id: string;
  doc_id: string;
  chunk_id: string;
  char_start: number;
  char_end: number;
  quote: string;
}

/** 单题结算裁定（POST /v1/sessions/{id}/settle 返回，等级已收敛为 L0–L4） */
export interface Verdict {
  item_id: string;
  label: DefectLabel;
  level: DefenseLevel;
  confidence: number;
  escalated: boolean;
  rationale: string;
  citation: CitationMeta;
  references: CitationRef[];
}

/** 结算报告（settle 响应；后端不另存报告，由前端本地缓存承接） */
export interface SettleReport {
  session_id: string;
  verdicts: Verdict[];
  calls: number;
  cost_cny: number;
  markdown: string;
  /** 真实后端附加字段 */
  latency_ms?: number;
  unverified_items?: number;
  cost_known?: boolean;
  report_fallback?: boolean;
  budget?: {
    cap: number;
    total: number;
    remaining: number;
    reserve: number;
    cost_cny?: number;
  };
  stage_calls?: Record<string, number>;
  rag_usage?: Record<string, unknown>;
  trace?: unknown[];
}