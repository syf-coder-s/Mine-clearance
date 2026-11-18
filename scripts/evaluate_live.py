"""真实模型验收与固定样本判例消融。只读 RAGFlow；产物包含教师答案，不对学生开放。

运行：docker compose exec -T api python scripts/evaluate_live.py
每次独立目录，保存中间结果；不自动重试付费请求。
"""
from __future__ import annotations
import csv
import hashlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mineclearance.agents import Adversary, Judge
from mineclearance.agents.judge import extract_row
from mineclearance.agents.pure_probe import PurePythonProbe
from mineclearance.api.store import default_specs
from mineclearance.budget import CallBudget
from mineclearance.config import Settings
from mineclearance.llm import build_router
from mineclearance.orchestration import Session
from mineclearance.rag import build_retriever, SealedView, as_query
from mineclearance.schemas import DefectItem, DefectType, ItemRun, Level, RoundRecord, StudentAnswer, to_dict


def save(directory, name, value):
    (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def fixtures():
    empty = 'def nearest(values, target):\n    """空输入返回 None；等距时保留先出现的值。"""\n    if not values:\n        return None\n    best = values[0]\n    for value in values[1:]:\n        if abs(value - target) < abs(best - target):\n            best = value\n    return best\n'
    tie = 'def nearest(values, target):\n    """空输入返回 None；等距时保留先出现的值。"""\n    if not values:\n        return None\n    best = values[0]\n    for value in values[1:]:\n        if abs(value - target) < abs(best - target):\n            best = value\n    return best\n'
    tests = 'def test_contract():\n    assert nearest([], 2) is None\n    assert nearest([1, 3], 2) == 1\n    assert nearest([1, 4], 3) == 4\n'
    false_source = tie.replace("保留先出现的值", "保留后出现的值").replace(" < abs", " <= abs")
    false_planted = false_source.replace(" <= abs", " < abs")
    false_tests = tests.replace("[1, 3], 2) == 1", "[1, 3], 2) == 3")
    return [
        dict(id="gold-empty", title="nearest 空输入边界处理", kind=DefectType.BOUNDARY,
             original=empty, planted=empty.replace("    if not values:\n        return None\n", ""), tests=tests,
             diff="删掉空输入守卫", answer="第3行 best = values[0]：当输入 values=[] 时触发 IndexError，因为未检查空列表。应在访问首元素之前增加 if not values: return None。",
             fix="if not values: return None", level=Level.L4, label="defect_present"),
        dict(id="gold-tie", title="nearest 等距候选时的返回值稳定性", kind=DefectType.LOGIC,
             original=tie, planted=tie.replace(" < abs", " <= abs"), tests=tests,
             diff="严格小于改为小于等于", answer="第7行距离比较用了 <=。当输入 [1,3]、target=2 时，等距的后一个3会覆盖1，与文档约定保留先出现的值冲突。",
             fix="", level=Level.L3, label="defect_present"),
        dict(id="gold-false-alarm", title="nearest 等距比较逻辑与误报反例", kind=DefectType.LOGIC,
             original=false_source, planted=false_planted, tests=false_tests,
             diff="约定后出现优先，却将 <= 改成 <", answer="第5行 best = values[0] 会修改传入列表，当输入 [1,3] 时会改变原列表。应该改为 best = values.copy()[0] 来修复输入被修改的问题。",
             fix="best = values.copy()[0]", level=Level.L0, label="no_defect"),
    ]


def main():
    settings = Settings.from_env()
    if settings.use_mock_llm():
        raise RuntimeError("验收必须使用真实模型")
    directory = Path("/app/data/live_evaluation") / time.strftime("%Y%m%d-%H%M%S")
    directory.mkdir(parents=True, exist_ok=False)
    print("OUTPUT=" + str(directory), flush=True)
    router = build_router(settings)
    session = None
    results = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "model_routes": router.summary()["model_routes"], "cost_known": False,
               "cost_note": "单价未核实，cost_cny=0是未估价，不能视为免费或金额预算已达标",
               "method": "同一固定代码、同一学生回答、同一本题证据；有参考组使用主判例、匹配雷型规则和正确代码反例，对照组全部移除。temperature=0；每组一次，无统计显著性。"}
    try:
        if "--fixed-only" not in sys.argv:
            rag = build_retriever(settings)
            session = Session(settings=settings, router=router, retriever=rag, probe=PurePythonProbe())
            handle = session.open(default_specs(3), session_id="live-generated")
            generated = {"accepted": len(handle.runs), "rejected": handle.rejected,
                         "items": [to_dict(r.item) for r in handle.runs], "trace": session.trace}
            save(directory, "generated.json", generated)
            save(directory, "model_calls.json", router.audit)
            print("GENERATED=" + json.dumps({"accepted": len(handle.runs), "rejected": handle.rejected}), flush=True)
            script_answers = ["我怀疑空输入的边界处理有问题，还不能给出具体反例。",
                              "第1行函数中，当输入有两个与 target 等距的候选时，返回值可能与约定冲突。我还没给出具体修复。",
                              "目前没有发现确定的缺陷。"]
            for index, run in enumerate(list(handle.runs)):
                answer = StudentAnswer(script_answers[index], cited_evidence_ids=run.item.evidence_ids[:1])
                for turn in range(run.target_rounds):
                    session.submit(handle, run.item.item_id, answer)
                    save(directory, "model_calls.json", router.audit)
                    print("ROUND=%s/%d" % (run.item.item_id, turn + 1), flush=True)
            report = session.settle(handle)
            generated.update(report=to_dict(report), report_fallback=session.reporter.fallback_used,
                             runs=[to_dict(r) for r in handle.runs], rag=rag.summary(), trace=session.trace)
            results["generated"] = {"accepted": len(handle.runs), "rejected": handle.rejected,
                                    "calls": report.calls, "stages": dict(report.stage_calls),
                                    "report_fallback": session.reporter.fallback_used}
            save(directory, "generated.json", generated)
            print("SESSION=" + json.dumps(results["generated"]), flush=True)

        fixed_rag = build_retriever(settings)
        fixed_items = []
        raw_fixtures = fixtures()
        probe = PurePythonProbe()
        for row in raw_fixtures:
            a, b = probe.verify_pair(row["original"], row["planted"], row["tests"])
            if not a.ok or b.ok or b.timed_out:
                raise RuntimeError("固定标注样本行为验证失败: " + row["id"] + a.detail + b.detail)
            doc_id = "doc_" + row["id"]
            fixed_rag.index(doc_id, row["original"], language="python")
            ids = tuple(c.evidence_id for c in fixed_rag.retrieve(row["title"], top_k=3, doc_id=doc_id))
            primary_query = as_query(row["title"], row["kind"].value, "python")
            defect_query = as_query(row["diff"], row["kind"].value, "python")
            cases = fixed_rag.prepare_cases(
                primary_query, alternate_queries=(defect_query,)
            )
            auxiliary = fixed_rag.prepare_auxiliary(
                " ".join((primary_query, defect_query)),
                expected_code={
                    DefectType.API_MISUSE: "R01", DefectType.BOUNDARY: "R02",
                    DefectType.PERF: "R03", DefectType.LOGIC: "R06",
                    DefectType.TYPE_CONFUSION: "R05",
                }.get(row["kind"], ""),
            )
            item = DefectItem(row["id"], "python", row["kind"], row["title"], row["original"], row["planted"],
                              row["diff"], ids, row["level"], verified=True, verify_source="PurePythonProbe",
                              case_evidence_ids=cases,
                              pattern_evidence_ids=auxiliary["patterns"],
                              negative_evidence_ids=auxiliary["negative_code"],
                              test_source=row["tests"])
            fixed_items.append(item)
        fixed_rag.seal()
        fixed_view = SealedView(fixed_rag)
        save(directory, "fixed_samples.json", [{**to_dict(item), "student": row["answer"],
             "gold_label": row["label"], "gold_level": row["level"].value,
             "test_results": [to_dict(v) for v in probe.verify_pair(item.original, item.planted, item.test_source)]}
             for item, row in zip(fixed_items, raw_fixtures)])
        # 完整召回文本与分数留在教师验收目录，便于独立审阅相关性。
        save(directory, "retrieved_cases.json", [{"item_id": item.item_id,
             "cases": [{**to_dict(fixed_rag.fetch(eid)), "score": fixed_rag._case_chunks[eid].score,
                         "role": fixed_rag._origins[eid].get("role", "other")}
                       for eid in (item.case_evidence_ids + item.pattern_evidence_ids + item.negative_evidence_ids)]}
                      for item in fixed_items])
        comparisons = []
        for index, (item, gold) in enumerate(zip(fixed_items, raw_fixtures)):
            for use_references in ([True, False] if index % 2 == 0 else [False, True]):
                treatment = "with_references" if use_references else "without_references"
                variant = item if use_references else replace(
                    item,
                    case_evidence_ids=(),
                    pattern_evidence_ids=(),
                    negative_evidence_ids=(),
                )
                answer = StudentAnswer(gold["answer"], cited_evidence_ids=item.evidence_ids[:1], proposed_fix=gold["fix"])
                run = ItemRun(variant, 1, (RoundRecord(1, answer, ""),))
                call_start = len(router.audit)
                # 直接单次复核诊断不属于正常会话的自动升级策略，不混入12次预算。
                challenge = Adversary(router).challenge(variant, answer, 1, budget=CallBudget(), view=fixed_view)
                judge = Judge(router, settings)
                prediction = judge._escalate(item.item_id, [run], [extract_row(variant, run.rounds)], CallBudget(), fixed_view)
                calls = router.audit[call_start:]
                result = {"item_id": item.item_id, "condition": treatment,
                          "gold_label": gold["label"], "gold_level": gold["level"].value,
                          "prediction": prediction, "challenge": challenge,
                          "label_correct": bool(prediction and prediction["label"] == gold["label"]),
                          "level_correct": bool(prediction and prediction["level"] == gold["level"].value),
                          "case_count": len(variant.case_evidence_ids),
                          "pattern_count": len(getattr(variant, "pattern_evidence_ids", ())),
                          "negative_count": len(getattr(variant, "negative_evidence_ids", ())),
                          "calls": len(calls), "tokens_in": sum(c.get("tokens_in", 0) for c in calls),
                          "tokens_out": sum(c.get("tokens_out", 0) for c in calls),
                          "latency_ms": sum(c["latency_ms"] for c in calls),
                          "judge_prompt_sha256": hashlib.sha256(calls[-1]["messages"][-1]["content"].encode()).hexdigest()}
                comparisons.append(result)
                save(directory, "comparison.json", comparisons)
                save(directory, "model_calls.json", router.audit)
                print("COMPARE=" + json.dumps({k: result[k] for k in ("item_id", "condition", "label_correct", "level_correct")}), flush=True)
        with (directory / "comparison.csv").open("w", newline="", encoding="utf-8-sig") as file:
            fields = [k for k in comparisons[0] if k not in {"prediction", "challenge"}]
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows({k: v for k, v in row.items() if k in fields} for row in comparisons)
        results["comparison"] = {t: {"n": 3, "label_correct": sum(r["label_correct"] for r in comparisons if r["condition"] == t),
                                     "level_correct": sum(r["level_correct"] for r in comparisons if r["condition"] == t),
                                     "tokens_in": sum(r["tokens_in"] for r in comparisons if r["condition"] == t),
                                     "tokens_out": sum(r["tokens_out"] for r in comparisons if r["condition"] == t),
                                     "latency_ms": sum(r["latency_ms"] for r in comparisons if r["condition"] == t)}
                                 for t in ("with_references", "without_references")}
        results["fixed_rag"] = fixed_rag.summary()
        results["status"] = "complete"
    except Exception as exc:
        results.update(status="failed", error=type(exc).__name__, detail=str(exc))
        print("FAILED=" + type(exc).__name__ + ": " + str(exc), flush=True)
        raise
    finally:
        results["actual_calls"] = len(router.audit)
        results["failed_calls"] = sum(c["status"] != "ok" for c in router.audit)
        results["tokens_in"] = sum(c.get("tokens_in", 0) for c in router.audit)
        results["tokens_out"] = sum(c.get("tokens_out", 0) for c in router.audit)
        results["case_consuming_calls"] = sum(bool(c.get("case_evidence_ids")) for c in router.audit)
        save(directory, "model_calls.json", router.audit)
        if session is not None:
            save(directory, "preparation_trace.json", session.trace)
        save(directory, "summary.json", results)
        print("SUMMARY=" + json.dumps(results, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
