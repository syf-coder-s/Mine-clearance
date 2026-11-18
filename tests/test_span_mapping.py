"""map_span_to_planted：把原版代码里的证据区间映射到埋雷版行区间。

核心约束：excerpt 只能来自 planted，映射失败必须退化为 (0, 0, "")——
开局不能失败，也绝不能把原版正确写法回显给学生。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mineclearance.api.store import map_span_to_planted  # noqa: E402


ORIGINAL = (
    "def pick(values):\n"
    "    best = values[0]\n"
    "    for v in values:\n"
    "        if abs(v - target) <= abs(best - target):\n"
    "            best = v\n"
    "    return best\n"
)


def span_of(text: str, needle: str) -> tuple:
    """(char_start, char_end) 覆盖 needle 所在的整行。"""
    line_start = text.index(needle)
    line_end = text.index("\n", line_start)
    return (line_start, line_end)


class MidLineEditTest(unittest.TestCase):
    """中间行改动：行数不变，行号一一对应。"""

    def test_maps_to_the_edited_line(self):
        planted = ORIGINAL.replace("<= abs(best - target)", "< abs(best - target)")
        start, end = span_of(ORIGINAL, "if abs(v - target)")
        line_start, line_end, excerpt = map_span_to_planted(ORIGINAL, planted, start, end)
        self.assertEqual((line_start, line_end), (4, 4))
        self.assertEqual(excerpt, "        if abs(v - target) < abs(best - target):")
        self.assertIn(excerpt, planted)
        self.assertNotIn("<=", excerpt)


class FirstLineEditTest(unittest.TestCase):
    """首行改动：映射仍应落在第 1 行。"""

    def test_maps_to_first_line(self):
        planted = ORIGINAL.replace("def pick(values):", "def pick_nearest(values):", 1)
        start, end = span_of(ORIGINAL, "def pick(values)")
        line_start, line_end, excerpt = map_span_to_planted(ORIGINAL, planted, start, end)
        self.assertEqual((line_start, line_end), (1, 1))
        self.assertEqual(excerpt, "def pick_nearest(values):")
        self.assertIn(excerpt, planted)


class PlantedHasExtraLineTest(unittest.TestCase):
    """埋雷版多出一行：被替换行映射到新增段的起始行。"""

    def test_maps_into_the_extra_segment(self):
        planted = ORIGINAL.replace(
            "    best = values[0]\n",
            "    best = None\n    seen = 0\n",
            1,
        )
        self.assertGreater(len(planted.splitlines()), len(ORIGINAL.splitlines()))
        start, end = span_of(ORIGINAL, "best = values[0]")
        line_start, line_end, excerpt = map_span_to_planted(ORIGINAL, planted, start, end)
        self.assertEqual((line_start, line_end), (2, 2), "原版第 2 行被替换成两行，应映射到替换段起始行")
        self.assertEqual(excerpt, "    best = None")
        self.assertIn(excerpt, planted)


class DegradeTest(unittest.TestCase):
    """任何对不上的输入都退化为 (0, 0, "")."""

    def test_out_of_range_returns_empty(self):
        self.assertEqual(map_span_to_planted(ORIGINAL, ORIGINAL, 10**6, 10**6 + 5), (0, 0, ""))

    def test_blank_inputs_return_empty(self):
        self.assertEqual(map_span_to_planted("", ORIGINAL, 0, 1), (0, 0, ""))
        self.assertEqual(map_span_to_planted(ORIGINAL, "", 0, 1), (0, 0, ""))

    def test_reversed_bounds_return_empty(self):
        self.assertEqual(map_span_to_planted(ORIGINAL, ORIGINAL, 5, 4), (0, 0, ""))


if __name__ == "__main__":
    unittest.main()