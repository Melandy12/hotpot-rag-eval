# -*- coding: utf-8 -*-
"""从 10.24数据整理(1).xlsx 构建 RAG 知识库语料（Markdown 分片 + manifest）。"""
import os, re, csv, sys
import openpyxl

SRC = os.environ.get("ZJ_SOURCE_XLSX", "<请配置原始数据 xlsx 路径>")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
KB_DIR = os.path.join(ROOT, "01_knowledge_base")
REG_DIR = os.path.join(ROOT, "02_国标待导入")

for d in (KB_DIR, REG_DIR):
    os.makedirs(d, exist_ok=True)

def safe(name, maxlen=40):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", str(name)).strip()
    s = re.sub(r"_+", "_", s)
    return s[:maxlen]

wb = openpyxl.load_workbook(SRC, data_only=True)
manifest = []

# ---------- 1. 文献索引 ----------
ws = wb["火锅底料知识文档索引"]
rows = list(ws.iter_rows(min_row=2, values_only=True))
for r in rows:
    if not r or not r[0]:
        continue
    doc_id, title, src, year, core, link = [("" if v is None else str(v).strip()) for v in (list(r) + [""] * 6)[:6]]
    body = f"""# {title}

- 文档编号：{doc_id}
- 来源：{src}
- 年份/期数：{year}
- 原文链接：{link}

## 核心提取内容（供AI检索）

{core}
"""
    fn = os.path.join(KB_DIR, f"{doc_id}_{safe(title)}.md")
    with open(fn, "w", encoding="utf-8") as f:
        f.write(body)
    manifest.append({"chunk_id": doc_id, "type": "文献摘要", "title": title,
                     "source": src, "file": os.path.basename(fn), "text": f"{title}。{src}。{core}"})

# ---------- 2. 历史异常案例 ----------
ws = wb["历史异常案例"]
hdr = [c.value for c in ws[1]]
rows = list(ws.iter_rows(min_row=2, values_only=True))
for r in rows:
    if not r or not r[0]:
        continue
    vals = [("" if v is None else str(v).strip()) for v in r]
    vals += [""] * (10 - len(vals))
    body = f"""# {vals[0]}｜{vals[1]}｜{vals[2]}

| 字段 | 内容 |
|---|---|
| 案例编号 | {vals[0]} |
| 产品及批次 | {vals[1]} |
| 异常现象 | {vals[2]} |
| 发生时间及储藏条件 | {vals[3]} |
| SPC指标表现 | {vals[4]} |
| 调查确认的原因 | {vals[5]} |
| 采取的措施 | {vals[6]} |
| 措施后的结果 | {vals[7]} |
| 来源记录 | {vals[8]} |
| 原因状态 | {vals[9]} |
"""
    fn = os.path.join(KB_DIR, f"{vals[0]}_{safe(vals[1] + '_' + vals[2])}.md")
    with open(fn, "w", encoding="utf-8") as f:
        f.write(body)
    text = "；".join([x for x in vals[1:] if x])
    manifest.append({"chunk_id": vals[0], "type": "异常案例", "title": f"{vals[1]}｜{vals[2]}",
                     "source": vals[8], "file": os.path.basename(fn), "text": text})

# ---------- 3. 时间序列（按批次聚合） ----------
ws = wb["时间序列检测数据"]
rows = list(ws.iter_rows(min_row=2, values_only=True))
batches = {}
for r in rows:
    if not r or not r[0]:
        continue
    d = str(r[0])[:10]
    batch, prod, temp, days, ind, val, unit = [("" if r[i] is None else str(r[i]).strip()) for i in range(1, 8)]
    batches.setdefault((batch, prod, temp), {}).setdefault(ind, []).append((days, val, unit))

for (batch, prod, temp), inds in batches.items():
    lines = [f"# {batch}｜{prod}｜储藏 {temp}", "", "## 逐时点检测值", "", "| 指标 | 储藏时间 | 测量值 | 单位 |", "|---|---|---|---|"]
    plain = []
    for ind, pts in inds.items():
        for days, val, unit in pts:
            lines.append(f"| {ind} | {days} | {val} | {unit} |")
        plain.append(f"{ind}：" + " → ".join(f"{v}{u}@{d}" for d, v, u in pts))
    fn = os.path.join(KB_DIR, f"TS_{batch}_{safe(prod)}.md")
    with open(fn, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    manifest.append({"chunk_id": f"TS_{batch}", "type": "检测时序", "title": f"{batch}｜{prod}｜{temp}",
                     "source": "10.24数据整理(1).xlsx", "file": os.path.basename(fn), "text": f"{batch} {prod} 储藏温度{temp} " + " ".join(plain)})

# ---------- 4. manifest ----------
with open(os.path.join(KB_DIR, "_manifest.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["chunk_id", "type", "title", "source", "file", "text"])
    w.writeheader()
    w.writerows(manifest)

print("chunks =", len(manifest))
from collections import Counter
print(Counter(m["type"] for m in manifest))
