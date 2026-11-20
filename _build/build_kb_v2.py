# -*- coding: utf-8 -*-
"""用【修订版】数据重建知识库语料（v2）。

与 v1 的差别：
  1. 案例卡片的「来源记录」改用 `来源记录_修订`（v1 用的是原始列，带 22 条错引）
  2. 案例卡片补 `产品编码` 与 `限值口径` 字段，方便按产品检索
  3. 时序卡片补 `判定限值`，让"酸价 2.5 / 过氧化值 0.25"这类限值能被检索到
输出到 01_knowledge_base_v2，与 v1 并存，便于对照。
"""
import os, re, csv
import openpyxl

SRC = os.path.join(ROOT, '06_修订版/10.24数据整理_修订版.xlsx')
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
KB_DIR = os.path.join(ROOT, "01_knowledge_base_v2")
os.makedirs(KB_DIR, exist_ok=True)


def safe(name, maxlen=40):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", str(name)).strip()
    s = re.sub(r"_+", "_", s)
    return s[:maxlen]


def s(v):
    return "" if v is None else str(v).strip()


wb = openpyxl.load_workbook(SRC, data_only=True)
manifest = []

# ---------- 1. 文献索引 ----------
ws = wb["火锅底料知识文档索引"]
for r in ws.iter_rows(min_row=2, values_only=True):
    if not r or not r[0]:
        continue
    doc_id, title, src, year, core, link = [s(v) for v in (list(r) + [""] * 6)[:6]]
    body = f"""# {title}

- 文档编号：{doc_id}
- 来源：{src}
- 年份/期数：{year}
- 原文链接：{link}

## 核心提取内容（供AI检索）

{core}
"""
    fn = os.path.join(KB_DIR, f"{doc_id}_{safe(title)}.md")
    open(fn, "w", encoding="utf-8").write(body)
    manifest.append({"chunk_id": doc_id, "type": "文献摘要", "title": title,
                     "source": src, "file": os.path.basename(fn), "text": f"{title}。{src}。{core}"})

# ---------- 2. 历史异常案例 ----------
ws = wb["历史异常案例"]
hdr = [s(c.value) for c in ws[1]]
I = {name: hdr.index(name) for name in
     ["案例编号", "产品及批次", "异常现象", "发生时间及储藏条件", "SPC指标表现",
      "调查确认的原因", "采取的措施", "措施后的结果", "来源记录", "原因状态",
      "产品编码（建议）", "来源记录_修订", "修订说明"]}

for r in ws.iter_rows(min_row=2, values_only=True):
    if not r or not r[0]:
        continue
    vals = [s(v) for v in r]
    cid = vals[I["案例编号"]]
    src_fixed = vals[I["来源记录_修订"]] or vals[I["来源记录"]]
    body = f"""# {vals[I['案例编号']]}｜{vals[I['产品及批次']]}｜{vals[I['异常现象']]}

| 字段 | 内容 |
|---|---|
| 案例编号 | {cid} |
| 产品编码 | {vals[I['产品编码（建议）']]} |
| 产品及批次 | {vals[I['产品及批次']]} |
| 异常现象 | {vals[I['异常现象']]} |
| 发生时间及储藏条件 | {vals[I['发生时间及储藏条件']]} |
| SPC指标表现 | {vals[I['SPC指标表现']]} |
| 调查确认的原因 | {vals[I['调查确认的原因']]} |
| 采取的措施 | {vals[I['采取的措施']]} |
| 措施后的结果 | {vals[I['措施后的结果']]} |
| 来源记录 | {src_fixed} |
| 原因状态 | {vals[I['原因状态']]} |
"""
    fn = os.path.join(KB_DIR, f"{cid}_{safe(vals[I['产品及批次']] + '_' + vals[I['异常现象']])}.md")
    open(fn, "w", encoding="utf-8").write(body)
    text = "；".join([x for x in [vals[I['产品编码（建议）']], vals[I['产品及批次']], vals[I['异常现象']],
                                 vals[I['SPC指标表现']], vals[I['调查确认的原因']], vals[I['采取的措施']],
                                 vals[I['措施后的结果']], src_fixed] if x])
    manifest.append({"chunk_id": cid, "type": "异常案例", "title": f"{vals[I['产品及批次']]}｜{vals[I['异常现象']]}",
                     "source": src_fixed, "file": os.path.basename(fn), "text": text})

# ---------- 3. 时间序列 ----------
ws = wb["时间序列检测数据"]
hdr = [s(c.value) for c in ws[1]]
J = {name: hdr.index(name) for name in
     ["日期", "批次", "产品类型", "储藏温度", "储藏时间", "指标名称", "测量值", "单位",
      "产品编码", "判定限值", "限值来源"]}
batches = {}
for r in ws.iter_rows(min_row=2, values_only=True):
    if not r or not r[J["批次"]]:
        continue
    key = (s(r[J["批次"]]), s(r[J["产品类型"]]), s(r[J["储藏温度"]]), s(r[J["产品编码"]]))
    batches.setdefault(key, {"限制": [], "点": {}})
    ind = s(r[J["指标名称"]])
    batches[key]["点"].setdefault(ind, []).append(
        (s(r[J["储藏时间"]]), s(r[J["测量值"]]), s(r[J["单位"]])))
    lim = s(r[J["判定限值"]])
    if lim and ind not in batches[key].get("已记指标", set()):
        batches[key].setdefault("已记指标", set()).add(ind)
        batches[key]["限制"].append(f"{ind} {lim} {s(r[J['单位']])}（{s(r[J['限值来源']])}）")

for (batch, prod, temp, code), d in batches.items():
    lines = [f"# {batch}｜{prod}｜{code}｜储藏 {temp}", "",
             "## 判定限值", ""]
    for x in d["限制"]:
        lines.append(f"- {x}")
    lines += ["", "## 逐时点检测值", "", "| 指标 | 储藏时间 | 测量值 | 单位 |", "|---|---|---|---|"]
    plain = []
    for ind, pts in d["点"].items():
        for days, val, unit in pts:
            lines.append(f"| {ind} | {days} | {val} | {unit} |")
        plain.append(f"{ind}：" + " → ".join(f"{v}{u}@{t}" for t, v, u in pts))
    fn = os.path.join(KB_DIR, f"TS_{batch}_{safe(prod)}.md")
    open(fn, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    manifest.append({"chunk_id": f"TS_{batch}", "type": "检测时序",
                     "title": f"{batch}｜{prod}｜{code}｜{temp}",
                     "source": "10.24数据整理_修订版.xlsx",
                     "file": os.path.basename(fn),
                     "text": f"{batch} {prod} {code} 储藏温度{temp} " + " ".join(plain)
                             + " 判定限值 " + " ".join(d["限制"])})

# ---------- 4. manifest ----------
with open(os.path.join(KB_DIR, "_manifest.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["chunk_id", "type", "title", "source", "file", "text"])
    w.writeheader()
    w.writerows(manifest)

from collections import Counter
print("chunks =", len(manifest))
print(Counter(m["type"] for m in manifest))
print("KB =", KB_DIR)
