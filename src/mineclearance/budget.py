"""预算守卫。

12 次是申报表里的硬上限，不是目标值。这里的实现让「超了」变成异常，
而不是日志里的一行 warning。任何人想在链路里多插一次调用，都必须改这张表。

放在包根而不是 orchestration/ 下，是因为 llm 与 agents 两层都要查额度：
    预算不是编排的一部分，是它们共同的约束。
    放在 orchestration/ 里会让 llm → orchestration → pipeline → agents → llm 绕成一圈。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

STAGE_LIMITS: Dict[str, int] = {
    "adversary": 9,          # 三段 × 2 至 3 轮
    "judge_decision": 1,     # 决策层，只吃抽取表
    "judge_escalation": 1,   # 收紧后只留 1 次升级余量
    "report": 1,
}


class BudgetExceeded(RuntimeError):
    def __init__(self, message: str, stage: str, total: int, cap: int) -> None:
        super().__init__(message)
        self.stage = stage
        self.total = total
        self.cap = cap


@dataclass(frozen=True)
class CallRecord:
    stage: str
    tier: str
    model: str
    latency_ms: int
    cost_cny: float


class CallBudget:
    def __init__(
        self,
        cap: int = 12,
        cost_cap_cny: float = 0.08,
        stage_limits: Optional[Mapping[str, int]] = None,
    ) -> None:
        self.cap = cap
        self.cost_cap_cny = cost_cap_cny
        self.stage_limits: Dict[str, int] = dict(STAGE_LIMITS)
        if stage_limits:
            self.stage_limits.update(stage_limits)
        self._counts: Counter = Counter()
        self._records: List[CallRecord] = []
        self._cost = 0.0

    def check(self, stage: str) -> None:
        """调用前检查。宁可先拒绝，也不要先花钱再报错。"""
        limit = self.stage_limits.get(stage, 0)
        if limit == 0:
            raise BudgetExceeded("未登记的阶段: %s" % stage, stage, len(self._records), self.cap)
        if self._counts[stage] >= limit:
            raise BudgetExceeded(
                "阶段 %s 已达上限 %d" % (stage, limit), stage, len(self._records), self.cap
            )
        if len(self._records) >= self.cap:
            raise BudgetExceeded(
                "会话调用总数已达硬上限 %d" % self.cap, stage, len(self._records), self.cap
            )
        if self._cost >= self.cost_cap_cny:
            raise BudgetExceeded(
                "成本已达上限 %.4f 元" % self.cost_cap_cny, stage, len(self._records), self.cap
            )

    def record(self, stage: str, tier: str, model: str, latency_ms: int, cost_cny: float) -> int:
        self._counts[stage] += 1
        self._records.append(CallRecord(stage, tier, model, latency_ms, cost_cny))
        self._cost += cost_cny
        return len(self._records)

    @property
    def total(self) -> int:
        return len(self._records)

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.total)

    @property
    def cost_cny(self) -> float:
        return round(self._cost, 6)

    @property
    def latency_ms(self) -> int:
        return sum(r.latency_ms for r in self._records)

    def stage_calls(self) -> Dict[str, int]:
        return {k: v for k, v in self._counts.items()}

    def summary(self) -> Dict[str, object]:
        return {
            "total": self.total,
            "cap": self.cap,
            "remaining": self.remaining,
            "cost_cny": self.cost_cny,
            "latency_ms": self.latency_ms,
            "stage_calls": self.stage_calls(),
        }
