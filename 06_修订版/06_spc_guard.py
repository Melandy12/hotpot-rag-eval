# -*- coding: utf-8 -*-
"""SPC 判定 → 知识库检索 → 处置建议（联动演示）

读修订版数据，对时序表每个读数：
  1) 按「判定限值」做 正常 / 预警(≥90%限值) / 超限 判定
  2) 命中预警或超限时，用 BM25 在历史异常案例里检索同产品、同指标的相似案例
  3) 输出该案例的「调查确认的原因」与「采取的措施」

注意：本脚本做的是**限值判定**，不是控制图判异。控制图需要 20~25 个批次的
出厂数据才能估计控制限，时序表只有 3~4 个点，脚本会明确提示这一点。
"""
import os, re, math, csv
from collections import Counter
import openpyxl
import jieba

REV = os.path.join(ROOT, '06_修订版/10.24数据整理_修订版.xlsx')
OUT = os.path.join(ROOT, '06_修订版/06_判定与案例联动结果.csv')

STOP = set("的了和与及或在是有为以其之一个这那怎么什么哪些啥吗呢吧啊也就都还又再更很太请问如何为什么哪个多少")
K1, B = 1.5, 0.75


def toks(s):
    out = []
    for t in jieba.lcut(str(s)):
        t = t.strip()
        if len(t) < 2 or t in STOP or not re.match(r"^[\w\u4e00-\u9fff]+$", t):
            continue
        out.append(t)
    return out


class BM25:
    def __init__(self, docs):
        self.tf = [Counter(d) for d in docs]
        self.dl = [len(d) for d in docs]
        self.df = Counter()
        for c in self.tf:
            for t in c:
                self.df[t] += 1
        self.N = len(docs)
        self.avg = sum(self.dl) / max(self.N, 1) or 1
        self.idf = {t: math.log((self.N - n + 0.5) / (n + 0.5) + 1) for t, n in self.df.items()}

    def search(self, q, k=3):
        q = toks(q)
        sc = []
        for i, c in enumerate(self.tf):
            s = 0.0
            for t in q:
                f = c.get(t, 0)
                if f:
                    s += self.idf[t] * (f * (K1 + 1)) / (f + K1 * (1 - B + B * self.dl[i] / self.avg))
            sc.append((s, i))
        sc.sort(key=lambda x: (-x[0], x[1]))
        return [(i, s) for s, i in sc[:k] if s > 0]


wb = openpyxl.load_workbook(REV, data_only=True)

# ---------- 案例库 ----------
ws_c = wb["历史异常案例"]
case_hdr = [c.value for c in ws_c[1]]
I_CID = case_hdr.index("案例编号")
I_PROD = case_hdr.index("产品及批次")
I_PHEN = case_hdr.index("异常现象")
I_SPC = case_hdr.index("SPC指标表现")
I_CAUSE = case_hdr.index("调查确认的原因")
I_ACT = case_hdr.index("采取的措施")
I_RES = case_hdr.index("措施后的结果")
I_CODE = case_hdr.index("产品编码（建议）")
I_SRC = case_hdr.index("来源记录_修订")

cases = []
for r in ws_c.iter_rows(min_row=2, values_only=True):
    if not r or not r[I_CID]:
        continue
    code = str(r[I_CODE] or "")
    cases.append({
        "cid": r[I_CID], "code": re.findall(r"PRD-\d\d", code)[0] if re.findall(r"PRD-\d\d", code) else "",
        "prod": r[I_PROD], "phen": r[I_PHEN], "spc": r[I_SPC],
        "cause": r[I_CAUSE], "act": r[I_ACT], "res": r[I_RES],
        "src": r[I_SRC] or r[case_hdr.index("来源记录")],
        "text": f"{r[I_PROD]} {r[I_PHEN]} {r[I_SPC]} {r[I_CAUSE]} {r[I_ACT]}",
    })

bm = BM25([toks(c["text"]) for c in cases])

