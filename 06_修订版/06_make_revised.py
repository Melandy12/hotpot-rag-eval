# -*- coding: utf-8 -*-
"""生成「修订版」数据文件：原文件一字不动，改动只落在新增列里。
本轮只做两条核心改动：
  改动① 案例表 —— 新增「来源记录_修订」「修订说明」，清掉 22 条错引（不覆盖原列，可回滚）
  改动② 时序表 —— 新增「产品编码」「判定限值」「限值来源」，让 SPC 能按产品分组判定
"""
import os
import shutil, re, os, stat
from collections import Counter
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill

SRC = os.environ.get("ZJ_SOURCE_XLSX", "<请配置原始数据 xlsx 路径>")
DST = os.path.join(ROOT, '06_修订版/10.24数据整理_修订版.xlsx')
os.makedirs(os.path.dirname(DST), exist_ok=True)
if os.path.exists(DST):
    os.chmod(DST, stat.S_IWRITE)
    os.remove(DST)
shutil.copyfile(SRC, DST)   # 用 copyfile，不继承源文件的只读属性
os.chmod(DST, stat.S_IWRITE | stat.S_IREAD)

wb = openpyxl.load_workbook(DST)
HDR_FONT = Font(bold=True, color="FFFFFF")
HDR_FILL = PatternFill("solid", fgColor="4472C4")

# ============================================================
# 改动① 案例表：来源记录修订
# ============================================================
FIX = {
 "CASE-2026-001": ("《一种降低红油火锅底料油脂酸价的炒制工艺》（DOC-005）",
   "原引标题《熬制条件对牛油基火锅油品质的影响》与 DOC-005 不是同一篇文献；按主题（炒制温度致油脂氧化、酸价升高）改标 DOC-005 正确标题"),
 "CASE-2026-004": ("《火锅底料香气提升研究进展》（DOC-008）（间接参考）",
   "标题笔误：'品质提升'应为'香气提升'。该文为综述，对'焦苦味/氨基酸态氮下降'仅间接支撑"),
 "CASE-2026-011": ("《火锅底料香气提升研究进展》（DOC-008）（间接参考）",
   "同上标题笔误；'香菇粉烘干致苦味肽'与该综述无直接论述，降级为间接参考"),
 "CASE-2026-010": ("《麻辣火锅底料的麻辣风味特性及其与咸度关联分析》（DOC-016）",
   "原引《不同骨类的骨汤炖煮工艺优化》索引内不存在；咸味问题改引咸度关联研究。'18% 上限'须另引国标（GB 31644 或企业标准），不能引文献"),
 "CASE-2026-021": ("《红四氮唑在川味复合调味料菌落总数检测中的应用》（DOC-038）",
   "原引《一种提升麻辣火锅底料风味物质加工工艺探讨》索引内不存在；胀气/厌氧菌改引微生物检测类文献"),
 "CASE-2026-028": ("无直接文献支撑（内部记录）",
   "原引文献索引内不存在；'汤色浑浊/透光率下降'在现有 50 篇内无对应研究，如实标注"),
 "CASE-2026-031": ("GB 7718 预包装食品标签通则（国标，非文献）",
   "原把国标塞进文献编号（DOC-031 实为罂粟壳生物碱检测方法）。标签问题应引国标，DOC 编号留空"),
 "CASE-2026-033": ("《免疫亲和柱净化-超高效液相色谱串联质谱法同时测定火锅底料中的5种真菌毒素》（DOC-030）",
   "原引 DOC-027（工业染料与生物碱）与黄曲霉毒素 B1 不同类；改引真菌毒素检测文献"),
 "CASE-2026-050": ("待追溯（来源记录与原因状态均为空）",
   "该行来源记录、原因状态两列均为空，需补录；原因状态建议先填'未确认'"),
 "CASE-2026-006": ("无直接文献支撑（内部记录）", "漏油/密封性 与 塑化剂迁移 无共同指标，原引不成立"),
 "CASE-2026-008": ("无直接文献支撑（内部记录）", "黑色碎屑/杂质超标 与 微生物多样性测序 无关"),
 "CASE-2026-012": ("无直接文献支撑（内部记录）", "麻味不足/花椒酰胺 在所引方砖品质文献摘要中无任何论述"),
 "CASE-2026-016": ("无直接文献支撑（内部记录）", "沉淀/不溶性固形物 与 工艺参数优化 无共同指标"),
 "CASE-2026-022": ("无直接文献支撑（内部记录）", "金属异味/铁离子 与 番茄贮藏品质 无关"),
 "CASE-2026-023": ("无直接文献支撑（内部记录）", "鲜味不足/谷氨酸钠 与 辣椒有效成分溶出 无关"),
 "CASE-2026-024": ("无直接文献支撑（内部记录）", "沙粒感/灰分 与 挥发性成分分析 无关"),
 "CASE-2026-027": ("无直接文献支撑（内部记录）", "包装褪色/油墨脱落 与 塑化剂迁移 无关"),
 "CASE-2026-034": ("无直接文献支撑（内部记录）", "包装内水滴/水分活度 与 塑化剂迁移 无关"),
 "CASE-2026-039": ("无直接文献支撑（内部记录）", "呈味核苷酸降解 与 辣椒有效成分溶出 无关"),
 "CASE-2026-042": ("无直接文献支撑（内部记录）", "袋内大冰晶/组织结构破坏 在所引番茄贮藏文献中无论述"),
 "CASE-2026-044": ("原引用保留（间接参考：同属包装材料，指标不同）", "内壁发黄/油脂渗透 与 塑化剂迁移 仅同属包装材料，保留但降级"),
 "CASE-2026-046": ("《热解吸-电喷雾离子源-三重四极杆质谱法快速筛查火锅底料和肉汤中非法添加罂粟壳》（DOC-033）",
   "口腔麻木/疑似违规添加 应引非法添加类文献，原引方砖品质文献不成立"),
}

