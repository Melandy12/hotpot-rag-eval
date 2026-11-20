# -*- coding: utf-8 -*-
"""用师傅原话题集重跑 SAG2 检索评测（M0 原句 / M1 总是扩展），K=2"""
import csv
import json
import os
import re
import subprocess
import sys
import time

SAG = os.environ.get("ZJ_SAG_BIN", "<请配置 SAG 命令行路径 sag.exe>")
CORPUS = os.path.join(ROOT, '01_knowledge_base_v2_sag')
QSET = os.path.join(ROOT, '03_评测/14_师傅原话问题集.csv')
DICT = os.path.join(ROOT, '03_评测/03_同义词扩展词典.json')
OUT_DIR = os.path.join(ROOT, '04_结果')
TOPK = 10
EXPAND_K = 2
DOCID = re.compile(r"^((?:DOC|CASE|TS_BATCH|GB)-[\w\-]+?)(?=_|\.md|$)")


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
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout + 30)
    ids = []
    if p.returncode == 0 and p.stdout.strip():
        try:
            data = json.loads(p.stdout)
            for item in data.get("results", []):
                if ".sag-converted" in item.get("path", ""):
                    continue
                m = DOCID.match(os.path.basename(item.get("path", "")))
                if m and m.group(1) not in ids:
                    ids.append(m.group(1))
        except Exception as e:
            print("  解析失败 %s" % e)
    return ids


def run_mode(mode, rows, dic):
    out = []
    for i, r in enumerate(rows, 1):
        gold = [g.strip() for g in r["gold_ids"].split("|") if g.strip()]
        q0 = r["query"]
        used = q0
        ids = sag(q0)
        terms = []
        if mode == "M1":
            used, terms = expand(q0, dic)
            if terms:
                ids = sag(used)
        rank = None
        for idx, did in enumerate(ids, 1):
            if did in gold:
                rank = idx
                break
        out.append({"mode": mode, "intent": r["intent"], "query": q0,
                    "retrieval_query": used, "扩展词": "|".join(terms),
                    "rank": rank or "", "hit@1": 1 if rank == 1 else 0,
                    "hit@3": 1 if rank and rank <= 3 else 0,
                    "hit@5": 1 if rank and rank <= 5 else 0,
                    "rr": 1.0 / rank if rank else 0.0,
                    "zero_recall": 1 if not ids else 0,
                    "top5": "|".join(ids[:5])})
        print("  %s %2d/%d rank=%s 扩展=%s" % (mode, i, len(rows), rank, terms), flush=True)
    return out


def main():
    dic = load_dict()
    rows = list(csv.DictReader(open(QSET, encoding="utf-8-sig")))
    print("题集 %d 条" % len(rows))
    t0 = time.time()
    all_res = []
    summ = []
    for mode in ("M0", "M1"):
        print("== %s ==" % mode, flush=True)
        res = run_mode(mode, rows, dic)
        all_res.extend(res)
        n = len(res)
        summ.append({
            "mode": mode, "n": n,
            "hit@1": "%.1f%%" % (100 * sum(x["hit@1"] for x in res) / n),
            "hit@3": "%.1f%%" % (100 * sum(x["hit@3"] for x in res) / n),
            "hit@5": "%.1f%%" % (100 * sum(x["hit@5"] for x in res) / n),
            "mrr": "%.3f" % (sum(x["rr"] for x in res) / n),
            "零召回": sum(x["zero_recall"] for x in res),
        })

    tag = "14_师傅原话口语评测_K2"
    with open(os.path.join(OUT_DIR, tag + "_汇总.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0].keys()))
        w.writeheader()
        w.writerows(summ)
    with open(os.path.join(OUT_DIR, tag + "_逐题.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_res[0].keys()))
        w.writeheader()
        w.writerows(all_res)

    print("\n== 汇总 ==")
    for s in summ:
        print(json.dumps(s, ensure_ascii=False))
    print("用时 %.1f 秒" % (time.time() - t0))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