# ---------- 时序 ----------
ws_t = wb["时间序列检测数据"]
hdr_t = [c.value for c in ws_t[1]]
I2 = {k: hdr_t.index(k) for k in ["批次", "产品类型", "储藏温度", "储藏时间", "指标名称", "测量值", "单位", "产品编码", "判定限值"]}
rows = []
for r in ws_t.iter_rows(min_row=2, values_only=True):
    if not r or not r[I2["批次"]]:
        continue
    rows.append({k: r[v] for k, v in I2.items()})

# ---------- 点数自检 ----------
grp = Counter((r["批次"], r["指标名称"]) for r in rows)
print("=" * 74)
print("① 数据自检：控制图可行性")
print("=" * 74)
mx = max(grp.values())
print("  共 %d 个(批次×指标)组合，单组合最多 %d 个点。" % (len(grp), mx))
if mx < 20:
    print("  → 控制限无法估计（需 20~25 点）。本轮改走【限值判定】，控制图待补足批次数据后再启用。")

# ---------- 判定 + 检索 ----------
print()
print("=" * 74)
print("② 逐读数判定 + 相似历史案例")
print("=" * 74)
out = []
for r in rows:
    try:
        val = float(r["测量值"])
    except (TypeError, ValueError):
        continue
    limit = r["判定限值"]
    try:
        lim = float(limit)
    except (TypeError, ValueError):
        lim = None

    if lim is None:
        verdict, ratio = "限值未核定（不判定）", ""
    elif val > lim:
        verdict, ratio = "超限", "%.0f%% 限值" % (val / lim * 100)
    elif val >= 0.9 * lim:
        verdict, ratio = "预警", "%.0f%% 限值" % (val / lim * 100)
    else:
        verdict, ratio = "正常", "%.0f%% 限值" % (val / lim * 100)

    rec = {"批次": r["批次"], "产品编码": r["产品编码"], "产品": r["产品类型"],
           "指标": r["指标名称"], "储藏时间": r["储藏时间"], "测量值": val,
           "判定限值": limit, "判定": verdict, "占限值比": ratio,
           "相似案例": "", "该案例原因": "", "该案例措施": ""}

    if verdict in ("超限", "预警"):
        q = f"{r['产品类型']} {r['指标名称']} 超标 异常"
        hits = bm.search(q, 3)
        # 优先同产品编码的案例
        same = [(i, s) for i, s in hits if cases[i]["code"] == re.findall(r"PRD-\d\d", str(r["产品编码"]))[0]] if re.findall(r"PRD-\d\d", str(r["产品编码"])) else []
        pick = same[0] if same else (hits[0] if hits else None)
        if pick:
            c = cases[pick[0]]
            rec["相似案例"] = f"{c['cid']}（{c['phen']}）"
            rec["该案例原因"] = c["cause"]
            rec["该案例措施"] = c["act"]
    out.append(rec)

# ---------- 控制台输出 ----------
print("%-13s %-7s %-11s %-5s %-6s %-6s %s" % ("批次", "产品", "指标", "时点", "读数", "判定", "联动案例"))
print("-" * 74)
for rec in out:
    print("%-13s %-7s %-11s %-5s %-6s %-6s %s" % (
        rec["批次"], rec["产品编码"], rec["指标"], rec["储藏时间"] if "天" in str(rec["储藏时间"]) else str(rec["储藏时间"]) + "天",
        ("%.2f" % rec["测量值"]) if rec["测量值"] is not None else "", rec["判定"],
        rec["相似案例"][:38] if rec["相似案例"] else "—"))

hit = [r for r in out if r["判定"] in ("超限", "预警")]
print()
print("=" * 74)
print("③ 命中 %d 条（超限/预警），逐条给出知识库里的原因与措施" % len(hit))
print("=" * 74)
for r in hit:
    print("\n▌ %s ｜ %s %s ｜ 储藏%s ｜ 读数 %.2f（限值 %s）→ %s，%s"
          % (r["批次"], r["产品编码"], r["指标"], r["储藏时间"], r["测量值"], r["判定限值"], r["判定"], r["占限值比"]))
    if r["相似案例"]:
        print("   知识库相似案例：%s" % r["相似案例"])
        print("   原因：%s" % r["该案例原因"])
        print("   措施：%s" % r["该案例措施"])
    else:
        print("   知识库中未检索到相似案例（需补录该类异常的处置记录）")

with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)
print("\n结果表：", OUT)
