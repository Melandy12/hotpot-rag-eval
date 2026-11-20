# -*- coding: utf-8 -*-
"""案例卡 / 文献卡 / 标准卡 分权重重排实验（22 题原话集，M1 扩词 K=2）

思路：SAG 只给有序列表、不给分数，所以本地重排——
  1) 取前 15 个候选（含 heading + content）
  2) 用字 bigram 覆盖率算一个本地相关度分
  3) 乘文档类型权重，再重排
  4) 与原始顺序对比 Hit@1/3/5、MRR
"""
import os
import csv, json, os, re, subprocess, sys, time

SAG = os.environ.get("ZJ_SAG_BIN", "<请配置 SAG 命令行路径 sag.exe>")
CORPUS = os.path.join(ROOT, '01_knowledge_base_v2_sag')
QSET = os.path.join(ROOT, '03_评测/14_师傅原话问题集.csv')
DICT = os.path.join(ROOT, '03_评测/03_同义词扩展词典.json')
OUT_DIR = os.path.join(ROOT, '04_结果')
TOPK = 15
EXPAND_K = 2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rerank_apply import doc_id_of, doc_type_of

# 意图词表：决定给哪类卡加权
STD_WORDS = ["国标", "限值", "标准", "卡的是", "超标", "判定", "合规", "出厂检验"]
CASE_WORDS = ["咋回事", "为什么", "为啥", "是不是", "原因", "正常吗", "怎么回事", "退回去"]
DOC_WORDS = ["验收", "指标", "怎么", "哪些", "方法", "检测", "工艺", "留样", "控制"]


def load_dict():
    with open(DICT, encoding="utf-8") as f:
        d = json.load(f)
    return {k: v for k, v in d.items() if not k.startswith("_") and isinstance(v, list)}


def expand(query, dic):
    terms = []
    for k, vals in dic.items():
        if k in query:
            for v in vals:
                if v not in terms and v not in query:
                    terms.append(v)
    return (query + " " + " ".join(terms[:EXPAND_K])).strip(), terms[:EXPAND_K]


def sag(query, timeout=240):
    p = subprocess.run([SAG, query, CORPUS, "--json", "-m", str(TOPK), "--timeout", str(timeout)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout + 30)
    out = []
    if p.returncode == 0 and p.stdout.strip():
        try:
            for item in json.loads(p.stdout).get("results", []):
                path = item.get("path", "")
                if ".sag-converted" in path:
                    continue
                did = doc_id_of(path)
                m = bool(did)
                if not m:
                    continue
                if any(x["id"] == did for x in out):
                    continue
                out.append({
                    "id": did,
                    "type": doc_type_of(did),
                    "heading": item.get("heading", "") or "",
                    "content": item.get("content", "") or "",
                })
        except Exception as e:
            print("  解析失败 %s" % e)
    return out


def bigrams(text):
    t = re.sub(r"[\s\W_]+", "", text.lower())
    return set(t[i:i + 2] for i in range(len(t) - 1)) if len(t) > 1 else set(t)


def local_score(query, item):
    qb = bigrams(query)
    if not qb:
        return 0.0
    hb = bigrams(item["heading"]) & qb
    cb = bigrams(item["content"]) & qb
    hcov = len(hb) / len(qb)
    ccov = len(cb) / len(qb)
    return 0.30 * hcov + 0.70 * ccov


def intent_of(query):
    if any(w in query for w in STD_WORDS):
        return "std"
    if any(w in query for w in CASE_WORDS):
        return "case"
    if any(w in query for w in DOC_WORDS):
        return "doc"
    return "mix"


SCHEMES = {
    "S0_原始顺序": None,                                   # 不重排
    "S1_案例优先": {"CASE": 1.20, "DOC": 0.95, "GB": 1.00, "QY": 1.00, "TS": 1.00},
    "S2_文献优先": {"CASE": 0.90, "DOC": 1.20, "GB": 1.00, "QY": 1.00, "TS": 1.00},
    "S3_标准优先": {"CASE": 0.90, "DOC": 0.95, "GB": 1.30, "QY": 1.30, "TS": 1.00},
    "S4_意图路由": "intent",
}

INTENT_W = {
    "std":  {"CASE": 0.85, "DOC": 0.95, "GB": 1.30, "QY": 1.30, "TS": 1.00},
    "case": {"CASE": 1.25, "DOC": 0.95, "GB": 0.90, "QY": 0.90, "TS": 1.00},
    "doc":  {"CASE": 0.90, "DOC": 1.25, "GB": 1.00, "QY": 1.00, "TS": 1.00},
    "mix":  {"CASE": 1.05, "DOC": 1.05, "GB": 1.00, "QY": 1.00, "TS": 1.00},
}


def rerank(items, query, weights):
    scored = []
    for i, it in enumerate(items):
        s = local_score(query, it)
        # 原始位次给一点基础分，避免本地分把明显靠前的挤掉
        base = 1.0 / (1.0 + 0.08 * i)
        w = weights.get(it["type"], 1.0)
        scored.append(((s * 0.75 + base * 0.25) * w, i, it["id"], it["type"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored


def eval_rank(ids, gold):
    for idx, did in enumerate(ids, 1):
        if did in gold:
            return idx
    return None


def main():
    dic = load_dict()
    rows = list(csv.DictReader(open(QSET, encoding="utf-8-sig")))
    print("题集 %d 条，候选 %d" % (len(rows), TOPK))

    rows_built = []
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        q0 = r["query"]
        used, terms = expand(q0, dic)
        items = sag(used)
        rows_built.append({"intent": r["intent"], "query": q0, "used": used,
                           "terms": "|".join(terms),
                           "gold": [g.strip() for g in r["gold_ids"].split("|") if g.strip()],
                           "items": items, "qtype": intent_of(q0)})
        print("  取候选 %2d/%d  %d 条  %s" % (i, len(rows), len(items), used[:38]), flush=True)

    res_all, summ = [], []
    for name, w in SCHEMES.items():
        ranks = []
        detail = []
        for rb in rows_built:
            if w is None:
                ids = [it["id"] for it in rb["items"]]
            elif w == "intent":
                order = rerank(rb["items"], rb["used"], INTENT_W[rb["qtype"]])
                ids = [x[2] for x in order]
            else:
                order = rerank(rb["items"], rb["used"], w)
                ids = [x[2] for x in order]
            rank = eval_rank(ids, rb["gold"])
            ranks.append(rank)
            detail.append({"方案": name, "query": rb["query"], "qtype": rb["qtype"],
                           "rank": rank or "", "top5": "|".join(ids[:5])})
        n = len(ranks)
        s = {"方案": name, "n": n,
             "hit@1": "%.1f%%" % (100 * sum(1 for r in ranks if r == 1) / n),
             "hit@3": "%.1f%%" % (100 * sum(1 for r in ranks if r and r <= 3) / n),
             "hit@5": "%.1f%%" % (100 * sum(1 for r in ranks if r and r <= 5) / n),
             "mrr": "%.3f" % (sum(1.0 / r if r else 0.0 for r in ranks) / n)}
        summ.append(s)
        res_all.extend(detail)
        print(json.dumps(s, ensure_ascii=False))

    with open(os.path.join(OUT_DIR, "15_重排权重实验_汇总.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(summ[0].keys()))
        wr.writeheader()
        wr.writerows(summ)
    with open(os.path.join(OUT_DIR, "15_重排权重实验_逐题.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(res_all[0].keys()))
        wr.writeheader()
        wr.writerows(res_all)
    print("用时 %.1f 秒" % (time.time() - t0))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
