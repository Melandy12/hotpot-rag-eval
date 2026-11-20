# -*- coding: utf-8 -*-
"""99 验收自检：一条命令判断这套系统现在是否"活着且没退化"

用法：
    python 99_验收自检.py            # 完整自检（约 1~2 分钟）
    python 99_验收自检.py --fast     # 跳过 30 题整批问答（省 3.5 分钟）

断言的是**能力底线**，不是刷分：
    术语 Hit@1 ≥ 90、口语 Hit@1 ≥ 80、零召回 == 0、索引 120 片、
    水分口径必须出现"不判定"和"45662"、两端口在线
任何一条不达标就 exit 1，并指出是哪一条——这就是固定题集的用处：
在没人报错的时候发现系统坏了（例如 Jev 分词失效导致打分恒定）。
"""
import os
import json
import re
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
KB = os.path.join(ROOT, '01_knowledge_base_v2_sag')
SAG = os.environ.get("ZJ_SAG_BIN", "<请配置 SAG 命令行路径 sag.exe>")
PY = sys.executable

FAST = "--fast" in sys.argv
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""), flush=True)


def http_ok(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return True, r.read(300).decode("utf-8", "ignore")
    except Exception as e:
        return False, str(e)


print("=== 一、服务在线性 ===", flush=True)
ok, body = http_ok("http://127.0.0.1:8000/")
calls = ""
m = re.search(r'"calls"\s*:\s*(\d+)', body)
if m:
    calls = "calls=%s" % m.group(1)
check("Jev 决策服务 8000 在线（backend=lexical）", ok and "lexical" in body, calls or body[:60])
ok2, body2 = http_ok("http://127.0.0.1:11434/api/tags")
check("Ollama 11434 在线", ok2 and "qwen25-7b-local" in body2, "模型已注册" if ok2 else body2[:60])

print("=== 二、索引完整性 ===", flush=True)
out = subprocess.run([SAG, "check", KB], capture_output=True, timeout=120)
txt = out.stdout.decode("utf-8", "ignore")
m = re.search(r"当前目录内已索引文件数：(\d+)", txt)
n = int(m.group(1)) if m else -1
check("语料索引 120 片", n == 120, "读到 %d 片" % n)

print("=== 三、检索指标（固定题集）===", flush=True)
p = subprocess.run([PY, "09_sag2_syn_eval.py", "2"], cwd=HERE, capture_output=True, timeout=900)
txt2 = p.stdout.decode("utf-8", "ignore")
rows = {}
for line in txt2.splitlines():
    line = line.strip()
    if line.startswith("{"):
        try:
            d = json.loads(line)
            rows[d["mode"]] = d
        except Exception:
            pass
m1 = rows.get("M1")
if not m1:
    check("09 号评测可跑", False, txt2[-200:])
else:
    t1 = float(m1["术语版_hit@1"].rstrip("%"))
    o1 = float(m1["口语版_hit@1"].rstrip("%"))
    z = m1["术语版_零召回"] + m1["口语版_零召回"]
    check("术语版 Hit@1 ≥ 90%", t1 >= 90, "实测 %.1f%%（定稿 93.3%%）" % t1)
    check("口语版 Hit@1 ≥ 80%", o1 >= 80, "实测 %.1f%%（定稿 86.7%%）" % o1)
    check("零召回 == 0", z == 0, "实测 %d" % z)

print("=== 四、答案层两条确定性规则 ===", flush=True)
q1 = "水分 有没有限值 超多少算超标"
p1 = subprocess.run([PY, "11_local_answer.py", q1], cwd=HERE, capture_output=True, timeout=600)
a1 = p1.stdout.decode("utf-8", "ignore")
check("水分口径：说出「不判定」", "不判定" in a1)
check("水分口径：引出 GB/T 45662 参照值", "45662" in a1)
check("水分口径：口径卡被强制置顶", "GB-SF-料渣水分" in a1)

q2 = "底料煮出来汤发黑是咋回事"
p2 = subprocess.run([PY, "11_local_answer.py", q2], cwd=HERE, capture_output=True, timeout=600)
a2 = p2.stdout.decode("utf-8", "ignore")
check("环节归因：案例卡首位是工艺归因（CASE-035）", "CASE-2026-035" in a2, "" if "CASE-2026-035" in a2 else a2.splitlines()[2:5])

if not FAST:
    print("=== 五、30 题整批问答（约 3.5 分钟）===", flush=True)
    p3 = subprocess.run([PY, "12b_answer_batch_30.py"], cwd=HERE, capture_output=True, timeout=1200)
    a3 = p3.stdout.decode("utf-8", "ignore")
    m = re.search(r"前五命中 gold (\d+)/30，总耗时 (\d+) 秒", a3)
    if m:
        hit, secs = int(m.group(1)), int(m.group(2))
        check("30 题前五命中 == 30/30", hit == 30, "实测 %d/30，%d 秒" % (hit, secs))
    else:
        check("30 题整批可跑", False, a3[-200:])

bad = [r for r in results if not r[1]]
print("\n=== 结论 ===", flush=True)
print("通过 %d / %d 项" % (len(results) - len(bad), len(results)))
if bad:
    print("未通过：")
    for name, _, d in bad:
        print("  - " + name + ("  " + d if d else ""))
    sys.exit(1)
print("系统当前状态：正常，可交付。")
