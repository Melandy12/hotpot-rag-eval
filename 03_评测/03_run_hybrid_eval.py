# -*- coding: utf-8 -*-
"""混合检索评测：BM25 + 向量（bge-m3 / nomic-embed-text），同一套固定问题集。

用法：
    python 03_run_hybrid_eval.py --model bge-m3
    python 03_run_hybrid_eval.py --model nomic-embed-text --host http://127.0.0.1:11434

后端二选一：
  1) Ollama 本地  http://127.0.0.1:11434   （--model bge-m3）
  2) OpenAI 兼容  http://127.0.0.1:1234/v1 （AnythingLLM / Cherry Studio 内置服务，--openai）
"""
import os, csv, json, math, re, sys, argparse, urllib.request
from collections import Counter
import jieba

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
KB_DIR = os.path.join(ROOT, "01_knowledge_base")
EVAL_DIR = os.path.join(ROOT, "03_评测")
RES_DIR = os.path.join(ROOT, "04_结果")
CACHE = os.path.join(RES_DIR, "_embed_cache.json")
os.makedirs(RES_DIR, exist_ok=True)

TOP_K = 5
K1, B = 1.5, 0.75
TOKEN_RE = re.compile(r"^[\w\u4e00-\u9fff%\.\-]+$")
STOP = set("的了和与及或在是有为以其之一个这那怎么什么哪些啥吗呢吧啊也就都还又再更很太请问如何怎样为什么哪个多少")
DOMAIN_WORDS = """酸价 过氧化值 水分活度 料渣 黑水 哈喇味 起泡 胀袋 辣椒素 罂粟壳 罂粟壳生物碱
塑化剂 邻苯二甲酸酯 美拉德反应 乳化稳定性 不溶性固形物 氨基酸态氮 极性组分 黄曲霉毒素 苯并芘
亚硝酸盐 色差 透光率 针入度 灰分 还原糖 挥发性风味物质 香气保留率 风味稳定性 货架期 加速试验
动力学模型 活化能 菌落总数 产气菌 乳酸菌 汤色 黑色碎屑 沉淀物 油脂析出 表面张力 泡沫 乳化剂
炒制温度 炒制时间 工艺参数 食盐含量 咸度 减钠 批次一致性 方差 迁移 包装材料 防腐 氧化 酸败 褐变
色素 顶空香气 感官评价 响应面法 主成分分析 生物碱 真菌毒素 工业染料 农药残留 矿质元素 重金属
水分 油脂 牛油 清油 底料 火锅底料 炒制 储藏 冷藏 微生物 酵母菌 厌氧菌 铁离子""".split()


