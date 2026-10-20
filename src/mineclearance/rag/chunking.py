"""结构切分。

为什么不按固定行数切：
    按行切会把一个函数拦腰截断，签名在上半、边界处理在下半，检索回来的片段
    自己就不完整，裁判据此判「定位错误」，学生被冤枉。CAST 那篇实测过这件事。
    所以切分粒度跟着雷的类型走：代码按函数（含签名与完整体），数据按表，
    文章按小节。切得对不对，直接决定证据链能不能核验。
"""

from __future__ import annotations

import re
from typing import List, Tuple

_CODE_START = re.compile(r"^(?:async\s+def|def|class)\s+\w+", re.MULTILINE)
_TABLE_START = re.compile(r"^(?:CREATE\s+TABLE|INSERT\s+INTO|---\s*|\|\s*字段|\|\s*-{3,})", re.MULTILINE | re.IGNORECASE)
_SECTION_START = re.compile(r"^#{2,3}\s+\S+", re.MULTILINE)

Span = Tuple[int, int]


def _split_at(text: str, pattern: re.Pattern) -> List[Span]:
    starts = [m.start() for m in pattern.finditer(text)]
    if not starts:
        return [(0, len(text))] if text.strip() else []
    spans: List[Span] = []
    if starts[0] > 0 and text[: starts[0]].strip():
        spans.append((0, starts[0]))
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        spans.append((start, end))
    return spans


def _trim(text: str, spans: List[Span]) -> List[Span]:
    """去掉首尾空白，但保持原文字符偏移，否则 evidence 的 quote 长度对不上。"""
    trimmed: List[Span] = []
    for start, end in spans:
        while start < end and text[start] in " \t\r\n":
            start += 1
        while end > start and text[end - 1] in " \t\r\n":
            end -= 1
        if end > start:
            trimmed.append((start, end))
    return trimmed


def split(text: str, language: str = "text") -> List[Span]:
    """按语言选切法。返回 (char_start, char_end) 列表，始终指向原文。"""
    normalized = (language or "text").strip().lower()
    if normalized in {"python", "py", "code", "js", "javascript", "java", "cpp", "go"}:
        spans = _split_at(text, _CODE_START)
    elif normalized in {"table", "data", "sql", "csv"}:
        spans = _split_at(text, _TABLE_START)
    else:
        spans = _split_at(text, _SECTION_START)
    return _trim(text, spans)


def chunk_id(doc_id: str, char_start: int, char_end: int) -> str:
    return "%s#%d-%d" % (doc_id, char_start, char_end)
