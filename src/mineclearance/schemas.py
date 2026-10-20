"""冻结的数据契约。

这个文件对应编排文档里的「schema 先冻结」。五个人的协作里，
口径不一致比写错代码更贵，所以这里所有 dataclass 都是 frozen 的，
改字段必须走一次显式的版本号变更。
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "1.0.0"


class DefectType(str, Enum):
    LOGIC = "logic"
    BOUNDARY = "boundary"
    API_MISUSE = "api_misuse"
    DATA_LEAK = "data_leak"
    TYPE_CONFUSION = "type_confusion"
    SECURITY = "security"
    PERF = "perf"
    DOC_MISMATCH = "doc_mismatch"


class JudgeLabel(str, Enum):
    """封闭集。裁判只能从这三个里选，不允许自由文本。"""

    DEFECT = "defect_present"
    NONE = "no_defect"
    PARTIAL = "partial"


class Level(str, Enum):
    L1 = "L1_perception"
    L2 = "L2_localization"
    L3 = "L3_attribution"
    L4 = "L4_repair"

    @property
    def rank(self) -> int:
        return {"L1_perception": 1, "L2_localization": 2, "L3_attribution": 3, "L4_repair": 4}[self.value]


class SessionState(str, Enum):
    OPEN = "open"
    SETTLED = "settled"


@dataclass(frozen=True)
class EvidenceSpan:
    """一段被封存的原文。封印后只读，只能按 id 取回。"""

    evidence_id: str
    doc_id: str
    chunk_id: str
    char_start: int
    char_end: int
    quote: str

    def __post_init__(self) -> None:
        if not self.evidence_id:
            raise ValueError("evidence_id 不能为空")
        if self.char_start < 0 or self.char_end <= self.char_start:
            raise ValueError("字符区间非法: %d-%d" % (self.char_start, self.char_end))
        if len(self.quote) != self.char_end - self.char_start:
            raise ValueError("quote 长度必须等于区间长度，否则引用不可核验")


@dataclass(frozen=True)
class DefectItem:
    """一颗雷。original 是原版，planted 是埋雷版。"""

    item_id: str
    language: str
    defect_type: DefectType
    title: str
    original: str
    planted: str
    diff: str
    evidence_ids: Tuple[str, ...]
    expected_level: Level
    rubric_hint: str = ""
    verified: bool = False
    verify_source: str = "none"

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("item_id 不能为空")
        if not self.original or not self.planted:
            raise ValueError("原版与埋雷版都不能为空")
        if self.original == self.planted:
            raise ValueError("埋雷版必须与原版不同")
        if not self.evidence_ids:
            raise ValueError("每颗雷必须绑定至少一条证据，否则无法核验引用")

    def fingerprint(self) -> str:
        """题库缓存键。同样的原版与埋雷版只应存在一份。"""
        raw = (self.language + "\x00" + self.original + "\x00" + self.planted).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]


@dataclass(frozen=True)
class StudentAnswer:
    text: str
    cited_evidence_ids: Tuple[str, ...] = ()
    proposed_fix: str = ""

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("作答不能为空")


@dataclass(frozen=True)
class RoundRecord:
    index: int
    answer: StudentAnswer
    challenge: str
    calls: int = 1


@dataclass(frozen=True)
class ItemRun:
    item: DefectItem
    target_rounds: int
    rounds: Tuple[RoundRecord, ...] = ()

    @property
    def done(self) -> bool:
        return len(self.rounds) >= self.target_rounds

    def append(self, record: RoundRecord) -> "ItemRun":
        return ItemRun(item=self.item, target_rounds=self.target_rounds, rounds=self.rounds + (record,))


@dataclass(frozen=True)
class CitationReport:
    precision: float
    recall: float
    supported: Tuple[str, ...] = ()
    unsupported: Tuple[str, ...] = ()
    missing: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Verdict:
    item_id: str
    label: JudgeLabel
    level: Level
    confidence: float
    escalated: bool
    rationale: str
    citation: CitationReport

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence 必须在 0 到 1 之间")


@dataclass(frozen=True)
class SessionReport:
    session_id: str
    verdicts: Tuple[Verdict, ...]
    calls: int
    cost_cny: float
    latency_ms: int
    unverified_items: int
    markdown: str
    stage_calls: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ItemSpec:
    """出题单。离线阶段的输入：出什么题、埋什么雷、期望判到哪一级。

    query 留空时由 rag.as_query() 用 topic + defect_type 拼一次就定稿，
    不做在线查询改写——改写要再发一次请求，会从 12 次里扣。
    """

    item_id: str
    topic: str
    language: str
    defect_type: DefectType
    expected_level: Level
    query: str = ""

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("item_id 不能为空")
        if not self.topic.strip():
            raise ValueError("topic 不能为空")

    def fingerprint(self) -> str:
        """出题单指纹。题库按它查，查到了就不用再出题、再埋雷。"""
        raw = "\x00".join(
            [self.language, self.defect_type.value, self.expected_level.value, self.topic]
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]


def to_dict(obj: Any) -> Any:
    """递归转成可 JSON 化的结构，枚举取 value。"""
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Mapping):
        return {str(k): to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    return obj