# ---------------- 数据 ----------------
def load_corpus():
    with open(os.path.join(KB_DIR, "_manifest.csv"), encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def load_questions():
    with open(os.path.join(EVAL_DIR, "03_固定问题集.csv"), encoding="utf-8-sig", newline="") as f:
        out = []
        for r in csv.DictReader(f):
            if r.get("query"):
                out.append({"intent": r["intent"], "style": r["style"], "query": r["query"],
                            "gold": [g.strip() for g in r["gold_ids"].split("|") if g.strip()]})
        return out

def load_synonyms():
    with open(os.path.join(EVAL_DIR, "03_同义词扩展词典.json"), encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}

def tokenize(text):
    out = []
    for t in jieba.lcut(text):
        t = t.strip().lower()
        if not t or t in STOP or not TOKEN_RE.match(t):
            continue
        if len(t) == 1 and not t.isdigit():
            continue
        out.append(t)
    return out


# ---------------- BM25 ----------------
class BM25:
    def __init__(self, docs_tokens):
        self.N = len(docs_tokens)
        self.tf = [Counter(t) for t in docs_tokens]
        self.dl = [len(t) for t in docs_tokens]
        self.df = Counter()
        for c in self.tf:
            for t in c:
                self.df[t] += 1
        self.avgdl = sum(self.dl) / max(self.N, 1) or 1.0
        self.idf = {t: math.log((self.N - n + 0.5) / (n + 0.5) + 1.0) for t, n in self.df.items()}

    def scores(self, qtokens):
        out = []
        for i, c in enumerate(self.tf):
            s = 0.0
            for t in qtokens:
                f = c.get(t, 0)
                if f:
                    s += self.idf[t] * (f * (K1 + 1)) / (f + K1 * (1 - B + B * self.dl[i] / self.avgdl))
            out.append(s)
        return out


# ---------------- 向量 ----------------
def embed_ollama(texts, model, host):
    vecs = []
    for i, t in enumerate(texts):
        req = urllib.request.Request(
            host.rstrip("/") + "/api/embed",
            data=json.dumps({"model": model, "input": t}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        v = d.get("embeddings", [d.get("embedding")])[0]
        vecs.append(v)
        if i % 20 == 0:
            print("  embedded %d/%d" % (i, len(texts)), flush=True)
    return vecs

def embed_openai(texts, model, host, api_key="none"):
    req = urllib.request.Request(
        host.rstrip("/") + "/embeddings",
        data=json.dumps({"model": model, "input": texts}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key})
    with urllib.request.urlopen(req, timeout=180) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    return [x["embedding"] for x in d["data"]]

def cos(a, b):
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(y * y for y in b)) or 1e-9
    return num / (na * nb)

def minmax(v):
    lo, hi = min(v), max(v)
    if hi - lo < 1e-12:
        return [0.0] * len(v)
    return [(x - lo) / (hi - lo) for x in v]


# ---------------- 评测 ----------------
def evaluate(rankings, ids, questions, tag):
    rows = []
    for q, ranked in zip(questions, rankings):
        top = [ids[i] for i in ranked[:TOP_K]]
        gold = set(q["gold"])
        rank = next((r for r, cid in enumerate(top, 1) if cid in gold), None)
        rows.append({"variant": tag, "intent": q["intent"], "style": q["style"], "query": q["query"],
                     "hit@1": 1 if top[:1] and top[0] in gold else 0,
                     "hit@3": 1 if any(c in gold for c in top[:3]) else 0,
                     "hit@5": 1 if any(c in gold for c in top[:5]) else 0,
                     "first_rank": rank or "", "rr": round(1.0 / rank, 4) if rank else 0.0,
                     "top5": " > ".join(top)})
    return rows

def summarize(rows, tag):
    out = {}
    for style in ("术语版", "口语版"):
        sub = [r for r in rows if r["style"] == style]
        n = len(sub)
        out[(tag, style)] = {"n": n,
                             "hit@1": sum(r["hit@1"] for r in sub) / n,
                             "hit@3": sum(r["hit@3"] for r in sub) / n,
                             "hit@5": sum(r["hit@5"] for r in sub) / n,
                             "mrr": sum(r["rr"] for r in sub) / n,
                             "零召回": sum(1 for r in sub if not r["first_rank"])}
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="bge-m3")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--openai", action="store_true", help="走 OpenAI 兼容 /v1/embeddings")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()
    tag = args.tag or ("D_%s" % args.model.replace(":", "-"))

    corpus = load_corpus()
    ids = [c["chunk_id"] for c in corpus]
    texts = [c["title"] + "。" + c["text"] for c in corpus]
    questions = load_questions()
    syn = load_synonyms()
    for w in DOMAIN_WORDS:
        jieba.add_word(w, freq=5000)

    # BM25
    bm = BM25([tokenize(t) for t in texts])

    # 向量（带缓存，避免重复算）
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))
    key = args.model
    if key in cache and len(cache[key]["docs"]) == len(texts):
        doc_vecs = cache[key]["docs"]
        query_vecs = cache[key].get("queries", {})
        print("命中缓存：%s" % key)
    else:
        print("编码语料 %d 条 ..." % len(texts), flush=True)
        doc_vecs = embed_openai(texts, args.model, args.host) if args.openai else embed_ollama(texts, args.model, args.host)
        cache[key] = {"docs": doc_vecs, "queries": {}}
        json.dump(cache, open(CACHE, "w", encoding="utf-8"))
    if not cache[key].get("queries"):
        cache[key]["queries"] = {}

    qtexts = [q["query"] for q in questions]
    missing = [t for t in qtexts if t not in cache[key]["queries"]]
    if missing:
        qv = embed_openai(missing, args.model, args.host) if args.openai else embed_ollama(missing, args.model, args.host)
        for t, v in zip(missing, qv):
            cache[key]["queries"][t] = v
        json.dump(cache, open(CACHE, "w", encoding="utf-8"))

    # 三个排序：纯向量 / 混合RRF / 混合加权(0.4 BM25 + 0.6 向量)
    r_dense, r_rrf, r_w = [], [], []
    for q in questions:
        qt, _ = expand_query(q["query"], syn)
        qtoks = tokenize(qt)
        b = bm.scores(qtoks)
        b_norm = minmax(b)
        qv = cache[key]["queries"][q["query"]]
        d = [cos(qv, dv) for dv in doc_vecs]
        d_norm = minmax(d)

        r_dense.append(sorted(range(len(ids)), key=lambda i: -d[i]))
        r_w.append(sorted(range(len(ids)), key=lambda i: -(0.4 * b_norm[i] + 0.6 * d_norm[i])))
        # RRF
        rb = sorted(range(len(ids)), key=lambda i: -b[i])
        rd = sorted(range(len(ids)), key=lambda i: -d[i])
        rrf = [0.0] * len(ids)
        for r, i in enumerate(rb[:60], 1):
            rrf[i] += 1.0 / (60 + r)
        for r, i in enumerate(rd[:60], 1):
            rrf[i] += 1.0 / (60 + r)
        r_rrf.append(sorted(range(len(ids)), key=lambda i: -rrf[i]))

    all_rows, summary = [], {}
    for name, rk in ((tag + "_dense", r_dense), (tag + "_hybridRRF", r_rrf), (tag + "_hybridW", r_w)):
        rows = evaluate(rk, ids, questions, name)
        all_rows.extend(rows)
        summary.update(summarize(rows, name))

    out = os.path.join(RES_DIR, "04_混合检索逐题结果_%s.csv" % tag)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)

    print("\n=== %s 汇总 ===" % tag)
    print(f"{'方案':<26}{'问法':<8}{'Hit@1':>8}{'Hit@3':>8}{'Hit@5':>8}{'MRR':>8}{'零召回':>8}")
    for (nm, style), v in summary.items():
        print(f"{nm:<26}{style:<8}{v['hit@1']:>7.1%}{v['hit@3']:>8.1%}{v['hit@5']:>8.1%}{v['mrr']:>8.3f}{v['零召回']:>8}")
    print("\n输出：", out)


def expand_query(q, syn):
    extra = []
    for k, vs in syn.items():
        if k in q:
            extra.extend(vs)
    return q + (" " + " ".join(extra) if extra else ""), extra


if __name__ == "__main__":
    main()
