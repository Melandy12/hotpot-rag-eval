# -*- coding: utf-8 -*-
"""重建 SAG 索引（语料新增 2 张国标卡）并做国标题命中检查"""
import os
import json, os, re, subprocess, sys

SAG = os.environ.get("ZJ_SAG_BIN", "<请配置 SAG 命令行路径 sag.exe>")
CORPUS = os.path.join(ROOT, '01_knowledge_base_v2_sag')
DOCID = re.compile(r"^((?:DOC|CASE|TS_BATCH|GB)-[\w\-]+)")

QS = [
    "过氧化值的国标限值是多少",
    "酸价限值的检验方法用哪个标准",
    "复合调味料对酸价有没有限值",
    "火锅底料成品该适用哪个食品安全国家标准",
    "料渣水分的限值标准出处",
]


def run(args):
    p = subprocess.run([SAG] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main():
    print("语料 md 数:", len([f for f in os.listdir(CORPUS) if f.endswith(".md")]))
    rc, out = run(["remove", CORPUS])
    print("remove:", rc, out.strip()[:200])
    rc, out = run(["add", CORPUS])
    print("add:", rc, out.strip()[:300])

    for q in QS:
        rc, out = run([q, CORPUS, "--json", "-m", "3", "--timeout", "180"])
        print("\n问:", q)
        if rc != 0:
            print("  失败:", out[:200])
            continue
        try:
            data = json.loads(out)
        except Exception:
            print("  解析失败:", out[:200])
            continue
        for i, it in enumerate(data.get("results", []), 1):
            path = it.get("path", "")
            if ".sag-converted" in path:
                continue
            m = DOCID.match(os.path.basename(path))
            print("  %d. %s" % (i, m.group(1) if m else os.path.basename(path)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
