# -*- coding: utf-8 -*-
"""给 24 批酸价表补三列：数据性质、占企标 3.0 的比例、受控判定。

原有列一字不改；新增列写在末尾；同时留一份原始文件备份。
"""
import os
import csv, os, shutil, sys

SRC = os.path.join(ROOT, '04_结果/13_牛油方砖酸价_24批次.csv')
BAK = SRC.replace(".csv", ".bak_20261106.csv")
DST = os.path.join(ROOT, '04_结果/13_牛油方砖酸价_24批次_带数据性质.csv')

LIMIT_QY = 3.0     # Q/NHTY 0019S-2019 油（膏）包
LIMIT_RAW = 2.5    # GB 10146-2015 牛油原料

if not os.path.exists(BAK):
    shutil.copyfile(SRC, BAK)
    print("备份 ->", BAK)

rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
out = []
for r in rows:
    v = float(r["酸价_mg_g"])
    pct_qy = v / LIMIT_QY * 100
    pct_raw = v / LIMIT_RAW * 100
    if pct_qy >= 80:
        lvl = "高位（达企标限值 80% 以上）"
    elif pct_qy >= 65:
        lvl = "偏高"
    else:
        lvl = "正常区间"
    r["数据性质"] = "按文献区间生成的模拟数据（非企业真实台账）"
    r["占企标3.0比例"] = "%.1f%%" % pct_qy
    r["占原料国标2.5比例"] = "%.1f%%" % pct_raw
    r["限值位置"] = lvl
    out.append(r)

fields = list(rows[0].keys()) + ["数据性质", "占企标3.0比例", "占原料国标2.5比例", "限值位置"]
with open(DST, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(out)

hi = [r for r in out if r["限值位置"].startswith("高位")]
print("写出 ->", DST, len(out), "行")
print("高位批次：", ", ".join("%s=%s" % (r["批次编号"], r["酸价_mg_g"]) for r in hi))
print("最高值占企标 3.0：", max(r["占企标3.0比例"] for r in out))
