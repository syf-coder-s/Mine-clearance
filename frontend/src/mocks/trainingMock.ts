/**
 * 训练 Mock 数据与本地状态机
 *
 * 重要约束（与规格 §9 一致）：
 * 1. 题库中的代码预埋缺陷，但训练阶段绝不下发正确答案/缺陷位置/触发条件/修复方案。
 * 2. AI 对抗回复按轮次变化，只做通用质疑与追问，不指出缺陷位置。
 * 3. 证据仅白名单字段：excerpt 只有在 visible_in_code=true 时才非空。
 * 4. 每次训练固定 3 题，每题最多 3 轮，每场最多 12 次调用（预留 3 次结算）。
 */
import { mockDb, genId, mockDelay } from './mockDb';
import type {
  BudgetInfo,
  EvidenceItem,
  Language,
  SubmitRequest,
  SubmitResponse,
  TrainingDirection,
  TrainingItem,
  TrainingSession,
} from '../types/training';
import { buildReport } from './reportMock';
import { upsertHistory } from './historyMock';
import type { SettleReport } from '../types/report';

/* ---------- 题目池（埋雷版代码，与真实后端无关的演示题目） ---------- */

interface MockProblem {
  item_id: string;
  title: string;
  language: string;
  direction: TrainingDirection;
  /** 埋雷版代码：缺陷隐藏在代码中，前端只负责展示 */
  code: string;
  /** 训练阶段披露的“提示性证据” */
  evidence: EvidenceItem[];
  /** 缺陷所在行区间（仅报告结算时用于引用展示，训练中禁用） */
  defect_lines: [number, number];
  /** 标准缺陷描述（仅结算后展示） */
  defect_desc: string;
  /** 预置结算裁定 */
  verdict: {
    label: 'defect_present' | 'no_defect';
    level: 'L0' | 'L1' | 'L2' | 'L3' | 'L4';
    confidence: number;
    references: string[];
  };
}

export const MOCK_PROBLEMS: MockProblem[] = [
  {
    item_id: 'PRB-BIN-001',
    title: '二分查找的边界条件审查',
    language: 'python',
    direction: 'logic_boundary',
    code: `def binary_search(arr, target):
    """在有序数组 arr 中查找 target，返回下标；不存在则返回 -1。"""
    left, right = 0, len(arr)
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1


if __name__ == "__main__":
    data = [2, 5, 8, 12, 16, 23, 38]
    print(binary_search(data, 38))  # 期望输出：6`,
    evidence: [
      { evidence_id: 'EV-BIN-001-01', excerpt: '该函数在数组边界附近有未覆盖的执行路径，请关注循环条件与下标取值的关系。', visible_in_code: true },
    ],
    defect_lines: [2, 10],
    defect_desc: '右边界初始化为 len(arr) 且循环条件使用 <=，当目标不存在或位于特定位置时会触发越界访问。',
    verdict: {
      label: 'defect_present',
      level: 'L3',
      confidence: 0.86,
      references: ['循环不变量文档', 'Python 列表索引规范'],
    },
  },
  {
    item_id: 'PRB-PAG-002',
    title: '分页参数的边界处理',
    language: 'python',
    direction: 'logic_boundary',
    code: `def paginate(items, page, page_size):
    """返回第 page 页的数据，page 从 1 开始。"""
    start = page * page_size
    end = start + page_size
    return items[start:end]


def total_pages(total, page_size):
    """计算总页数。"""
    return total // page_size


if __name__ == "__main__":
    items = list(range(1, 26))
    print(paginate(items, 1, 10))  # 期望输出：[1..10]
    print(total_pages(25, 10))     # 期望输出：3`,
    evidence: [
      { evidence_id: 'EV-PAG-002-01', excerpt: '接口文档中约定 page 从 1 开始计数，请核对实现中的换算逻辑。', visible_in_code: true },
    ],
    defect_lines: [1, 8],
    defect_desc: '起始偏移未按“page 从 1 开始”换算，且总页数计算忽略余数，导致分页结果整体错位与漏页。',
    verdict: {
      label: 'defect_present',
      level: 'L2',
      confidence: 0.78,
      references: ['分页接口设计约定', '常见分页实现对照'],
    },
  },
  {
    item_id: 'PRB-CMP-003',
    title: '等距候选值的返回稳定性',
    language: 'python',
    direction: 'api_usage',
    code: `def find_nearest(values, target):
    """返回 values 中与 target 距离最近的下标；有多个等距值时返回任意一个。"""
    best_idx = -1
    best_dist = None
    for i, v in enumerate(values):
        dist = abs(v - target)
        if best_dist is None or dist <= best_dist:
            best_dist = dist
            best_idx = i
    return best_idx


if __name__ == "__main__":
    values = [1, 5, 9, 13]
    print(find_nearest(values, 7))  # 返回 1 或 2 取决于实现`,
    evidence: [
      { evidence_id: 'EV-CMP-003-01', excerpt: '该函数被下游服务用作稳定排序依据，请审查其在多个等距候选值时的行为。', visible_in_code: true },
    ],
    defect_lines: [2, 10],
    defect_desc: '使用 <= 会让后出现的等距值覆盖先出现的值，且空列表返回 -1 可能被误当作合法下标。',
    verdict: {
      label: 'defect_present',
      level: 'L4',
      confidence: 0.91,
      references: ['稳定选择语义', '下游排序服务契约'],
    },
  },
];

