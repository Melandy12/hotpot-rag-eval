# -*- coding: utf-8 -*-
"""抽查：案例「来源记录」引用的文献，与案例内容主题是否真的相关（词项重叠法）。"""
import os
import re, csv
import openpyxl
import jieba

SRC = os.environ.get("ZJ_SOURCE_XLSX", "<请配置原始数据 xlsx 路径>")
OUT = os.path.join(ROOT, '05_数据体检/05_引用内容相关性抽查.csv')
wb = openpyxl.load_workbook(SRC, data_only=True)
ws_d = wb["火锅底料知识文档索引"]
docs = {r[0]: (str(r[1] or ""), str(r[4] or "")) for r in ws_d.iter_rows(min_row=2, values_only=True) if r[0]}
ws_c = wb["历史异常案例"]
cases = [r for r in ws_c.iter_rows(min_row=2, values_only=True) if r[0]]

STOP = set("的了和与及或在是有为以其之一个这那怎么什么哪些啥吗呢吧啊也就都还又再更很太请问如何为什么哪个多少")

def toks(s):
    out = []
    for t in jieba.lcut(s):
        t = t.strip()
        if len(t) < 2 or t in STOP:
            continue
        if not re.match(r"^[\w\u4e00-\u9fff]+$", t):
            continue
        out.append(t)
    return set(out)

rows = []
for c in cases:
    cid, prod, phen, when, spc, cause, act, res, src, status = [("" if v is None else str(v)) for v in c]
    mi = re.findall(r"DOC-(\d{3})", src)
    if not mi:
        continue
    doc_id = "DOC-" + mi[0]
    if doc_id not in docs:
        continue
    dtitle, dsum = docs[doc_id]
    case_t = toks(phen + spc + cause + act)
    doc_t = toks(dtitle + dsum)
    inter = case_t & doc_t
    rate = len(inter) / max(len(case_t), 1)
    rows.append({"案例编号": cid, "引用编号": doc_id, "文献标题": dtitle,
                 "案例要点": (phen + "｜" + spc)[:48],
                 "重叠词": "/".join(sorted(inter))[:60],
                 "重叠率": round(rate, 3),
                 "判定": "疑似不相关" if len(inter) <= 1 else ("弱相关" if rate < 0.15 else "相关")})

with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["案例编号", "引用编号", "文献标题", "案例要点", "重叠词", "重叠率", "判定"])
    w.writeheader()
    w.writerows(rows)

bad = [r for r in rows if r["判定"] == "疑似不相关"]
print("可判定配对 %d 条；疑似不相关 %d 条；弱相关 %d 条；相关 %d 条"
      % (len(rows), len(bad),
         sum(1 for r in rows if r["判定"] == "弱相关"),
         sum(1 for r in rows if r["判定"] == "相关")))
print("\n--- 疑似不相关 ---")
for r in bad:
    print("%s → %s《%s》" % (r["案例编号"], r["引用编号"], r["文献标题"][:34]))
    print("      案例：%s" % r["案例要点"])
    print("      重叠词：%s" % (r["重叠词"] or "（无）"))
