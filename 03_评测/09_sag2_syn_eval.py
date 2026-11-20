# -*- coding: utf-8 -*-
"""
路线 A：SAG2 骨架 + 词法决策 + 同义词表补检索
对比三种查询策略（同一语料、同一题集、同一决策服务）：
  M0 原句直查
  M1 总是扩展（原句 + 规范词）
  M2 零召回才扩展（先原句，取空了再用扩展句重查）
"""
import os
import csv, json, os, re, subprocess, sys, time

SAG = os.environ.get("ZJ_SAG_BIN", "<请配置 SAG 命令行路径 sag.exe>")
CORPUS = os.path.join(ROOT, '01_knowledge_base_v2_sag')
QSET = os.path.join(ROOT, '03_评测/03_固定问题集.csv')
DICT = os.path.join(ROOT, '03_评测/03_同义词扩展词典.json')
OUT_DIR = os.path.join(ROOT, '04_结果')
TOPK = 10
# 每次最多追加几个规范词（命令行第 1 个参数，默认不限）
EXPAND_K = int(sys.argv[1]) if len(sys.argv) > 1 else 99
DOCID = re.compile(r"^((?:DOC|CASE|TS_BATCH)-[\w\-]+?)(?=_|\.md|$)")


def load_dict():
    with open(DICT, encoding="utf-8") as f:
        d = json.load(f)
    return {k: v for k, v in d.items() if not k.startswith("_") and isinstance(v, list)}


def expand(query, dic):
    """命中口语词 → 追加对应规范词（去重）"""
    terms = []
    for k, vals in dic.items():
        if k in query:
            for v in vals:
                if v not in terms and v not in query:
                    terms.append(v)
    return (query + " " + " ".join(terms[:EXPAND_K])).strip(), terms[:EXPAND_K]


def sag(query, timeout=240):
    p = subprocess.run([SAG, query, CORPUS, "--json", "-m", str(TOPK), "--timeout", str(timeout)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout + 30)
    ids = []
    if p.returncode == 0 and p.stdout.strip():
        try:
            data = json.loads(p.stdout)
            for item in data.get("results", []):
                if ".sag-converted" in item.get("path", ""):
                    continue
                m = DOCID.match(os.path.basename(item.get("path", "")))
                if m and m.group(1) not in ids:
                    ids.append(m.group(1))
        except Exception as e:
            print("  解析失败: %s" % e)
    return ids


def run_mode(mode, rows, dic):
    out = []
    for i, r in enumerate(rows, 1):
        gold = [g.strip() for g in r["gold_ids"].split("|") if g.strip()]
        q0 = r["query"]
        used = q0
        ids = sag(q0)
        if mode == "M1":
            used, terms = expand(q0, dic)
            if terms:
                ids = sag(used)
        elif mode == "M2":
            if not ids:
                used, terms = expand(q0, dic)
                if terms:
                    ids = sag(used)
        rank = None
        for idx, did in enumerate(ids, 1):
            if did in gold:
                rank = idx
                break
        out.append({"intent": r["intent"], "style": r["style"], "query": q0,
                    "retrieval_query": used, "rank": rank or "",
                    "hit@1": 1 if rank == 1 else 0,
                    "hit@3": 1 if rank and rank <= 3 else 0,
                    "hit@5": 1 if rank and rank <= 5 else 0,
                    "hit@10": 1 if rank else 0,
                    "rr": 1.0 / rank if rank else 0.0,
                    "zero_recall": 1 if not ids else 0,
                    "top_ids": "|".join(ids)})
        if i % 5 == 0:
            print("  %s %d/%d" % (mode, i, len(rows)), flush=True)
    return out


def summarize(mode, res):
    line = {"mode": mode}
    for style in ("术语版", "口语版"):
        sub = [x for x in res if x["style"] == style]
        n = len(sub)
        line[style + "_hit@1"] = "%.1f%%" % (100 * sum(x["hit@1"] for x in sub) / n)
        line[style + "_hit@5"] = "%.1f%%" % (100 * sum(x["hit@5"] for x in sub) / n)
        line[style + "_mrr"] = "%.3f" % (sum(x["rr"] for x in sub) / n)
        line[style + "_零召回"] = sum(x["zero_recall"] for x in sub)
    return line


def main():
    dic = load_dict()
    with open(QSET, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    all_sum, detail = [], []
    t0 = time.time()
    for mode in ("M0", "M1", "M2"):
        print("== %s ==" % mode, flush=True)
        res = run_mode(mode, rows, dic)
        all_sum.append(summarize(mode, res))
        for x in res:
            x["mode"] = mode
        detail.extend(res)

    tag = "09_SAG2_词表策略_K%d" % EXPAND_K
    with open(os.path.join(OUT_DIR, tag + "_汇总.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_sum[0].keys()))
        w.writeheader(); w.writerows(all_sum)
    with open(os.path.join(OUT_DIR, tag + "_逐题.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(detail[0].keys()))
        w.writeheader(); w.writerows(detail)

    print("\n== 汇总 ==")
    for s in all_sum:
        print(json.dumps(s, ensure_ascii=False))
    print("用时 %.1f 秒" % (time.time() - t0))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
