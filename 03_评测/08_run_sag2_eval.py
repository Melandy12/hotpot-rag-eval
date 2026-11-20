# -*- coding: utf-8 -*-
"""
SAG2（SAG Wiki + 本地 Jev 决策服务）评测
1) 建干净语料目录（只放 106 个 .md，剔除 _manifest.csv / README）
2) 重新入索引
3) 用同一 30 题集跑，输出 Hit@1/3/5/10、MRR、零召回
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time

SAG = os.environ.get("ZJ_SAG_BIN", "<请配置 SAG 命令行路径 sag.exe>")
SRC = os.path.join(ROOT, '01_knowledge_base_v2')
CLEAN = os.path.join(ROOT, '01_knowledge_base_v2_sag')
QSET = os.path.join(ROOT, '03_评测/03_固定问题集.csv')
OUT_DIR = os.path.join(ROOT, '04_结果')

TOPK = 10


def sag(*args, timeout=300):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([SAG, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, env=env)
    return p.returncode, p.stdout, p.stderr


def build_clean():
    if os.path.exists(CLEAN):
        shutil.rmtree(CLEAN)
    os.makedirs(CLEAN)
    n = 0
    for f in os.listdir(SRC):
        if f.lower().endswith(".md") and not f.startswith("_"):
            shutil.copyfile(os.path.join(SRC, f), os.path.join(CLEAN, f))
            n += 1
    print("干净语料: %d 个 md" % n)
    return n


DOCID = re.compile(r"^((?:DOC|CASE|TS_BATCH)-[\w\-]+?)(?=_|\.md|$)")


def to_id(path):
    if ".sag-converted" in path:
        return None
    base = os.path.basename(path)
    m = DOCID.match(base)
    return m.group(1) if m else None


def main():
    build_clean()

    print("移除旧索引:", sag("remove", SRC, "--json")[1][:200])
    print("加入干净语料:", sag("add", CLEAN, "--json")[1][:200])

    rows = []
    with open(QSET, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    results = []
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        gold = [g.strip() for g in r["gold_ids"].strip().split("|") if g.strip()]
        rc, out, err = sag(r["query"], CLEAN, "--json", "-m", str(TOPK), "--timeout", "240")
        ids = []
        if rc == 0 and out.strip():
            try:
                data = json.loads(out)
                for item in data.get("results", []):
                    did = to_id(item.get("path", ""))
                    if did and did not in ids:
                        ids.append(did)
            except Exception as e:
                print("解析失败 %s: %s" % (r["query"], e))
        else:
            print("查询失败 rc=%d %s | %s" % (rc, r["query"], (err or "")[:150]))

        rank = None
        for idx, did in enumerate(ids, 1):
            if did in gold:
                rank = idx
                break
        results.append({
            "intent": r["intent"], "style": r["style"], "query": r["query"],
            "gold_ids": r["gold_ids"],
            "top_ids": "|".join(ids),
            "rank": rank if rank else "",
            "hit@1": 1 if rank == 1 else 0,
            "hit@3": 1 if rank and rank <= 3 else 0,
            "hit@5": 1 if rank and rank <= 5 else 0,
            "hit@10": 1 if rank else 0,
            "rr": (1.0 / rank) if rank else 0.0,
            "zero_recall": 1 if not ids else 0,
        })
        print("[%2d/%d] %-6s %-4s rank=%s  (%.1fs)" % (i, len(rows), r["intent"], r["style"],
                                                       rank if rank else "-", time.time() - t0))

    os.makedirs(OUT_DIR, exist_ok=True)
    detail = os.path.join(OUT_DIR, "04_SAG2_逐题结果.csv")
    with open(detail, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    summary = []
    for style in ("术语版", "口语版"):
        sub = [x for x in results if x["style"] == style]
        n = len(sub)
        summary.append({
            "style": style, "n": n,
            "hit@1": "%.1f%%" % (100 * sum(x["hit@1"] for x in sub) / n),
            "hit@3": "%.1f%%" % (100 * sum(x["hit@3"] for x in sub) / n),
            "hit@5": "%.1f%%" % (100 * sum(x["hit@5"] for x in sub) / n),
            "hit@10": "%.1f%%" % (100 * sum(x["hit@10"] for x in sub) / n),
            "mrr": "%.3f" % (sum(x["rr"] for x in sub) / n),
            "zero_recall": sum(x["zero_recall"] for x in sub),
        })
    summ = os.path.join(OUT_DIR, "04_SAG2_汇总.csv")
    with open(summ, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)

    print("\n== 汇总 ==")
    for s in summary:
        print(s)
    print("完成，用时 %.1f 秒" % (time.time() - t0))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
