# -*- coding: utf-8 -*-
"""30 题固定集整批跑本地问答链路（SAG 检索 → 重排 → 7B 生成）

用法: python 12b_answer_batch_30.py
输出: 04_结果\12b_本地问答链路_30题整批.md
"""
import csv
import importlib.util
import io
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
spec = importlib.util.spec_from_file_location(
    "la", os.path.join(HERE, "11_local_answer.py"))
la = importlib.util.module_from_spec(spec)
spec.loader.exec_module(la)

QS_CSV = os.path.join(ROOT, '03_评测/03_固定问题集.csv')
OUT = os.path.join(ROOT, '04_结果/12b_本地问答链路_30题整批.md')

rows = []
with open(QS_CSV, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows.append(r)

out = io.StringIO()
out.write("# 本地问答链路 · 30 题固定集整批\n\n")
out.write("链路：SAG Wiki 本地检索（BM25 + Jev 词法决策）→ M1 扩词 K=2 → 15 候选重排 → 前 5 做证据 → "
          "qwen25-7b-local 生成。语料 120 片。\n\n")
out.write("说明：本表只做**答案质量抽查**，指标口径（Hit@1/3/5、MRR）以 09 号脚本为准，两者不混用。\n\n")

ok = 0
t0 = time.time()
for i, r in enumerate(rows, 1):
    q = r["query"]
    try:
        items, ans = la.ask(q)
        hit = any(it["id"] in r["gold_ids"] for it in items)
        ok += 1 if hit else 0
        out.write("## %d. 问：%s\n\n" % (i, q))
        out.write("- 类型：%s / %s　gold：%s\n" % (r["intent"], r["style"], r["gold_ids"]))
        out.write("- 前五是否命中 gold：**%s**\n\n" % ("是" if hit else "否"))
        out.write("**命中证据**\n\n")
        for j, it in enumerate(items, 1):
            out.write("%d. [%s] %s\n" % (j, it["id"], it["heading"]))
        out.write("\n**回答**\n\n%s\n\n---\n\n" % ans.strip())
        sys.stdout.write("%d/30 done  hit=%s  %.1fs\n" % (i, hit, time.time() - t0))
        sys.stdout.flush()
    except Exception as e:  # noqa: BLE001
        out.write("## %d. 问：%s\n\n**失败**：%s\n\n---\n\n" % (i, q, e))
        sys.stdout.write("%d/30 FAILED %s\n" % (i, e))

with open(OUT, "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("\n前五命中 gold %d/30，总耗时 %.0f 秒，结果 %s" % (ok, time.time() - t0, OUT))
