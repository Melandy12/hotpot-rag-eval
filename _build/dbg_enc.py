# -*- coding: utf-8 -*-
import sys, fitz

p = sys.argv[1]
doc = fitz.open(p)
raw = doc[2].get_text()
sample = raw[:60]
print("原始:", repr(sample))
for enc in ("cp949", "euc-kr", "uhc"):
    try:
        b = sample.encode(enc)
        print(enc, "-> bytes len", len(b), b[:40])
        for dec in ("gbk", "gb18030", "big5"):
            try:
                print("   ", dec, ":", b.decode(dec)[:40])
            except Exception as e:
                print("   ", dec, "失败", e)
    except Exception as e:
        print(enc, "编码失败:", e)