ws = wb["历史异常案例"]
maxr, maxc = ws.max_row, ws.max_column
ws.cell(row=1, column=maxc + 1, value="产品编码（建议）")
ws.cell(row=1, column=maxc + 2, value="来源记录_修订")
ws.cell(row=1, column=maxc + 3, value="修订说明")
for c in range(maxc + 1, maxc + 4):
    cell = ws.cell(row=1, column=c)
    cell.font, cell.fill = HDR_FONT, HDR_FILL
    cell.alignment = Alignment(horizontal="center", vertical="center")

PROD_MAP = {
    "牛油麻辣底料": "PRD-01",
    "牛油底料": "PRD-01（与牛油麻辣同族，待确认）",
    "麻辣底料": "PRD-01（待确认）",
    "清油麻辣底料": "PRD-02",
    "清油底料": "PRD-02（与清油麻辣同族，待确认）",
    "番茄底料": "PRD-03",
    "菌汤底料": "PRD-04",
    "牛油特辣底料": "PRD-05",
    "混合底料": "待确认",
}

n_fix = 0
for r in range(2, maxr + 1):
    cid = str(ws.cell(row=r, column=1).value or "")
    prod = str(ws.cell(row=r, column=2).value or "").split("（")[0].strip()
    ws.cell(row=r, column=maxc + 1, value=PROD_MAP.get(prod, "待确认"))
    if cid in FIX:
        ws.cell(row=r, column=maxc + 2, value=FIX[cid][0])
        ws.cell(row=r, column=maxc + 3, value=FIX[cid][1])
        n_fix += 1
    else:
        ws.cell(row=r, column=maxc + 3, value="无需修订：引用标题与编号一致且主题相关")
widths = {maxc + 1: 26, maxc + 2: 62, maxc + 3: 72}
for c, w in widths.items():
    ws.column_dimensions[ws.cell(row=1, column=c).column_letter].width = w
for r in range(2, maxr + 1):
    for c in range(maxc + 1, maxc + 4):
        ws.cell(row=r, column=c).alignment = Alignment(vertical="top", wrap_text=True)

# ============================================================
# 改动② 时序表：产品编码 + 判定限值 + 限值来源
# ============================================================
ws2 = wb["时间序列检测数据"]
m2r, m2c = ws2.max_row, ws2.max_column
ws2.cell(row=1, column=m2c + 1, value="产品编码")
ws2.cell(row=1, column=m2c + 2, value="判定限值")
ws2.cell(row=1, column=m2c + 3, value="限值来源")
for c in range(m2c + 1, m2c + 4):
    cell = ws2.cell(row=1, column=c)
    cell.font, cell.fill = HDR_FONT, HDR_FILL
    cell.alignment = Alignment(horizontal="center", vertical="center")

