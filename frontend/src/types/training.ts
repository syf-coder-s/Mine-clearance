/**
 * 训练相关类型
 * 形状与真实后端契约保持一致（见 frontend-api-doc/frontend-api-doc.html），
 * 后端接入时无需改动页面层。
 */

export type Language = 'python' | 'java' | 'c' | 'cpp';

export type TrainingDirection =
  | 'random'
  | 'logic_boundary'
  | 'api_usage'
  | 'security_performance';

/** 训练会话状态 */
export type SessionStatus = 'in_progress' | 'finished';

/** 证据条目（仅展示后端授权字段） */
export interface EvidenceItem {
  evidence_id: string;
  /** 引用片段：仅 visible_in_code=true 时后端才下发非空值 */
  excerpt: string;
  visible_in_code: boolean;
  /** 埋雷版代码中的行号范围（1-based、闭区间）；映射失败时为 0 */
  line_start?: number;
  line_end?: number;
}

/** 训练题目 */
export interface TrainingItem {
  item_id: string;
  language: string;
  title: string;
  code: string;
  rounds_done: number;
  target_rounds: number;
  evidence: EvidenceItem[];
}

/** 调用预算 */
export interface BudgetInfo {
  cap: number;      // 上限（12）
  total: number;
  remaining: number;
  reserve: number;  // 结算预留（3）
  /** 真实后端附加：累计费用与离线建库调用数，Mock 无 */
  cost_cny?: number;
  offline_calls?: number;
}

/** 训练会话（POST /v1/sessions 返回） */
export interface TrainingSession {
  session_id: string;
  schema_version: string;
  unverified_items: number;
  budget: BudgetInfo;
  items: TrainingItem[];
  /** 前端会话附加信息（本地持久化用；真实后端不返回这些字段） */
  language?: Language;
  direction?: TrainingDirection;
  status?: SessionStatus;
  /** 真实后端状态接口才有；结算后为 true */
  settled?: boolean;
}

/** 提交审查意见请求体（POST /v1/sessions/{id}/submit） */
export interface SubmitRequest {
  item_id: string;
  text: string;
  cited_evidence_ids: string[];
  proposed_fix: string;
}

export type SubmitReason = 'ok' | 'target_reached' | 'budget_guard';

/** 提交审查意见响应 */
export interface SubmitResponse {
  item_id: string;
  accepted: boolean;
  reason: SubmitReason;
  /** 本题已完成/预算不足时后端不带 round */
  round?: number;
  challenge: string;
  rounds_done: number;
  target_rounds: number;
  finished: boolean;
  budget: BudgetInfo;
}