/* ---------- AI 对抗回复模板（按轮次，不泄露缺陷） ---------- */

const CHALLENGE_TEMPLATES: string[] = [
  '收到你的审查意见。请进一步说明：你的判断基于代码中的哪些具体行？在什么样的输入条件下，你所描述的问题才会被触发？',
  '记录在案。换一个角度追问：如果这个问题真实存在，它会导致什么样的外部后果（错误结果、异常、性能损耗）？请评估影响范围与严重程度。',
  '你已完成本轮的对抗推演。请给出一个最小可复现的输入样例，并说明若进行修复，如何验证修复没有引入新问题。本题交互到此结束。',
];

/* ---------- 会话存储 ---------- */

function loadSessions(): TrainingSession[] {
  return mockDb.read<TrainingSession[]>(mockDb.keys.sessions, []);
}

function saveSessions(list: TrainingSession[]): void {
  mockDb.write(mockDb.keys.sessions, list);
}

function freshBudget(): BudgetInfo {
  return { cap: 12, total: 12, remaining: 12, reserve: 3 };
}

/** 创建训练会话（Mock 版 POST /v1/sessions） */
export async function createMockSession(
  language: Language,
  direction: TrainingDirection,
): Promise<TrainingSession> {
  await mockDelay();
  const problems =
    direction === 'random'
      ? MOCK_PROBLEMS
      : MOCK_PROBLEMS.filter((p) => p.direction === direction).length > 0
        ? MOCK_PROBLEMS.filter((p) => p.direction === direction)
        : MOCK_PROBLEMS;

  const picked = problems.slice(0, 3);
  // 不足 3 题时用题库头部补足，保证固定 3 题
  while (picked.length < 3) {
    const extra = MOCK_PROBLEMS.find((p) => !picked.includes(p));
    if (!extra) break;
    picked.push(extra);
  }

  const items: TrainingItem[] = picked.map((p) => ({
    item_id: p.item_id,
    language: p.language,
    title: p.title,
    code: p.code,
    rounds_done: 0,
    target_rounds: 3,
    evidence: p.evidence,
  }));

  const session: TrainingSession = {
    session_id: genId('sess'),
    schema_version: '1.0.0-demo',
    unverified_items: items.length,
    budget: freshBudget(),
    items,
    language,
    direction,
    status: 'in_progress',
  };

  const all = loadSessions();
  all.unshift(session);
  saveSessions(all);

  upsertHistory({
    session_id: session.session_id,
    created_at: new Date().toISOString(),
    direction: session.direction ?? 'random',
    language: session.language ?? 'python',
    status: 'in_progress',
    summaries: items.map((it) => ({
      item_id: it.item_id,
      title: it.title,
      rounds_done: 0,
      target_rounds: 3,
    })),
  });

  return session;
}

/** 读取会话（Mock 版 GET /v1/sessions/{id}） */
export async function getMockSession(sessionId: string): Promise<TrainingSession> {
  await mockDelay(250);
  const found = loadSessions().find((s) => s.session_id === sessionId);
  if (!found) {
    throw { status: 404, body: { code: 'SESSION_NOT_FOUND', message: '训练会话不存在或已过期' } };
  }
  return found;
}

