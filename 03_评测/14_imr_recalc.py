# -*- coding: utf-8 -*-
"""24 批次酸价 I-MR：三种基线策略对比 + 月度分层"""
import csv
import os

CSV_IN = os.path.join(ROOT, '04_结果/13_牛油方砖酸价_24批次.csv')
OUT = os.path.join(ROOT, '04_结果')

rows = list(csv.DictReader(open(CSV_IN, encoding="utf-8-sig")))
x = [float(r["酸价_mg_g"]) for r in rows]
dates = [r["生产日期"] for r in rows]
ids = [r["批次编号"] for r in rows]
n = len(x)


def imr(vals, dense_mr=True):
    """dense_mr=True: 仅对相邻且都在列的成对点算 MR"""
    keep = [i for i, v in enumerate(vals) if v is not None]
    v = [vals[i] for i in keep]
    mean = sum(v) / len(v)
    pairs = []
    for a, b in zip(keep, keep[1:]):
        if b - a == 1:
            pairs.append(abs(vals[b] - vals[a]))
    mrbar = sum(pairs) / len(pairs) if pairs else 0.0
    sigma = mrbar / 1.128
    return {
        "n_used": len(v),
        "n_mr": len(pairs),
        "mean": mean,
        "mrbar": mrbar,
        "sigma": sigma,
        "ucl": mean + 2.66 * mrbar,
        "lcl": mean - 2.66 * mrbar,
        "mr_ucl": 3.267 * mrbar,
    }


# A 全部 24 点
A = imr(list(x))
# B 剔除 010(2.3) 与 020(2.4)
mask_b = [v if i not in (9, 19) else None for i, v in enumerate(x)]
B = imr(mask_b)
# C 剔除 009~021 整段（2/18 ~ 5/1 的异常窗口）
mask_c = [v if not (8 <= i <= 20) else None for i, v in enumerate(x)]
C = imr(mask_c)

strategies = [("A 全部24点", A), ("B 剔除010/020", B), ("C 剔除009-021整段", C)]

print("=== 三种基线 ===")
for name, s in strategies:
    over = [ids[i] for i in range(n) if x[i] > s["ucl"] or x[i] < s["lcl"]]
    print("%-18s n=%2d MRn=%2d 均值=%.3f MRbar=%.3f sigma=%.3f UCL=%.3f LCL=%.3f MR-UCL=%.3f 越界=%d %s"
          % (name, s["n_used"], s["n_mr"], s["mean"], s["mrbar"], s["sigma"],
             s["ucl"], s["lcl"], s["mr_ucl"], len(over), ",".join(over)))

# 输出 A/B/C 对每点的判定
out = []
for i in range(n):
    d = {"批次编号": ids[i], "生产日期": dates[i], "酸价": x[i]}
    for name, s in strategies:
        d[name] = "超" if (x[i] > s["ucl"] or x[i] < s["lcl"]) else "否"
    out.append(d)
csv1 = os.path.join(OUT, "13_IMR基线三策略对比.csv")
with open(csv1, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)

# 月度分层
month = {}
for i in range(n):
    m = dates[i][:7]
    month.setdefault(m, []).append(x[i])
print("\n=== 月度分层 ===")
csv2 = os.path.join(OUT, "13_酸价月度分层.csv")
with open(csv2, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["月份", "批次数", "均值", "最小值", "最大值", "对GB10146_2.5的占比"])
    for m in sorted(month):
        vs = month[m]
        avg = sum(vs) / len(vs)
        print("%s n=%d 均值=%.2f 区间=[%.1f, %.1f] 峰值对2.5=%.0f%%"
              % (m, len(vs), avg, min(vs), max(vs), max(vs) / 2.5 * 100))
        w.writerow([m, len(vs), round(avg, 3), min(vs), max(vs), "%.0f%%" % (max(vs) / 2.5 * 100)])

# 合规判定
print("\n=== 合规判定（GB 10146-2015 酸价<=2.5）===")
bad = [(ids[i], x[i]) for i in range(n) if x[i] > 2.5]
print("超2.5的批次:", bad if bad else "无")
print(">=2.2（限值88%以上）的批次:", [(ids[i], x[i]) for i in range(n) if x[i] >= 2.2])
