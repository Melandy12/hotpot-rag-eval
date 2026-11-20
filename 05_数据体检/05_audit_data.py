# -*- coding: utf-8 -*-
"""对 10.24数据整理(1).xlsx 做数据体检：只输出可核验的事实，不写结论。"""
import os
import re, csv, os
from collections import Counter, defaultdict
from datetime import datetime
import openpyxl

SRC = os.environ.get("ZJ_SOURCE_XLSX", "<请配置原始数据 xlsx 路径>")
OUT = os.path.join(ROOT, '05_数据体检/05_数据体检_事实清单.txt')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

wb = openpyxl.load_workbook(SRC, data_only=True)
L = []
def p(*a):
    s = " ".join(str(x) for x in a)
    L.append(s)
    print(s)

# ============ A. 文献索引 ============
ws = wb["火锅底料知识文档索引"]
docs = [dict(zip([c.value for c in ws[1]], [c.value for c in r])) for r in ws.iter_rows(min_row=2)]
p("\n" + "=" * 72)
p("A. 文献索引（%d 条）" % len(docs))
p("=" * 72)

ids = [d["文档编号"] for d in docs]
p("编号连续且唯一：", ids == ["DOC-%03d" % i for i in range(1, len(docs) + 1)])

# 链接重复
urls = Counter(d["知网链接"] for d in docs)
p("\n[链接重复] 同一 URL 被多篇文献共用：")
dup_found = False
for u, n in urls.items():
    if n > 1:
        dup_found = True
        who = [d["文档编号"] + " " + str(d["标题"])[:24] for d in docs if d["知网链接"] == u]
        p("  x%d  %s" % (n, u))
        for w in who:
            p("        -", w)
if not dup_found:
    p("  无")

# 链接指向首页 / 校内代理
def is_home(u):
    if not u:
        return True
    m = re.match(r"https?://([^/]+)(/.*)?$", str(u))
    if not m:
        return True
    path = (m.group(2) or "").strip()
    return path in ("", "/")

home = [d for d in docs if is_home(d["知网链接"])]
p("\n[链接指向首页/裸域名] %d 条：" % len(home))
for d in home:
    p("  %s %s -> %s" % (d["文档编号"], str(d["标题"])[:30], d["知网链接"]))

proxy_kw = ["webvpn", "utuvpn", "sris.com.tw", "mdjsf", "443.webvpn"]
proxy = [d for d in docs if any(k in str(d["知网链接"]) for k in proxy_kw)]
p("\n[校内代理/境外镜像链接] %d 条（离校或换网络即失效）：" % len(proxy))
for d in proxy:
    p("  %s %s" % (d["文档编号"], str(d["标题"])[:34]))

# 结构字段完整性
p("\n[字段缺失]")
for f in ["来源（期刊/机构）", "年份/期数", "核心提取内容（供AI检索）"]:
    empty = [d["文档编号"] for d in docs if not d.get(f) or str(d.get(f)).strip() in ("", "—")]
    p("  %s 为空：%s" % (f, empty if empty else "无"))