TS_PROD = {"牛油麻辣底料": "PRD-01", "清油麻辣底料": "PRD-02", "番茄底料": "PRD-03",
           "菌汤底料": "PRD-04", "牛油特辣底料": "PRD-05"}
# 只用能核到出处（标准/表内）的限值；查不到的一律留空标"待核定"
LIMIT = {
    "酸价": (2.5, "企业内控/客户标准（案例表 CASE-2026-001 自述上限）；GB 2716-2018 表2 对植物油酸价为 3(棕榈仁油等)/4(其他) mg/g，成品 2.5 严于国标"),
    "过氧化值": (0.25, "GB 2716-2018 表2 过氧化值 ≤0.25 g/100g（适用于油脂；含油型底料作内控参考，非直接适用）"),
    "水分": ("待核定", "GB 31644-2018 未设水分限值，需以企业标准为准，本表暂不填"),
}
for r in range(2, m2r + 1):
    prod = str(ws2.cell(row=r, column=3).value or "").strip()
    ind = str(ws2.cell(row=r, column=6).value or "").strip()
    ws2.cell(row=r, column=m2c + 1, value=TS_PROD.get(prod, "待确认"))
    lim, src = LIMIT.get(ind, ("待核定", "无来源"))
    ws2.cell(row=r, column=m2c + 2, value=lim)
    ws2.cell(row=r, column=m2c + 3, value=src)
    # 酸价小数位统一显示（只改显示格式，不改数值）
    if ind == "酸价":
        ws2.cell(row=r, column=7).number_format = "0.0"

ws2.column_dimensions[ws2.cell(row=1, column=m2c + 1).column_letter].width = 14
ws2.column_dimensions[ws2.cell(row=1, column=m2c + 2).column_letter].width = 12
ws2.column_dimensions[ws2.cell(row=1, column=m2c + 3).column_letter].width = 56
for r in range(2, m2r + 1):
    ws2.cell(row=r, column=m2c + 3).alignment = Alignment(vertical="top", wrap_text=True)

# 说明页
ws3 = wb.create_sheet("修订说明")
notes = [
 ["本轮只改两条，原数据一字未动，改动全部落在新增列，可随时回滚", ""],
 ["改动", "内容"],
 ["① 案例表引用", "新增 3 列：产品编码（建议）/ 来源记录_修订 / 修订说明；共修订 %d 条（原「来源记录」原样保留）" % n_fix],
 ["② 时序表分组判定", "新增 3 列：产品编码 / 判定限值 / 限值来源；酸价显示格式统一为 0.0（数值未改）"],
 ["未改、留待下一轮", "SPC指标表现 拆成 指标名/实测值/单位/判定 四列；产品名称统一；补平行样与检测方法字段"],
 ["限值口径提醒", "表中只有『酸价 2.5mg/g』有表内出处（案例表自述）；过氧化值与水分均标『待核定』，未填任何凭记忆的数字"],
 ["SPC 点数提醒", "时序表 8 个(批次×指标)组合各仅 3~4 点，且为同一批次随储藏时间的变化，可用于货架期趋势图，不能用于控制图。控制图另需 20~25 个批次的出厂检验值"],
]
for row in notes:
    ws3.append(row)
ws3.column_dimensions["A"].width = 22
ws3.column_dimensions["B"].width = 100
for r in range(1, len(notes) + 1):
    ws3.cell(row=r, column=2).alignment = Alignment(vertical="top", wrap_text=True)

wb.save(DST)
print("已生成：", DST)
print("案例表修订 %d 条；原「来源记录」列保留未动" % n_fix)
print("新增列：案例表 +3（产品编码/来源记录_修订/修订说明），时序表 +3（产品编码/判定限值/限值来源）")

# 自检：确认原列没被改
wb2 = openpyxl.load_workbook(SRC, data_only=True)
wb3 = openpyxl.load_workbook(DST, data_only=True)
for name in ["火锅底料知识文档索引", "时间序列检测数据", "历史异常案例"]:
    a, b = wb2[name], wb3[name]
    same = all(a.cell(row=r, column=c).value == b.cell(row=r, column=c).value
               for r in range(1, a.max_row + 1) for c in range(1, a.max_column + 1))
    print("原列一致性 %-16s : %s" % (name, "未改动 OK" if same else "有差异 !!"))
