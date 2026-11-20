# -*- coding: utf-8 -*-
"""下载食品安全国家标准全文 PDF（政府官网/公开渠道），并校验可解析"""
import os, sys, urllib.request, hashlib

OUT = os.path.join(ROOT, '02_国标待导入')
TARGETS = {
    "GB 2716-2018 植物油.pdf": "http://jckspj.customs.gov.cn/spj/fileDir/resource/cms/article/4576761/4646844/2022102809450113057.pdf",
    "GB 31644-2018 复合调味料.pdf": "https://img.antpedia.com/standard/pdf/1/2212/GB%2031644-2018.pdf",
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, url in TARGETS.items():
        path = os.path.join(OUT, name)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            with open(path, "wb") as f:
                f.write(data)
            sha = hashlib.sha256(data).hexdigest()[:16]
            print("OK   %-32s %8d 字节  sha256:%s" % (name, len(data), sha))
            try:
                import fitz
                doc = fitz.open(path)
                pages = doc.page_count
                text = "".join(p.get_text() for p in doc)
                print("     PDF %d 页，抽出 %d 字，首行: %s" % (pages, len(text), text.strip().splitlines()[0][:60]))
            except Exception as e:
                print("     PDF 解析失败: %s" % e)
        except Exception as e:
            print("FAIL %-32s %s" % (name, e))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
