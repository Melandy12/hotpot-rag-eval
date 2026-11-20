# -*- coding: utf-8 -*-
import sys, os, fitz

p = sys.argv[1]
doc = fitz.open(p)
print("页数:", doc.page_count)
for i, page in enumerate(doc, 1):
    t = page.get_text()
    print("\n===== 第 %d 页（%d 字）=====" % (i, len(t)))
    print(t)
