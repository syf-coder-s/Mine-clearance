"""从 RAGFlow 现有文档名构造 30 条检索基准，只测召回，不调用模型。

文档名中的 Rxx 是库内已有雷型标记，作为检索 gold；不修改库、不上传内容。
这是检索相关性基准，不等同于人工判级 gold。
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from mineclearance.config import Settings
from mineclearance.rag.ragflow import RagflowRAG, rerank_cases

QUERY_VARIANTS = {
    "R01": ("接口参数调用错误", "API 参数与状态码", "分页接口协议使用", "调用参数类型", "接口错误处理"),
    "R02": ("边界空输入越界", "等距候选比较", "单元素极端值", "循环边界少走多走", "空列表返回值"),
    "R03": ("复杂度循环性能", "重复计算超时", "递归缺少记忆化", "数据范围与效率", "无限循环风险"),
    "R04": ("初始化状态变量", "哨兵值未重置", "返回值状态错误", "变量初始值", "状态标记缺失"),
    "R05": ("类型混淆转换", "字符串整数类型", "空值 None 类型", "类型检查", "参数类型错误"),
    "R06": ("等价语义偏移", "方向比较符语义", "代码风格还是正确性", "逻辑方向改变", "重构语义不一致"),
}


def get_documents(settings):
    documents = []
    for page in (1, 2):
        path = f"/api/v1/datasets/{settings.ragflow_dataset_id}/documents?page={page}&page_size=100"
        request = urllib.request.Request(
            settings.ragflow_base_url.rstrip("/") + path,
            headers={"Authorization": "Bearer " + settings.ragflow_api_key},
        )
        with urllib.request.urlopen(request, timeout=settings.ragflow_timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
        data = body.get("data") or {}
        documents.extend(data.get("docs") or [])
        if len(documents) >= int(data.get("total") or len(documents)):
            break
    return documents


def main():
    settings = Settings.from_env()
    rag = RagflowRAG(settings)
    documents = get_documents(settings)
    by_code = defaultdict(list)
    for document in documents:
        match = re.search(r"(?:^|/)\s*(R\d{2})[_-]", str(document.get("name", "")), re.I)
        if match:
            by_code[match.group(1).upper()].append(document)
    # 每类最多五条，按文档名稳定排序；最终不超过30条。
    selected = []
    for code in sorted(by_code):
        selected.extend(sorted(by_code[code], key=lambda d: str(d.get("name", "")))[:5])
    selected = selected[:30]
    if len(selected) < 30:
        raise RuntimeError("判例库中可解析 Rxx 文档不足30条: %d" % len(selected))

    rows = []
    per_code_index = Counter()
    aggregate_stats = {}
    for document in selected:
        name = str(document["name"])
        expected = re.search(r"(?:^|/)\s*(R\d{2})[_-]", name, re.I).group(1).upper()
        index = per_code_index[expected]
        per_code_index[expected] += 1
        query = QUERY_VARIANTS[expected][index % len(QUERY_VARIANTS[expected])]
        candidates = rag.retrieve(query, top_k=settings.case_candidate_k)
        reranked = rerank_cases(query, candidates, settings.case_top_k, stats=aggregate_stats)
        raw_top = candidates[: settings.case_top_k]
        rows.append({
            "document": name,
            "expected_code": expected,
            "query": query,
            "raw_top3_codes": [re.search(r"雷型:\s*(R\d{2})", c.text, re.I).group(1).upper()
                               if re.search(r"雷型:\s*(R\d{2})", c.text, re.I) else "UNKNOWN" for c in raw_top],
            "reranked_top3_codes": [re.search(r"雷型:\s*(R\d{2})", c.text, re.I).group(1).upper()
                                    if re.search(r"雷型:\s*(R\d{2})", c.text, re.I) else "UNKNOWN" for c in reranked],
            "raw_hit_at_3": any(expected == x for x in [re.search(r"雷型:\s*(R\d{2})", c.text, re.I).group(1).upper()
                                                       if re.search(r"雷型:\s*(R\d{2})", c.text, re.I) else "UNKNOWN" for c in raw_top]),
            "reranked_hit_at_3": any(expected == x for x in [re.search(r"雷型:\s*(R\d{2})", c.text, re.I).group(1).upper()
                                                            if re.search(r"雷型:\s*(R\d{2})", c.text, re.I) else "UNKNOWN" for c in reranked]),
        })
    result = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "dataset_id": settings.ragflow_dataset_id,
        "document_count": len(documents),
        "sample_count": len(rows),
        "gold_source": "Rxx label parsed from existing RAGFlow document names; retrieval benchmark only",
        "raw_hit_at_3": sum(row["raw_hit_at_3"] for row in rows),
        "reranked_hit_at_3": sum(row["reranked_hit_at_3"] for row in rows),
        "by_expected_code": {
            code: {
                "n": sum(row["expected_code"] == code for row in rows),
                "raw_hit_at_3": sum(row["expected_code"] == code and row["raw_hit_at_3"] for row in rows),
                "reranked_hit_at_3": sum(row["expected_code"] == code and row["reranked_hit_at_3"] for row in rows),
            }
            for code in sorted({row["expected_code"] for row in rows})
        },
        "rerank_stats": aggregate_stats,
        "rows": rows,
    }
    output = Path("/app/data/rag_retrieval_evaluation.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
