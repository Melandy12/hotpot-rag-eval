# -*- coding: utf-8 -*-
"""修复 GB 标准 PDF 的乱码：字体把 GBK 字节按 EUC-KR(cp949) 映射"""
import sys, fitz

p = sys.argv[1]
doc = fitz.open(p)
for i, page in enumerate(doc, 1):
    raw = page.get_text()
    fixed = None
    for enc in ("cp949", "euc-kr"):
        try:
            fixed = raw.encode(enc).decode("gbk")
            break
        except Exception:
            continue
    print("\n===== 第 %d 页 =====" % i)
    print(fixed if fixed else raw)
