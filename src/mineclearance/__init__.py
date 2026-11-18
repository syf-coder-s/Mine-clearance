"""排雷兵：学会拆穿 AI 写的代码。

包的结构按职责切，不按「谁写的」切：
    config      预算与开关，只读一次
    schemas     冻结的数据契约（改字段 = 升版本号）
    budget      调用额度守卫，llm 与 agents 共用
    llm         模型层，只管发请求，不管编排
    rag         检索层，封印之后只读
    agents      四个角色，各自只做一件事
    orchestration  主链，把上面几层串成一条可数调用次数的线
    api         对外 HTTP 面，含预留的检索代理

核心约束只有一条：一次会话的在线调用不超过 12 次，超了抛异常。
"""

from .budget import STAGE_LIMITS, BudgetExceeded, CallBudget
from .config import DEFAULT_SETTINGS, Settings
from .schemas import (
    SCHEMA_VERSION,
    CitationReport,
    DefectItem,
    DefectType,
    EvidenceSpan,
    JudgeLabel,
    Level,
    SessionReport,
    StudentAnswer,
    Verdict,
)

__all__ = [
    "SCHEMA_VERSION",
    "Settings",
    "DEFAULT_SETTINGS",
    "CallBudget",
    "BudgetExceeded",
    "STAGE_LIMITS",
    "DefectType",
    "DefectItem",
    "EvidenceSpan",
    "StudentAnswer",
    "JudgeLabel",
    "Level",
    "Verdict",
    "CitationReport",
    "SessionReport",
]

__version__ = "2.0.0"