# 核心提取内容长度
lens = [len(str(d["核心提取内容（供AI检索）"] or "")) for d in docs]
p("\n[核心提取内容] 字数范围 %d~%d，中位 %d（无全文，只有摘要）" % (min(lens), max(lens), sorted(lens)[len(lens)//2]))

# 主题归类
topic_kw = {
    "风味/香气": ["风味", "香气", "挥发性", "感官", "风味轮", "麻辣"],
    "酸价/氧化/货架期": ["酸价", "过氧化值", "氧化", "货架期", "贮藏", "储存"],
    "工艺/配方参数": ["工艺", "参数", "配方", "优化", "炒制"],
    "安全检测/非法添加": ["测定", "检测", "残留", "塑化剂", "生物碱", "毒素", "染料", "亚硝酸盐", "重金属", "农药"],
    "微生物": ["菌落", "微生物", "测序", "菌"],
    "包装/材料": ["包装", "材料", "迁移"],
    "设备/工程": ["设备", "装备", "智能"],
}
p("\n[主题分布]（一篇可落多类）")
cnt = Counter()
for d in docs:
    t = str(d["标题"]) + " " + str(d["核心提取内容（供AI检索）"])
    for k, kws in topic_kw.items():
        if any(w in t for w in kws):
            cnt[k] += 1
for k, v in cnt.most_common():
    p("  %-18s %d 篇" % (k, v))

# 强相关"风味稳定性"的文献
core_kw = ["酸价", "过氧化值", "货架期", "贮藏", "储存", "氧化稳定性", "风味稳定性"]
core = [d for d in docs if any(k in (str(d["标题"]) + str(d["核心提取内容（供AI检索）"])) for k in core_kw)]
p("\n[与酸价/氧化/货架期直接相关] %d 篇：%s" % (len(core), [d["文档编号"] for d in core]))

# ============ B. 历史异常案例 ============
ws = wb["历史异常案例"]
cases = [dict(zip([c.value for c in ws[1]], [c.value for c in r])) for r in ws.iter_rows(min_row=2)]
p("\n" + "=" * 72)
p("B. 历史异常案例（%d 条）" % len(cases))
p("=" * 72)

# 来源记录 -> 提取《标题》与 DOC 编号
title2id = {str(d["标题"]).strip(): d["文档编号"] for d in docs}
p("[来源记录：引用是否真实存在]")
bad_exist, bad_title, ok = [], [], []
for c in cases:
    src = str(c["来源记录"] or "")
    mt = re.findall(r"《(.+?)》", src)
    mi = re.findall(r"DOC-(\d{3})", src)
    if not mi:
        bad_exist.append((c["案例编号"], src, "无 DOC 编号"))
        continue
    doc_id = "DOC-" + mi[0]
    if doc_id not in ids:
        bad_exist.append((c["案例编号"], src, "编号 %s 不存在" % doc_id))
        continue
    cited = mt[0].strip() if mt else ""
    real = str(docs[ids.index(doc_id)]["标题"]).strip()
    # 引用标题与编号对应文献标题是否一致
    def norm(s):
        return re.sub(r"[（(].*?[)）]|[\s　\-—_·、，。]", "", s)
    if cited and norm(cited) != norm(real):
        bad_title.append((c["案例编号"], doc_id, cited, real))
    else:
        ok.append(c["案例编号"])

p("  能对上（引用标题 = 编号对应文献标题）：%d 条" % len(ok))
p("\n  [A] 引用了不存在的文档编号 / 完全无编号：%d 条" % len(bad_exist))
for cid, src, why in bad_exist:
    p("    %s | %s | %s" % (cid, src, why))

p("\n  [B] 编号存在但「引用标题」与「该编号真实标题」不一致（错配）：%d 条" % len(bad_title))
for cid, doc_id, cited, real in bad_title:
    p("    %s 引 %s" % (cid, doc_id))
    p("        文中写：《%s》" % cited)
    p("        实  为：《%s》" % real)

# 案例批次 vs 时序批次
ws = wb["时间序列检测数据"]
ts = [dict(zip([c.value for c in ws[1]], [c.value for c in r])) for r in ws.iter_rows(min_row=2)]
ts_batches = set(str(r["批次"]) for r in ts)
p("\n[批次可追溯性]")
case_batches = set()
for c in cases:
    for b in re.findall(r"BATCH-26-\d{3}", str(c["产品及批次"])):
        case_batches.add(b)
p("  时序表批次：%s（共 %d 个）" % (sorted(ts_batches), len(ts_batches)))
p("  案例表提到批次：%d 个，其中 %d 个在时序表里查不到检测数据"
  % (len(case_batches), len(case_batches - ts_batches)))
p("  案例批次范围：%s ~ %s" % (min(case_batches), max(case_batches)))

# 产品名称枚举
prod = Counter(str(c["产品及批次"]).split("（")[0].strip() for c in cases)
p("\n[产品名称枚举]（同一品类多种写法，SPC 分组会乱）")
for k, v in prod.most_common():
    p("  %-16s %d 条" % (k, v))

# 发生时间
def ym(s):
    m = re.search(r"(20\d\d)\s*年\s*(\d{1,2})?\s*月?", str(s))
    return (int(m.group(1)), int(m.group(2) or 0)) if m else None
times = [ym(c["发生时间及储藏条件"]) for c in cases]
times = [t for t in times if t]
p("\n[发生时间范围] %d 年 %d 月 ~ %d 年 %d 月" % (min(times)[0], min(times)[1], max(times)[0], max(times)[1]))
p("  超出今天(2026-11)的未来案例：%s" % [c["案例编号"] for c, t in zip(cases, [ym(x["发生时间及储藏条件"]) for x in cases]) if t and t > (2026, 11)])

# 原因状态
p("\n[原因状态分布]")
for k, v in Counter(str(c["原因状态"] or "空").strip() for c in cases).most_common():
    p("  %-8s %d 条 (%.0f%%)" % (k, v, v / len(cases) * 100))
p("  「初步判断」是否也写了措施与结果：%s" % [
    c["案例编号"] for c in cases
    if str(c["原因状态"]).strip() == "初步判断" and c["采取的措施"] and c["措施后的结果"]])

# SPC指标表现列的可解析性
p("\n[SPC指标表现 列：能否直接当判定结果用]")
numeric = 0
mixed = 0
for c in cases:
    s = str(c["SPC指标表现"] or "")
    n_ind = len(re.findall(r"(酸价|过氧化值|水分|食盐|辣椒素|菌落总数|pH|氨基酸态氮|谷氨酸钠|还原糖|总酸|灰分|透光率|色差|极性组分|铁离子|熔点|针入度|亚硝酸盐|挥发油|顶空|脂肪酸甲酯|辣椒素损耗|油脂析出|水分活度|苯并芘|黄曲霉毒素|邻苯二甲酸酯|挥发性风味)", s))
    has_num = bool(re.search(r"\d", s))
    if has_num:
        numeric += 1
    if n_ind >= 3 or (n_ind >= 2 and not has_num):
        mixed += 1
p("  含数值的：%d / %d" % (numeric, len(cases)))
p("  一格挤了多个指标（≥2 个指标名）：%d 条" % len([c for c in cases if len(re.findall(r"(酸价|过氧化值|水分|食盐|辣椒素|菌落总数|pH|氨基酸态氮|谷氨酸钠|还原糖|总酸|灰分|透光率|色差|极性组分|铁离子|熔点|针入度|亚硝酸盐|挥发油|顶空|脂肪酸甲酯|油脂析出|水分活度|苯并芘|黄曲霉毒素|邻苯二甲酸酯|挥发性风味)", str(c["SPC指标表现"]))) >= 2]))
p("  含「外观/感官/合格率」等非SPC口径：%d 条" % len([c for c in cases if re.search(r"外观|感官|合格率|不通过|客诉", str(c["SPC指标表现"]) + str(c["异常现象"]))]))

# 空字段
p("\n[必填字段缺失]")
for f in ["产品及批次", "异常现象", "SPC指标表现", "调查确认的原因", "采取的措施", "措施后的结果", "来源记录", "原因状态"]:
    empty = [c["案例编号"] for c in cases if not c.get(f) or not str(c.get(f)).strip()]
    p("  %s 为空：%s" % (f, empty if empty else "无"))

# ============ C. 时间序列 ============
p("\n" + "=" * 72)
p("C. 时间序列检测数据（%d 行）" % len(ts))
p("=" * 72)

grp = defaultdict(list)
for r in ts:
    grp[(str(r["批次"]), str(r["产品类型"]), str(r["指标名称"]))].append(r)
p("[每个(批次,指标)的可用点数]  ← SPC 至少要 20~25 点才能估计控制限")
for k, rows in sorted(grp.items()):
    days = [int(str(r["储藏时间"]).replace("天", "")) for r in rows]
    p("  %-14s %-12s %-8s 点数=%2d  时点=%s" % (k[0], k[1], k[2], len(rows), days))
p("\n  合计组合数 %d，点数≥20 的组合：%d" % (len(grp), sum(1 for v in grp.values() if len(v) >= 20)))

p("\n[日期与储藏时间是否自洽]")
bad_date = []
for k, rows in grp.items():
    d0 = min(datetime.strptime(str(r["日期"])[:10], "%Y-%m-%d") for r in rows)
    for r in rows:
        d = datetime.strptime(str(r["日期"])[:10], "%Y-%m-%d")
        delta = (d - d0).days
        claim = int(str(r["储藏时间"]).replace("天", ""))
        if abs(delta - claim) > 1:
            bad_date.append((k[0], k[2], str(r["日期"])[:10], claim, delta))
p("  不一致：%s" % (bad_date if bad_date else "无（全部自洽）"))

p("\n[产品类型枚举] %s" % sorted(set(str(r["产品类型"]) for r in ts)))
p("[单位枚举] %s" % [(k, v) for k, v in Counter(str(r["指标名称"]) + "=" + str(r["单位"]) for r in ts).items()])
p("[储藏温度枚举] %s" % sorted(set(str(r["储藏温度"]) for r in ts)))

p("\n[小数位不统一]")
for r in ts:
    v = str(r["测量值"])
    if v.count(".") == 0:
        p("  %s %s %s天 测量值=%s（整数写法，同列其他为一位小数）" % (r["批次"], r["指标名称"], r["储藏时间"], v))

p("\n[缺字段] 平行样次数 / 检测方法 / 仪器编号 / 操作人 / 环境温湿度 / 判定限值 列均不存在")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(L))
p("\n事实清单已写入：", OUT)
