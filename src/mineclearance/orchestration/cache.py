"""题库缓存与结构记忆。

两者都只做一件事：把本该在线花的调用，搬到离线或者零次。
缓存键用内容指纹，不用自增 id，避免同一个雷被重复生成。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..schemas import DefectItem, DefectType, Level, to_dict


class QuestionBank:
    """题库。命中即整条复用：题、证据链、埋雷 diff 一起拿走。

    键有两种用法：
        默认用 item.fingerprint()（内容指纹，保证同一个雷只有一份）；
        预取阶段用 ItemSpec.fingerprint() 查（还没出题，只能按出题单查）。
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self._items: Dict[str, DefectItem] = {}
        if path is not None and path.exists():
            self._load()

    def get(self, key: str) -> Optional[DefectItem]:
        return self._items.get(key)

    def put(self, item: DefectItem, *, key: str = "") -> str:
        cache_key = key or item.fingerprint()
        self._items[cache_key] = item
        if self.path is not None:
            self._flush()
        return cache_key

    def __len__(self) -> int:
        return len(self._items)

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
        for entry in raw.get("items", []):
            item = DefectItem(
                item_id=entry["item_id"],
                language=entry["language"],
                defect_type=DefectType(entry["defect_type"]),
                title=entry["title"],
                original=entry["original"],
                planted=entry["planted"],
                diff=entry["diff"],
                evidence_ids=tuple(entry["evidence_ids"]),
                expected_level=Level(entry["expected_level"]),
                rubric_hint=entry.get("rubric_hint", ""),
                verified=entry.get("verified", False),
                verify_source=entry.get("verify_source", "none"),
            )
            self._items[entry.get("key") or item.fingerprint()] = item

    def _flush(self) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        items = []
        for key, item in self._items.items():
            payload = to_dict(item)
            payload["key"] = key
            items.append(payload)
        self.path.write_text(
            json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class StructuralMemory:
    """结构记忆。

    以前跑过的同型题，直接给出轮次与追问模板，在线调用为 0。
    这不是投机预跑：它给的是结构与话术，不含任何针对本次作答的推断。
    """

    def __init__(self, table: Optional[Dict[Tuple[str, str], Tuple[int, List[str]]]] = None) -> None:
        self._table = table or {}

    def add(self, defect_type: DefectType, level: Level, rounds: int, templates: List[str]) -> None:
        self._table[(defect_type.value, level.value)] = (rounds, templates)

    def rounds_for(self, defect_type: DefectType, level: Level) -> Optional[int]:
        hit = self._table.get((defect_type.value, level.value))
        return hit[0] if hit else None

    def templates_for(self, defect_type: DefectType, level: Level) -> List[str]:
        hit = self._table.get((defect_type.value, level.value))
        return list(hit[1]) if hit else []
