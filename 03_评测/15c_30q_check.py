# -*- coding: utf-8 -*-
"""防过拟合验证：把 22 题上定下的重排方案拿到 30 题固定集（术语 / 口语两版）上跑

对比三组：
  A 原始顺序           —— SAG 直接给的
  B M1 扩词 + 原始顺序 —— 现有评测口径
  C M1 扩词 + 重排     —— 待验证的方案
分术语版 / 口语版分别统计。
"""
import os
import csv, importlib, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
rerank = importlib.import_module("rerank_apply")

SAG = os.environ.get("ZJ_SAG_BIN", "<请配置 SAG 命令行路径 sag.exe>")
CORPUS = os.path.join(ROOT, '01_knowledge_base_v2_sag')
QSET = os.path.join(ROOT, '03_评测/03_固定问题集.csv')
DICT = os.path.join(ROOT, '03_评测/03_同义词扩展词典.json')
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


def stat(ranks):
    n = len(ranks)
    return {"n": n,
            "hit@1": "%.1f%%" % (100 * sum(1 for r in ranks if r == 1) / n),
            "hit@3": "%.1f%%" % (100 * sum(1 for r in ranks if r and r <= 3) / n),
            "hit@5": "%.1f%%" % (100 * sum(1 for r in ranks if r and r <= 5) / n),
            "mrr": "%.3f" % (sum(1.0 / r if r else 0.0 for r in ranks) / n)}


def main():
    dic = load_dict()
    rows = list(csv.DictReader(open(QSET, encoding="utf-8-sig")))
    cfg = rerank.load_cfg()
    got = {"术语版": {"A": [], "B": [], "C": []}, "口语版": {"A": [], "B": [], "C": []}}
    detail = []
    print("30 题 × 1 次取候选（TOP15），分 A/B/C 三组算")
    for i, r in enumerate(rows, 1):
        style = r["style"]
        gold = [g.strip() for g in r["gold_ids"].split("|") if g.strip()]
        raw_items = sag(r["query"])                      # A：原始
        exp_items = sag(expand(r["query"], dic))         # B/C：扩词
        idsA = [it["id"] for it in raw_items]
        idsB = [it["id"] for it in exp_items]
        idsC = rerank.rerank(expand(r["query"], dic), exp_items, cfg, scorer="bigram", alpha=cfg["alpha"])
        def rk(ids):
            return next((k for k, d in enumerate(ids, 1) if d in gold), None)
        for key, ids in (("A", idsA), ("B", idsB), ("C", idsC)):
            got[style][key].append(rk(ids))
        detail.append({"style": style, "intent": r["intent"], "query": r["query"],
                       "A": rk(idsA) or "", "B": rk(idsB) or "", "C": rk(idsC) or "",
                       "intent_detected": rerank.intent_of(expand(r["query"], dic), cfg)})
        print("  %2d/%d %s A=%s B=%s C=%s" % (i, len(rows), style,
                                              detail[-1]["A"], detail[-1]["B"], detail[-1]["C"]), flush=True)

    summ = []
    for style in ("术语版", "口语版"):
        for key, name in (("A", "A_原始顺序"), ("B", "B_扩词后原顺序"), ("C", "C_扩词后重排")):
            s = stat(got[style][key])
            s.update({"style": style, "方案": name})
            summ.append(s)
            print(json.dumps(s, ensure_ascii=False))

    with open(os.path.join(OUT, "15c_30题防过拟合验证_汇总.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["style", "方案", "n", "hit@1", "hit@3", "hit@5", "mrr"])
        w.writeheader()
        w.writerows(summ)
    with open(os.path.join(OUT, "15c_30题防过拟合验证_逐题.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(detail[0].keys()))
        w.writeheader()
        w.writerows(detail)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
