# -*- coding: utf-8 -*-
"""验证"只在口语问法启用重排"这条闸门：22 题 + 30 题一起看

两套题集共用同一份候选（22 题用 rerank_cache.json；30 题重新取一次并落缓存）。
"""
import os
import csv, importlib, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
mod = importlib.import_module("rerank_apply")

SAG = os.environ.get("ZJ_SAG_BIN", "<请配置 SAG 命令行路径 sag.exe>")
CORPUS = os.path.join(ROOT, '01_knowledge_base_v2_sag')
DICT = os.path.join(ROOT, '03_评测/03_同义词扩展词典.json')
CACHE22 = os.path.join(os.environ.get("ZJ_TOOLS_DIR", "<请配置外部工具目录 _tools>"), 'rerank_cache.json')
CACHE30 = os.path.join(os.environ.get("ZJ_TOOLS_DIR", "<请配置外部工具目录 _tools>"), 'rerank_cache_30.json')
Q30 = os.path.join(ROOT, '03_评测/03_固定问题集.csv')
OUT = os.path.join(ROOT, '04_结果')
TOPK = 15
EXPAND_K = 2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rerank_apply import doc_id_of, doc_type_of


def load_dict():
    d = json.load(open(DICT, encoding="utf-8"))
    return {k: v for k, v in d.items() if not k.startswith("_") and isinstance(v, list)}


def expand(query, dic):
    terms = []
    for k, vals in dic.items():
        if k in query:
            for v in vals:
                if v not in terms and v not in query:
                    terms.append(v)
    return (query + " " + " ".join(terms[:EXPAND_K])).strip()


def sag(q, timeout=240):
    p = subprocess.run([SAG, q, CORPUS, "--json", "-m", str(TOPK), "--timeout", str(timeout)],
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


def build30(dic):
    if os.path.exists(CACHE30):
        return json.load(open(CACHE30, encoding="utf-8"))
    rows = list(csv.DictReader(open(Q30, encoding="utf-8-sig")))
    out = []
    for i, r in enumerate(rows, 1):
        out.append({"style": r["style"], "query": r["query"],
                    "used": expand(r["query"], dic),
                    "gold": [g.strip() for g in r["gold_ids"].split("|") if g.strip()],
                    "items": sag(expand(r["query"], dic))})
        print("  缓存30 %d/%d" % (i, len(rows)), flush=True)
    json.dump(out, open(CACHE30, "w", encoding="utf-8"), ensure_ascii=False)
    return out


def stat(ranks):
    n = len(ranks)
    return {"n": n,
            "hit@1": 100 * sum(1 for r in ranks if r == 1) / n,
            "hit@3": 100 * sum(1 for r in ranks if r and r <= 3) / n,
            "hit@5": 100 * sum(1 for r in ranks if r and r <= 5) / n,
            "mrr": sum(1.0 / r if r else 0.0 for r in ranks) / n}


def rk(ids, gold):
    return next((k for k, d in enumerate(ids, 1) if d in gold), None)


def main():
    dic = load_dict()
    cfg = mod.load_cfg()
    data22 = [{"style": "原话版", **x} for x in json.load(open(CACHE22, encoding="utf-8"))]
    data30 = build30(dic)

    groups = {"22题原话": data22,
              "30题术语": [x for x in data30 if x["style"] == "术语版"],
              "30题口语": [x for x in data30 if x["style"] == "口语版"]}

    def order(x):
        return [it["id"] for it in x["items"]]

    def full(x):
        return mod.rerank(x["used"], x["items"], cfg, scorer="bigram", alpha=cfg["alpha"])

    def gate(x):
        return mod.rerank_smart(x["used"], x["items"], cfg)

    print("\n%-10s | %-16s | H1 | H3 | H5 | MRR" % ("题集", "方案"))
    rows_out = []
    for gname, data in groups.items():
        for sname, fn in (("原始顺序", order), ("扩词后原顺序", order),
                          ("扩词+重排(全程)", full), ("扩词+重排(闸门)", gate)):
            if sname == "原始顺序" and gname != "22题原话":
                continue    # 30 题的 A 组已在 15c 报过，这里只对比 B / 全程 / 闸门
            ranks = [rk(fn(x), x["gold"]) for x in data]
            s = stat(ranks)
            rows_out.append({"题集": gname, "方案": sname, **{k: round(v, 1) if isinstance(v, float) else v
                                                             for k, v in s.items()}})
            print("%-10s | %-16s | %.1f | %.1f | %.1f | %.3f" %
                  (gname, sname, s["hit@1"], s["hit@3"], s["hit@5"], s["mrr"]))

    with open(os.path.join(OUT, "15d_重排闸门验证_汇总.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
