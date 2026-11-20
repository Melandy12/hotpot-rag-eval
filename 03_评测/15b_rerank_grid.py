# -*- coding: utf-8 -*-
"""重排权重网格搜索（候选只取一次，缓存在本地 JSON）

在 S4 意图路由的框架下扫三组参数：
  alpha  —— 本地相关度 vs 原始名次的混合比例
  w_std  —— 判定/限值类问题给标准卡的权重
  w_case —— 现象/原因类问题给案例卡的权重
  w_doc  —— 方法/指标类问题给文献卡的权重
目标：在 Hit@3 不掉的前提下把 Hit@1 抬上去。
"""
import os
import csv, itertools, json, os, re, subprocess, sys, time

SAG = os.environ.get("ZJ_SAG_BIN", "<请配置 SAG 命令行路径 sag.exe>")
CORPUS = os.path.join(ROOT, '01_knowledge_base_v2_sag')
QSET = os.path.join(ROOT, '03_评测/14_师傅原话问题集.csv')
DICT = os.path.join(ROOT, '03_评测/03_同义词扩展词典.json')
OUT_DIR = os.path.join(ROOT, '04_结果')
CACHE = os.path.join(os.environ.get("ZJ_TOOLS_DIR", "<请配置外部工具目录 _tools>"), 'rerank_cache.json')
TOPK = 15
EXPAND_K = 2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rerank_apply import doc_id_of, doc_type_of

STD_WORDS = ["国标", "限值", "标准", "卡的是", "超标", "判定", "合规", "出厂检验"]
CASE_WORDS = ["咋回事", "为什么", "为啥", "是不是", "原因", "正常吗", "怎么回事", "退回去"]
DOC_WORDS = ["验收", "指标", "怎么", "哪些", "方法", "检测", "工艺", "留样", "控制"]


def load_dict():
    with open(DICT, encoding="utf-8") as f:
        d = json.load(f)
    return {k: v for k, v in d.items() if not k.startswith("_") and isinstance(v, list)}


def expand(query, dic):
    terms = []
    for k, vals in dic.items():
        if k in query:
            for v in vals:
                if v not in terms and v not in query:
                    terms.append(v)
    return (query + " " + " ".join(terms[:EXPAND_K])).strip(), terms[:EXPAND_K]


