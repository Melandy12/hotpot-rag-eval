# -*- coding: utf-8 -*-
"""
SAG2 问答入口（路线 A 最终配置）
  查询 → 词表扩展（口语词→规范词，最多 K 个）→ SAG Wiki（SAG2 骨架）检索
       → 本地 Jev 服务（词法证据打分）排序 → 输出 Top-N 片段与出处

用法：
  python sag2_ask.py "底料放两个月就不香了 味道跑掉了"
  python sag2_ask.py "底料放两个月就不香了 味道跑掉了" --k 2 --top 5
  python sag2_ask.py "酸价超标的判定限值是多少" --raw     # 不做扩展
"""
import argparse
import json
import os
import re
import subprocess
import sys

SAG = os.environ.get("ZJ_SAG_BIN", "<请配置 SAG 命令行路径 sag.exe>")
CORPUS = os.path.join(ROOT, '01_knowledge_base_v2_sag')
DICT = os.path.join(ROOT, '03_评测/03_同义词扩展词典.json')
DOCID = re.compile(r"^((?:DOC|CASE|TS_BATCH)-[\w\-]+?)(?=_|\.md|$)")


def load_dict():
    with open(DICT, encoding="utf-8") as f:
        d = json.load(f)
    return {k: v for k, v in d.items() if not k.startswith("_") and isinstance(v, list)}


def expand(query, dic, k=2):
    hits = []
    for key, vals in dic.items():
        if key in query:
            for v in vals:
                if v not in hits and v not in query:
                    hits.append(v)
    return (query + " " + " ".join(hits[:k])).strip() if hits else query, hits[:k]


def ask(query, top=5, k=2, raw=False):
    q = query
    terms = []
    if not raw:
        q, terms = expand(query, load_dict(), k)
    p = subprocess.run([SAG, q, CORPUS, "--json", "-m", str(top), "--timeout", "180"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print("检索失败: %s" % (p.stderr or "")[:300])
        return 1
    data = json.loads(p.stdout)
    print("问: %s" % query)
    if terms:
        print("扩展词: %s" % "、".join(terms))
    print("检索式: %s\n" % q)
    for i, item in enumerate(data.get("results", []), 1):
        path = item.get("path", "")
        if ".sag-converted" in path:
            continue
        m = DOCID.match(os.path.basename(path))
        doc_id = m.group(1) if m else os.path.basename(path)
        heading = item.get("heading") or os.path.basename(path)
        body = (item.get("content") or "").replace("\r", "")
        snippet = ""
        SKIP_KEYS = ("案例编号", "产品编码", "产品及批次", "字段")
        for line in body.splitlines():
            s = line.strip()
            if not s or set(s) <= set("|-: "):
                continue
            if s.startswith("|"):
                cells = [c.strip() for c in s.strip("|").split("|")]
                if cells and cells[0] in SKIP_KEYS:
                    continue
                if len(cells) >= 2:
                    snippet = ("%s：%s" % (cells[0], cells[1]))[:180]
                    break
                s = " ".join(cells)
            snippet = s[:180]
            break
        print("%d. [%s] %s" % (i, doc_id, heading))
        if snippet:
            print("   %s" % snippet)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--raw", action="store_true", help="不做词表扩展")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    return ask(a.query, a.top, a.k, a.raw)


if __name__ == "__main__":
    raise SystemExit(main())
