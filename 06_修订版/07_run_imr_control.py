# -*- coding: utf-8 -*-
"""I-MR 控制图：数据到位后一条命令出控制限与判异结果。

用法：
    python 07_run_imr_control.py --file <填好的SPC数据模板.csv> --product PRD-01 --indicator 酸价 --timepoint 0

输入列（与 05_SPC数据模板.csv 一致）：
    产品编码 / 批次号 / 生产日期 / 检测时点_天 / 指标名称 / 实测值 / 单位 / 判定限值

输出：
    · 中心线 X̄、平均移动极差 MR̄、σ 估计、UCL / LCL
    · 逐点偏差与 Nelson 判异规则命中情况
    · 结果 CSV，可直接进报告

注意：n < 20 时控制限为初始估计，会在输出中明确标注；n < 8 时拒绝计算。
"""
import argparse, csv, os

D2 = 1.128      # n=2 时 d2
E2 = 2.660      # n=2 时 3/d2
D4 = 3.267      # n=2 时 D4（MR 图上控制限）


def load(path, product, indicator, timepoint):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if product and str(r.get("产品编码", "")).strip() != product:
                continue
            if indicator and str(r.get("指标名称", "")).strip() != indicator:
                continue
            tp = str(r.get("检测时点_天", "")).strip()
            if timepoint is not None and tp and tp != str(timepoint):
                continue
            v = str(r.get("实测值", "")).strip()
            if not v:
                continue
            try:
                x = float(v)
            except ValueError:
                continue
            rows.append({"批次": r.get("批次号", ""), "日期": r.get("生产日期", ""), "值": x})
    rows.sort(key=lambda a: (str(a["日期"]), str(a["批次"])))
    return rows


def nelson(xs, xbar, sigma):
    """Nelson 判异规则实用子集：1 / 2 / 3 / 5 / 6。"""
    n = len(xs)
    flags = [[] for _ in range(n)]
    if sigma <= 0:
        return flags
    z = [(x - xbar) / sigma for x in xs]
    for i in range(n):
        if abs(z[i]) > 3:
            flags[i].append("规则1：超出 3σ")
        if i >= 2 and abs(z[i]) > 2 and sum(1 for k in (0, 1, 2) if abs(z[i - k]) > 2) >= 2:
            flags[i].append("规则5：连续3点中2点超 2σ")
        if i >= 4 and abs(z[i]) > 1 and sum(1 for k in range(5) if abs(z[i - k]) > 1) >= 4:
            flags[i].append("规则6：连续5点中4点超 1σ")
    for i in range(8, n):
        seg = xs[i - 8:i + 1]
        if all(v > xbar for v in seg):
            flags[i].append("规则2：连续9点在中心线上方")
        if all(v < xbar for v in seg):
            flags[i].append("规则2：连续9点在中心线下方")
    for i in range(5, n):
        if all(xs[i - 5 + k] < xs[i - 5 + k + 1] for k in range(5)):
            flags[i].append("规则3：连续6点递增")
        if all(xs[i - 5 + k] > xs[i - 5 + k + 1] for k in range(5)):
            flags[i].append("规则3：连续6点递减")
    return flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--product", default="")
    ap.add_argument("--indicator", default="")
    ap.add_argument("--timepoint", default=None, help="只取某个检测时点（0 表示出厂）")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    rows = load(a.file, a.product, a.indicator, a.timepoint)
    n = len(rows)
    print("=" * 70)
    print("I-MR 控制图：%s / %s / 检测时点=%s"
          % (a.product or "全部", a.indicator or "全部", "全部" if a.timepoint is None else a.timepoint))
    print("=" * 70)
    print("有效数据点：%d" % n)
    if n < 8:
        print("✗ 不足 8 个点，无法估计控制限。请先按模板补齐数据。")
        print("  合格数据应满足：同一产品、同一指标、同一检测时点、连续 20~25 个批次。")
        return
    if n < 20:
        print("⚠ 点数 %d < 20，控制限为【初始估计】，报告里必须写明；补足 25 组后重算。" % n)

    xs = [r["值"] for r in rows]
    xbar = sum(xs) / n
    mrs = [abs(xs[i] - xs[i - 1]) for i in range(1, n)]
    mrbar = sum(mrs) / len(mrs)
    sigma = mrbar / D2
    ucl_i, lcl_i = xbar + E2 * mrbar, xbar - E2 * mrbar
    ucl_mr, lcl_mr = D4 * mrbar, 0.0

    print("\n【I 图（单值）】")
    print("  中心线 X̄        = %.3f" % xbar)
    print("  平均移动极差 MR̄  = %.3f" % mrbar)
    print("  σ 估计 = MR̄/d2  = %.3f" % sigma)
    print("  UCL             = %.3f" % ucl_i)
    print("  LCL             = %.3f" % lcl_i)
    print("\n【MR 图（移动极差）】")
    print("  中心线 MR̄       = %.3f" % mrbar)
    print("  UCL             = %.3f  (D4·MR̄, D4=3.267)" % ucl_mr)
    print("  LCL             = %.3f  (D3=0)" % lcl_mr)

    flags = nelson(xs, xbar, sigma)
    hit = sum(1 for f in flags if f)
    print("\n【判异】命中 %d / %d 点" % (hit, n))
    out = []
    for i, r in enumerate(rows):
        mr = "" if i == 0 else "%.3f" % abs(xs[i] - xs[i - 1])
        note = "；".join(flags[i])
        out.append({"序号": i + 1, "批次": r["批次"], "生产日期": r["日期"], "实测值": r["值"],
                    "移动极差MR": mr,
                    "偏离中心线σ数": round((r["值"] - xbar) / sigma, 2) if sigma else "", "判异": note})
        if note:
            print("  #%02d %-14s %8.3f  %s" % (i + 1, r["批次"], r["值"], note))

    dst = a.out or os.path.splitext(a.file)[0] + "_IMR结果.csv"
    with open(dst, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print("\n结果：", dst)
    if not hit:
        print("\n过程未见判异点；若堆积历史数据显示长期趋势，仍需结合趋势图判断。")
    if n < 20:
        print("提示：控制限基于 %d 个点，属初始估计。" % n)


if __name__ == "__main__":
    main()
