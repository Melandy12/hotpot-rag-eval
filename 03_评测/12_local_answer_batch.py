# -*- coding: utf-8 -*-
"""批量跑本地问答链路，结果落 md"""
import importlib.util
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
spec = importlib.util.spec_from_file_location(
    "la", os.path.join(HERE, "11_local_answer.py"))
la = importlib.util.module_from_spec(spec)
spec.loader.exec_module(la)

QS = [
    "黑水是咋回事，煮出来汤是黑的",
    "底料放两个月就不香了，味道跑掉了，是什么原因",
    "酸价超标一般是什么原因造成的",
    "火锅底料成品该适用哪个食品安全国家标准",
    "料渣水分高会带来什么问题",
]

out = io.StringIO()
out.write("# 本地问答链路试跑（SAG 检索 + Qwen2.5-7B 本地生成）\n\n")
out.write("检索：SAG Wiki 本地服务（FTS5 + BM25 + Jev 判定），知识库 108 片；生成：qwen25-7b-local（Ollama，RTX 4060 Laptop）。\n\n")
for q in QS:
    items, ans = la.ask(q)
    out.write("## 问：%s\n\n" % q)
    out.write("**命中证据**\n\n")
    for i, it in enumerate(items, 1):
        out.write("- [证据%d] %s ｜ %s\n" % (i, it["path"], it["heading"]))
    out.write("\n**回答**\n\n%s\n\n---\n\n" % ans.strip())
    sys.stdout.write("done: %s\n" % q)

path = os.path.join(ROOT, "04_结果", "12_本地问答链路_试跑.md")
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("saved", path, os.path.getsize(path))
