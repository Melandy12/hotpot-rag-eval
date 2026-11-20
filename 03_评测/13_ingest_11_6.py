# -*- coding: utf-8 -*-
"""把 11.6 资料整理.docx 的三块内容结构化：
1) 24 批次牛油方砖底料酸价 -> CSV + I-MR 控制图计算
2) 40 条师傅原话 -> 真实问法集 CSV
3) 水分限值 -> 参考表 CSV（标注来源不可核）
"""
import csv
import os
import re

SRC = os.path.join(os.environ.get("ZJ_TOOLS_DIR", "<请配置外部工具目录 _tools>"), 'tmp_read_11_6.txt')
OUT = os.path.join(ROOT, '04_结果')
os.makedirs(OUT, exist_ok=True)

with open(SRC, "r", encoding="utf-8") as f:
    lines = [ln.strip() for ln in f.readlines()]

# ---------- 1) 酸价数据 ----------
rows = []
for ln in lines:
    m = re.match(r"^(\d+)\s+(BATCH-2026-(\d{3}))\s+(\d{4}-\d{2}-\d{2})\s+([\d.]+)\s+(\S+)\s+(.+)$", ln)
    if m:
        rows.append({
            "序号": int(m.group(1)),
            "批次编号": m.group(2),
            "生产日期": m.group(4),
            "酸价_mg_g": float(m.group(5)),
            "原判定": m.group(6),
            "原备注": m.group(7).strip(),
        })

print("解析到酸价批次:", len(rows))
csv1 = os.path.join(OUT, "13_牛油方砖酸价_24批次.csv")
with open(csv1, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

# I-MR
x = [r["酸价_mg_g"] for r in rows]
n = len(x)
mean = sum(x) / n
mr = [abs(x[i] - x[i - 1]) for i in range(1, n)]
mrbar = sum(mr) / len(mr)
sigma = mrbar / 1.128
ucl = mean + 2.66 * mrbar
lcl = mean - 2.66 * mrbar
mr_ucl = 3.267 * mrbar
print("n=%d 均值=%.3f MRbar=%.3f sigma=%.3f I-UCL=%.3f I-LCL=%.3f MR-UCL=%.3f" % (n, mean, mrbar, sigma, ucl, lcl, mr_ucl))

out_rows = []
runs_up = runs_dn = 0
for i, r in enumerate(rows):
    d = mr[i - 1] if i > 0 else None
    out_rows.append({
        "序号": r["序号"], "批次编号": r["批次编号"], "生产日期": r["生产日期"],
        "酸价": r["酸价_mg_g"],
        "I值": round(r["酸价_mg_g"] - mean, 3),
        "移动极差MR": "" if d is None else round(d, 3),
        "超I控制限": "是" if (r["酸价_mg_g"] > ucl or r["酸价_mg_g"] < lcl) else "否",
        "超MR控制限": "" if d is None else ("是" if d > mr_ucl else "否"),
        "原备注": r["原备注"],
    })
csv2 = os.path.join(OUT, "13_牛油方砖酸价_IMR控制图.csv")
with open(csv2, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
    w.writeheader()
    w.writerows(out_rows)

# 连续上升/下降链（7 点规则）
longest_up = longest_dn = cur_up = cur_dn = 0
for i in range(1, n):
    if x[i] > x[i - 1]:
        cur_up += 1
        cur_dn = 0
    elif x[i] < x[i - 1]:
        cur_dn += 1
        cur_up = 0
    else:
        cur_up = cur_dn = 0
    longest_up = max(longest_up, cur_up)
    longest_dn = max(longest_dn, cur_dn)

print("最长连续上升=%d 最长连续下降=%d" % (longest_up, longest_dn))
print("超I限点数=%d 超MR限点数=%d" % (
    sum(1 for r in out_rows if r["超I控制限"] == "是"),
    sum(1 for r in out_rows if r["超MR控制限"] == "是")))

# ---------- 2) 师傅原话 ----------
def is_quote(ln):
    return ln.startswith("\u201c") and ln.endswith("\u201d")

quotes = [ln.strip("\u201c\u201d") for ln in lines if is_quote(ln)]
print("解析到原话:", len(quotes))
csv3 = os.path.join(OUT, "13_师傅原话_真实问法集.csv")
with open(csv3, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["序号", "师傅原话（现场真实表述）", "类型"])
    for i, q in enumerate(quotes, 1):
        typ = "问句" if ("？" in q or "?" in q or q.endswith("吗")) else "经验陈述"
        w.writerow([i, q, typ])
