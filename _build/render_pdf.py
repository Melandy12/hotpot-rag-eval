# -*- coding: utf-8 -*-
"""把国标 PDF 渲染成 PNG，便于逐页核对文本"""
import os
import sys, os, fitz

OUT = os.path.join(ROOT, '_build/gb_pages')
os.makedirs(OUT, exist_ok=True)
for path in sys.argv[1:]:
    tag = os.path.splitext(os.path.basename(path))[0].replace(" ", "_")
    doc = fitz.open(path)
    for i, page in enumerate(doc, 1):
        pix = page.get_pixmap(dpi=200)
        png = os.path.join(OUT, "%s_p%d.png" % (tag, i))
        pix.save(png)
        print("%s  %dx%d" % (png, pix.width, pix.height))
