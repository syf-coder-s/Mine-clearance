"""冒烟：不联网、不要密钥，把整条链跑一遍并核对调用次数。

跑法（仓库根目录）：
    python scripts/smoke.py

它验证的是申报表里承诺的那几条，而不是「代码没报错」：
    1  一次会话的在线调用不超过 12 次，且次数能按阶段对上；
    2  对抗阶段不超过 9 次（留 3 次给结算与复盘）；
    3  结算恰好 1 次决策调用，升级最多 1 次；
    4  封印之后 retrieve()/index() 直接抛错，只有 fetch() 还能读；
    5  题库命中时不再出题、不再埋雷（离线调用为 0）；
    6  未通过复核的题不参与评分；
    7  对抗与裁判不同源（同源时升级复核等于自己查自己，功能上看不出症状）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

_ROOT = Path(__file__).resolve().parents[1]
for _path in (str(_ROOT), str(_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from mineclearance.agents import MarkerProbe  # noqa: E402
from mineclearance.config import Settings  # noqa: E402
from mineclearance.llm import build_router  # noqa: E402
from mineclearance.orchestration import QuestionBank, Session, summarize_trace  # noqa: E402
from mineclearance.rag import IndexSealed, build_retriever  # noqa: E402
from mineclearance.schemas import (  # noqa: E402
    DefectItem,
    DefectType,
    ItemSpec,
    Level,
    StudentAnswer,
)


class ScriptedAnswers:
    """脚本作答：定位、触发条件、修复三段都写全，用来核对能判到 L4。"""

    def __init__(self) -> None:
        self.rounds = 0

    def submit(self, item: DefectItem, round_index: int, challenge: str) -> StudentAnswer:
        self.rounds += 1
        cited = list(item.evidence_ids[:1])
        if round_index == 1:
            # 故意多标一个不存在的证据，用来验证引用核验是本地算、不花调用
            cited.append("ev_deadbeef0000")
        return StudentAnswer(
            text=(
                "缺陷在 %s 的那行比较上：abs(value - target) <= abs(best - target)。"
                "当输入里出现与 target 距离相等的两个元素时（例如 values=[1, 3]、target=2），"
                "因为用的是 <=，后出现的那个会覆盖先出现的，返回值依赖遍历顺序。"
                "触发条件是「存在两个距离相等的候选」。"
                "应改为 abs(value - target) < abs(best - target)，保留先出现的那个。"
                % item.item_id
            ),
            cited_evidence_ids=tuple(cited),
            proposed_fix="把 <= 改成 <",
        )


def build_specs() -> Sequence[ItemSpec]:
    return (
        ItemSpec(
            item_id="item-1",
            topic="在有序数组里找最接近目标值的元素",
            language="python",
            defect_type=DefectType.BOUNDARY,
            expected_level=Level.L2,
        ),
        ItemSpec(
            item_id="item-2",
            topic="等距候选时的返回值稳定性",
            language="python",
            defect_type=DefectType.LOGIC,
            expected_level=Level.L3,
        ),
        ItemSpec(
            item_id="item-3",
            topic="边界比较运算符的修复",
            language="python",
            defect_type=DefectType.BOUNDARY,
            expected_level=Level.L4,
        ),
    )


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("冒烟失败：" + message)


def rag_line(retriever) -> str:
    """一行说清「到底连没连上后端」。现场演示最怕悄悄降级了却没人发现。"""
    summary = getattr(retriever, "summary", None)
    if not callable(summary):
        return type(retriever).__name__
    info = summary()
    line = str(info.get("backend", type(retriever).__name__))
    if info.get("degraded"):
        line += "（已降级到本地桩：%s）" % info.get("degrade_reason", "")
    return line


def main() -> int:
    settings = Settings(llm_provider="mock", max_calls_per_session=12)
    router = build_router(settings)
    retriever = build_retriever(settings)
    print("检索后端：%s" % rag_line(retriever))

    bank = QuestionBank()
    answers = ScriptedAnswers()
    session = Session(
        settings=settings,
        router=router,
        retriever=retriever,
        answers=answers,
        bank=bank,
        probe=MarkerProbe(),
    )

    report = session.run(build_specs(), session_id="s_smoke")

    print()
    print(summarize_trace(report, session.trace))
    print()
    print("---- 复盘 ----")
    print(report.markdown)

    # 1、2、3：调用次数
    check(report.calls <= settings.max_calls_per_session, "在线调用 %d 次，超过 12 次上限" % report.calls)
    stages = dict(report.stage_calls)
    check(stages.get("adversary", 0) <= 9, "对抗阶段 %d 次，超过 9 次" % stages.get("adversary", 0))
    check(stages.get("judge_decision", 0) == 1, "结算决策调用应为 1 次，实际 %s" % stages.get("judge_decision", 0))
    check(
        stages.get("judge_escalation", 0) <= 1,
        "升级调用 %s 次，超过 1 次" % stages.get("judge_escalation", 0),
    )
    check(stages.get("report", 0) == 1, "复盘调用应为 1 次，实际 %s" % stages.get("report", 0))

    # 离线调用不占在线预算，但必须被单独计数
    check(router.offline_calls > 0, "离线阶段没有发生任何调用，链路可能没走到出题/埋雷")
    check(
        report.calls == sum(stages.values()),
        "总数 %d 与阶段分布之和 %d 对不上" % (report.calls, sum(stages.values())),
    )

    # 厂商隔离：对抗与升级裁判同源时，这次复核等于自己查自己。
    # 功能上看不出症状，只有这条检查会先喊出来。
    check(router.vendor_isolated, "演练模式下厂商隔离应成立：对抗与裁判必须不同源")

    # 4：封印
    check(retriever.sealed, "会话打开后索引应处于封印状态")
    for bad_call in (
        lambda: retriever.retrieve("再查一次", top_k=3),
        lambda: retriever.index("doc_x", "print(1)", language="python"),
    ):
        try:
            bad_call()
        except IndexSealed:
            pass
        else:
            raise SystemExit("冒烟失败：封印后仍然可以改索引或重新检索")
    for verdict in report.verdicts:
        check(
            bool(verdict.citation.supported),
            "%s 的引用没有被认到封存证据里，引用核验可能失效" % verdict.item_id,
        )

    # 5：题库命中
    check(len(bank) == 3, "题库应有 3 道题，实际 %d" % len(bank))
    router2 = build_router(settings)
    session2 = Session(
        settings=settings,
        router=router2,
        retriever=build_retriever(settings),
        bank=bank,
        probe=MarkerProbe(),
    )
    handle2 = session2.open(build_specs(), session_id="s_smoke_2")
    check(router2.offline_calls == 0, "题库命中时不应再出题/埋雷，实际离线调用 %d 次" % router2.offline_calls)
    check(len(handle2.runs) == 3, "题库命中后应有 3 道题可打，实际 %d" % len(handle2.runs))

    # 6：未通过复核的题不进评分
    session3 = Session(
        settings=settings,
        router=build_router(settings),
        retriever=build_retriever(settings),
        probe=None,  # 不给探针 = 无法证明雷埋上了
    )
    handle3 = session3.open(build_specs(), session_id="s_smoke_3")
    check(len(handle3.runs) == 0, "没有探针时不应有可打的题，实际 %d 道" % len(handle3.runs))
    report3 = session3.settle(handle3)
    check(report3.verdicts == (), "没有探针时不应产出任何判级")
    check(report3.unverified_items == 3, "未复核计数应为 3，实际 %d" % report3.unverified_items)

    print()
    print(
        "冒烟通过：在线 %d 次（对抗 %d + 结算 %d + 升级 %d + 复盘 %d），离线 %d 次，成本 %.4f 元"
        % (
            report.calls,
            stages.get("adversary", 0),
            stages.get("judge_decision", 0),
            stages.get("judge_escalation", 0),
            stages.get("report", 0),
            router.offline_calls,
            report.cost_cny,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