/** 提交审查意见（Mock 版 POST /v1/sessions/{id}/submit） */
export async function submitMockReview(
  sessionId: string,
  req: SubmitRequest,
): Promise<SubmitResponse> {
  await mockDelay(500);
  const all = loadSessions();
  const session = all.find((s) => s.session_id === sessionId);
  if (!session) {
    throw { status: 404, body: { code: 'SESSION_NOT_FOUND', message: '训练会话不存在或已过期' } };
  }
  if (session.status === 'finished') {
    throw { status: 409, body: { code: 'SESSION_FINISHED', message: '该训练已完成结算，不能再提交审查意见' } };
  }

  const item = session.items.find((i) => i.item_id === req.item_id);
  if (!item) {
    throw { status: 404, body: { code: 'ITEM_NOT_FOUND', message: '题目不存在' } };
  }
  if (item.rounds_done >= item.target_rounds) {
    throw { status: 409, body: { code: 'TARGET_REACHED', message: '该题已达到最大交互轮数' } };
  }
  // 预留 3 次结算调用：剩余 <= reserve 时拒绝提交
  if (session.budget.remaining <= session.budget.reserve) {
    throw { status: 402, body: { code: 'BUDGET_EXHAUSTED', message: '本次训练调用预算已用完，请结算训练' } };
  }

  item.rounds_done += 1;
  session.unverified_items = session.items.filter((i) => i.rounds_done < i.target_rounds).length;
  session.budget = { ...session.budget, remaining: session.budget.remaining - 1 };

  const roundNow = item.rounds_done;
  const finished = roundNow >= item.target_rounds;
  const challenge = CHALLENGE_TEMPLATES[Math.min(roundNow - 1, CHALLENGE_TEMPLATES.length - 1)];

  saveSessions(all);
  upsertHistory({
    session_id: session.session_id,
    created_at: new Date().toISOString(),
    direction: session.direction ?? 'random',
    language: session.language ?? 'python',
    status: 'in_progress',
    summaries: session.items.map((it) => ({
      item_id: it.item_id,
      title: it.title,
      rounds_done: it.rounds_done,
      target_rounds: it.target_rounds,
    })),
  });

  return {
    item_id: item.item_id,
    accepted: true,
    reason: finished ? 'target_reached' : 'ok',
    round: roundNow,
    challenge,
    rounds_done: item.rounds_done,
    target_rounds: item.target_rounds,
    finished,
    budget: session.budget,
  };
}

/** 结算训练（Mock 版 POST /v1/sessions/{id}/settle） */
export async function settleMockSession(sessionId: string): Promise<SettleReport> {
  await mockDelay(900);
  const all = loadSessions();
  const session = all.find((s) => s.session_id === sessionId);
  if (!session) {
    throw { status: 404, body: { code: 'SESSION_NOT_FOUND', message: '训练会话不存在或已过期' } };
  }
  if (session.status === 'finished') {
    throw { status: 409, body: { code: 'SESSION_FINISHED', message: '该训练已完成结算' } };
  }

  const report = buildReport(session);
  session.status = 'finished';
  saveSessions(all);

  const reports = mockDb.read<Record<string, SettleReport>>(mockDb.keys.reports, {});
  reports[sessionId] = report;
  mockDb.write(mockDb.keys.reports, reports);

  upsertHistory({
    session_id: session.session_id,
    created_at: new Date().toISOString(),
    direction: session.direction ?? 'random',
    language: session.language ?? 'python',
    status: 'finished',
    summaries: session.items.map((it) => ({
      item_id: it.item_id,
      title: it.title,
      rounds_done: it.rounds_done,
      target_rounds: it.target_rounds,
    })),
  });

  return report;
}

/** 读取已结算报告（Mock 版，localStorage） */
export async function getMockReport(sessionId: string): Promise<SettleReport> {
  await mockDelay(300);
  const reports = mockDb.read<Record<string, SettleReport>>(mockDb.keys.reports, {});
  const report = reports[sessionId];
  if (!report) {
    throw { status: 404, body: { code: 'REPORT_NOT_FOUND', message: '训练报告不存在，请先完成结算' } };
  }
  return report;
}

/** 判断题目当前轮次（供工作台 UI 使用） */
export function challengeForRound(roundNow: number): string {
  return CHALLENGE_TEMPLATES[Math.min(roundNow - 1, CHALLENGE_TEMPLATES.length - 1)];
}