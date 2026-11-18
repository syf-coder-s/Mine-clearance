/**
 * 训练报告 Mock
 * 仅在这里将题目缺陷信息“解密”到结算报告中；
 * 训练阶段（结算前）任何页面都不得引用本文件的缺陷描述。
 */
import type { CitationRef, SettleReport, Verdict } from '../types/report';
import type { TrainingSession } from '../types/training';
import { MOCK_PROBLEMS } from './trainingMock';

/** 根据会话生成结算报告（Mock 版 settle 的响应体） */
export function buildReport(session: TrainingSession): SettleReport {
  const verdicts: Verdict[] = session.items.map((item) => {
    const problem = MOCK_PROBLEMS.find((p) => p.item_id === item.item_id);
    const base = problem?.verdict ?? {
      label: 'defect_present' as const,
      level: 'L2' as const,
      confidence: 0.7,
      references: [],
    };
    // 交互轮数影响裁定等级（演示逻辑，不代表真实后端评分规则）
    const levelBoost = Math.max(0, item.rounds_done - 1);
    const ladder = ['L0', 'L1', 'L2', 'L3', 'L4'] as const;
    const baseIdx = ladder.indexOf(base.level);
    const level = ladder[Math.min(baseIdx + levelBoost, ladder.length - 1)];

    const refs: CitationRef[] = base.references.map((name, i) => ({
      evidence_id: `REF-${item.item_id}-${i + 1}`,
      doc_id: 'demo-bank',
      chunk_id: `chunk-${i + 1}`,
      char_start: 0,
      char_end: name.length,
      quote: name,
    }));

    return {
      item_id: item.item_id,
      label: base.label,
      level,
      confidence: Math.min(0.98, base.confidence + item.rounds_done * 0.02),
      escalated: level === 'L4',
      rationale: `本题编号 ${item.item_id}。你在 ${item.rounds_done} 轮交互中完成了审查推演。结算审阅结论：${problem?.defect_desc ?? '未发现明确缺陷。'}`,
      citation: {
        precision: Math.min(0.98, base.confidence + item.rounds_done * 0.02),
        recall: refs.length > 0 ? 1 : 0,
        supported: refs.map((r) => r.evidence_id),
        unsupported: [],
        missing: [],
      },
      references: refs,
    };
  });

  const calls = session.budget.total - session.budget.remaining;
  const cost_cny = Math.round(calls * 0.02 * 100) / 100;

  const summary = verdicts
    .map((v) => `- ${v.item_id}：${v.level}（置信度 ${(v.confidence * 100).toFixed(0)}%）`)
    .join('\n');

  const markdown = `# 训练报告 ${session.session_id}\n\n## 总体结果\n\n- 完成题目：${session.items.length} 道\n- 模型调用：${calls} / ${session.budget.cap} 次\n- 本次费用：¥${cost_cny.toFixed(2)}\n\n## 分题评估\n\n${summary}\n\n> 注：L0–L4 等级为单题评估结论，不代表合成总分；费用为演示估算值。`;

  return {
    session_id: session.session_id,
    verdicts,
    calls,
    cost_cny,
    markdown,
  };
}