def sag(query, timeout=240):
    p = subprocess.run([SAG, query, CORPUS, "--json", "-m", str(TOPK), "--timeout", str(timeout)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout + 30)
    out = []
    if p.returncode == 0 and p.stdout.strip():
        try:
            for item in json.loads(p.stdout).get("results", []):
                path = item.get("path", "")
                if ".sag-converted" in path:
                    continue
                did = doc_id_of(path)
                m = bool(did)
                if not m:
                    continue
                if any(x["id"] == did for x in out):
                    continue
                out.append({"id": did, "type": doc_type_of(did),
                            "heading": item.get("heading", "") or "",
                            "content": item.get("content", "") or ""})
        except Exception as e:
            print("  解析失败 %s" % e)
    return out


def bigrams(text):
    t = re.sub(r"[\s\W_]+", "", text.lower())
    return set(t[i:i + 2] for i in range(len(t) - 1)) if len(t) > 1 else set(t)


def local_score(query, item):
    qb = bigrams(query)
    if not qb:
        return 0.0
    hcov = len(bigrams(item["heading"]) & qb) / len(qb)
    ccov = len(bigrams(item["content"]) & qb) / len(qb)
    return 0.30 * hcov + 0.70 * ccov


def intent_of(query):
    if any(w in query for w in STD_WORDS):
        return "std"
    if any(w in query for w in CASE_WORDS):
        return "case"
    if any(w in query for w in DOC_WORDS):
        return "doc"
    return "mix"


def build_cache(rows, dic):
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    out = []
    for i, r in enumerate(rows, 1):
        used, terms = expand(r["query"], dic)
        out.append({"query": r["query"], "used": used, "terms": terms,
                    "gold": [g.strip() for g in r["gold_ids"].split("|") if g.strip()],
                    "items": sag(used)})
        print("  缓存 %d/%d" % (i, len(rows)), flush=True)
    json.dump(out, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return out


def evaluate(cache, alpha, weights_for):
    ranks = []
    for rb in cache:
        items = rb["items"]
        if not items:
            ranks.append(None)
            continue
        qt = intent_of(rb["query"])
        w = weights_for(qt)
        scored = []
        for i, it in enumerate(items):
            s = local_score(rb["used"], it)
            base = 1.0 / (1.0 + 0.08 * i)
            scored.append(((s * alpha + base * (1 - alpha)) * w.get(it["type"], 1.0), i, it["id"]))
        scored.sort(key=lambda x: (-x[0], x[1]))
        ids = [x[2] for x in scored]
        rank = None
        for idx, did in enumerate(ids, 1):
            if did in rb["gold"]:
                rank = idx
                break
        ranks.append(rank)
    n = len(ranks)
    return {"hit@1": 100 * sum(1 for r in ranks if r == 1) / n,
            "hit@3": 100 * sum(1 for r in ranks if r and r <= 3) / n,
            "hit@5": 100 * sum(1 for r in ranks if r and r <= 5) / n,
            "mrr": sum(1.0 / r if r else 0.0 for r in ranks) / n}


def main():
    dic = load_dict()
    rows = list(csv.DictReader(open(QSET, encoding="utf-8-sig")))
    cache = build_cache(rows, dic)
    print("候选已缓存 %d 题" % len(cache))

    base = {"CASE": 1.0, "DOC": 1.0, "GB": 1.0, "QY": 1.0, "TS": 1.0}
    b = evaluate(cache, 0.75, lambda qt: base)
    print("基准（不重排权重）: H1 %.1f H3 %.1f H5 %.1f MRR %.3f" %
          (b["hit@1"], b["hit@3"], b["hit@5"], b["mrr"]))

    best = None
    grid = []
    for alpha in (0.5, 0.65, 0.75, 0.85):
        for w_std, w_case, w_doc in itertools.product(
                (1.0, 1.1, 1.2, 1.3), (1.0, 1.1, 1.2, 1.3), (1.0, 1.1, 1.2)):
            def wf(qt, a=w_std, c=w_case, d=w_doc):
                if qt == "std":
                    return {"CASE": 1 / a * 0.85, "DOC": 1 / a * 0.95, "GB": a, "QY": a, "TS": 1.0}
                if qt == "case":
                    return {"CASE": c, "DOC": 1 / c * 0.95, "GB": 1 / c * 0.9, "QY": 1 / c * 0.9, "TS": 1.0}
                if qt == "doc":
                    return {"CASE": 1 / d * 0.9, "DOC": d, "GB": 1.0, "QY": 1.0, "TS": 1.0}
                return base
            r = evaluate(cache, alpha, wf)
            grid.append({"alpha": alpha, "w_std": w_std, "w_case": w_case, "w_doc": w_doc,
                         "hit@1": round(r["hit@1"], 1), "hit@3": round(r["hit@3"], 1),
                         "hit@5": round(r["hit@5"], 1), "mrr": round(r["mrr"], 3)})
            if r["hit@3"] >= b["hit@3"] and (best is None or r["hit@1"] > best["hit@1"]) :
                best = dict(grid[-1])

    grid.sort(key=lambda x: (-x["hit@1"], -x["hit@3"]))
    print("\nTop 10（按 Hit@1 排）:")
    for g in grid[:10]:
        print("  " + json.dumps(g, ensure_ascii=False))
    print("\nHit@3 不掉的约束下最佳:", json.dumps(best, ensure_ascii=False) if best else "无")

    with open(os.path.join(OUT_DIR, "15_重排权重网格.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(grid[0].keys()))
        w.writeheader()
        w.writerows(grid)
    print("网格结果 ->", os.path.join(OUT_DIR, "15_重排权重网格.csv"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
