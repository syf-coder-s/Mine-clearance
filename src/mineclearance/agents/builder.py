"""出题：从一份需求写出一段「本来就对」的代码/数据/短文。

这一层在离线跑，不占 12 次在线预算。之所以允许它用大模型，是因为它出错
可以被下一层（埋雷 + 探针）兜住；而在线的对抗轮次出错，就没人兜了。
"""

from __future__ import annotations

from ..llm import Router, system, user
from ..schemas import ItemSpec


class BuilderError(RuntimeError):
    pass


class Builder:
    def __init__(self, router: Router) -> None:
        self.router = router

    def draft(self, spec: ItemSpec) -> str:
        messages = [
            system(
                "你是出题人。你要写一段**正确**的示例材料，供后续埋雷使用。"
                "要求：自包含、能独立运行或独立阅读；不超过 40 行；"
                "不要写注释解释「这里是易错点」，不要把缺陷提前说出来。"
                "如果语言是 python，请在末尾保留一行 `# OK` 作为健康标记。"
            ),
            user(
                "TASK=builder\n"
                "item_id=%s\n"
                "TOPIC=%s\n"
                "LANGUAGE=%s\n"
                "DEFECT_TYPE=%s\n"
                "EXPECTED_LEVEL=%s"
                % (
                    spec.item_id,
                    spec.topic,
                    spec.language,
                    spec.defect_type.value,
                    spec.expected_level.value,
                )
            ),
        ]
        response = self.router.offline("builder", messages)
        source = _strip_fence(response.text)
        if not source.strip():
            raise BuilderError("出题返回为空: %s" % spec.item_id)
        return source


def _strip_fence(text: str) -> str:
    """模型爱把代码包在 ``` 里，去掉围栏但保留内容原文。"""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 2:
        return stripped
    lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)
