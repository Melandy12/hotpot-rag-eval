# -*- coding: utf-8 -*-
"""BM25 检索评测：文献+案例知识库，术语版 vs 口语版固定问题集。

三组对照：
  A  vanilla   —— 默认 jieba 分词 + BM25
  B  dict      —— 加领域词典（保证专业词不被切碎）+ BM25
  C  expanded  —— 领域词典 + 口语同义词扩展 + BM25
"""
import os, csv, json, math, re, sys
from collections import Counter
import jieba

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
KB_DIR = os.path.join(ROOT, "01_knowledge_base")
# 可选参数：argv[1]=知识库目录，argv[2]=结果文件后缀标签
TAG = ""
if len(sys.argv) >= 2 and sys.argv[1].strip():
    KB_DIR = sys.argv[1].strip()
if len(sys.argv) >= 3 and sys.argv[2].strip():
    TAG = "_" + sys.argv[2].strip()
EVAL_DIR = os.path.join(ROOT, "03_评测")
RES_DIR = os.path.join(ROOT, "04_结果")
os.makedirs(RES_DIR, exist_ok=True)
print("KB_DIR =", KB_DIR)

TOP_K = 5
K1, B = 1.5, 0.75

DOMAIN_WORDS = """酸价 过氧化值 水分活度 料渣 黑水 哈喇味 起泡 胀袋 辣椒素 罂粟壳
罂粟壳生物碱 塑化剂 邻苯二甲酸酯 美拉德反应 乳化稳定性 不溶性固形物 氨基酸态氮
极性组分 黄曲霉毒素 苯并芘 亚硝酸盐 色差 透光率 针入度 灰分 还原糖 挥发性风味物质
香气保留率 风味稳定性 货架期 加速试验 动力学模型 活化能 菌落总数 产气菌 乳酸菌
汤色 黑色碎屑 沉淀物 油脂析出 表面张力 泡沫 乳化剂 炒制温度 炒制时间 工藝参数 工艺参数
食盐含量 咸度 减钠 批次一致性 方差 迁移 包装材料 防腐 氧化 酸败 褐变 色素 顶空香气
感官评价 响应面法 主成分分析 生物碱 真菌毒素 工业染料 农药残留 矿质元素 重金属
饮水 水分 油脂 牛油 清油 底料 火锅底料 炒制 储藏 冷藏 微生物 酵母菌 厌氧菌 铁离子
""".split()


def load_corpus():
    path = os.path.join(KB_DIR, "_manifest.csv")
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def build_tokenizer(use_domain_dict):
    if use_domain_dict:
        for w in DOMAIN_WORDS:
            if w:
                jieba.add_word(w, freq=5000)


TOKEN_RE = re.compile(r"^[\w\u4e00-\u9fff%\.\-]+$")
STOP = set("的了和与及或在是有为以其之一个这那怎么什么哪些啥吗呢吧啊也就都还又再更很太"
           "请问如何怎样为什么哪个多少")


def tokenize(text):
    out = []
    for t in jieba.lcut(text):
        t = t.strip().lower()
        if not t or t in STOP:
            continue
        if not TOKEN_RE.match(t):
            continue
        if len(t) == 1 and not t.isdigit():
            continue
        out.append(t)
    return out


class BM25:
    def __init__(self, docs_tokens):
        self.N = len(docs_tokens)
        self.df = Counter()
        self.tf = []
        self.dl = []
        for toks in docs_tokens:
            c = Counter(toks)
            self.tf.append(c)
            self.dl.append(len(toks))
            for t in c:
                self.df[t] += 1
        self.avgdl = sum(self.dl) / max(self.N, 1) or 1.0
        self.idf = {}
        for t, n in self.df.items():
            self.idf[t] = math.log((self.N - n + 0.5) / (n + 0.5) + 1.0)

    def search(self, qtokens, k=TOP_K):
        scores = []
        for i, c in enumerate(self.tf):
            s = 0.0
            dl = self.dl[i]
            for t in qtokens:
                f = c.get(t, 0)
                if f == 0:
                    continue
                idf = self.idf.get(t)
                if idf is None:
                    continue
                s += idf * (f * (K1 + 1)) / (f + K1 * (1 - B + B * dl / self.avgdl))
            scores.append((s, i))
        scores.sort(key=lambda x: (-x[0], x[1]))
        return [i for s, i in scores[:k] if s > 0]


def load_questions():
    path = os.path.join(EVAL_DIR, "03_固定问题集.csv")
    qs = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if not r.get("query"):
                continue
            gold = [g.strip() for g in r["gold_ids"].split("|") if g.strip()]
            qs.append({"intent": r["intent"], "style": r["style"], "query": r["query"],
                       "gold": gold, "note": r.get("note", "")})
    return qs


def load_synonyms():
    path = os.path.join(EVAL_DIR, "03_同义词扩展词典.json")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def expand_query(q, syn):
    extra = []
    for k, vs in syn.items():
        if k in q:
            extra.extend(vs)
    return q + (" " + " ".join(extra) if extra else ""), extra


def run():
    corpus = load_corpus()
    ids = [c["chunk_id"] for c in corpus]
    id2idx = {c: i for i, c in enumerate(ids)}
    texts = [c["title"] + "。" + c["text"] for c in corpus]
    questions = load_questions()
    syn = load_synonyms()

    variants = [
        ("A_vanilla", False, False),
        ("B_dict", True, False),
        ("C_expanded", True, True),
    ]

    all_rows = []
    summary = {}

    for name, use_dict, use_exp in variants:
        jieba.initialize()
        if use_dict:
            for w in DOMAIN_WORDS:
                if w:
                    jieba.add_word(w, freq=5000)
        docs_tokens = [tokenize(t) for t in texts]
        bm = BM25(docs_tokens)

        rows = []
        for q in questions:
            qt = q["query"]
            extra = []
            if use_exp:
                qt, extra = expand_query(qt, syn)
            toks = tokenize(qt)
            hits = bm.search(toks, TOP_K)
            hit_ids = [ids[i] for i in hits]
            gold = set(q["gold"])
            rank = next((r for r, cid in enumerate(hit_ids, 1) if cid in gold), None)
            rows.append({
                "variant": name, "intent": q["intent"], "style": q["style"],
                "query": q["query"], "expanded_terms": "/".join(extra),
                "hit@1": 1 if (hit_ids[:1] and hit_ids[0] in gold) else 0,
                "hit@3": 1 if any(c in gold for c in hit_ids[:3]) else 0,
                "hit@5": 1 if any(c in gold for c in hit_ids[:5]) else 0,
                "first_rank": rank if rank else "",
                "rr": round(1.0 / rank, 4) if rank else 0.0,
                "top5": " > ".join(hit_ids),
                "top5_all_gold": 1 if all(c in gold for c in hit_ids) else 0,
            })
        all_rows.extend(rows)

        # 汇总
        for style in ("术语版", "口语版"):
            sub = [r for r in rows if r["style"] == style]
            n = len(sub)
            summary[(name, style)] = {
                "n": n,
                "hit@1": sum(r["hit@1"] for r in sub) / n,
                "hit@3": sum(r["hit@3"] for r in sub) / n,
                "hit@5": sum(r["hit@5"] for r in sub) / n,
                "mrr": sum(r["rr"] for r in sub) / n,
                "零召回": sum(1 for r in sub if not r["first_rank"]),
            }

    out_csv = os.path.join(RES_DIR, f"04_BM25逐题结果{TAG}.csv")
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)

    # 汇总 CSV
    srows = []
    for (name, style), v in summary.items():
        srows.append({"方案": name, "问法": style, "题数": v["n"],
                      "Hit@1": f"{v['hit@1']:.1%}", "Hit@3": f"{v['hit@3']:.1%}",
                      "Hit@5": f"{v['hit@5']:.1%}", "MRR": f"{v['mrr']:.3f}",
                      "完全未命中题数": v["零召回"]})
    s_csv = os.path.join(RES_DIR, f"04_BM25汇总{TAG}.csv")
    with open(s_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(srows[0].keys()))
        w.writeheader()
        w.writerows(srows)

    # 控制台
    print("\n=== BM25 汇总（%d 个 chunk，%d 道题）===" % (len(corpus), len(questions) // 2))
    print(f"{'方案':<12}{'问法':<8}{'Hit@1':>8}{'Hit@3':>8}{'Hit@5':>8}{'MRR':>8}{'零召回':>8}")
    for (name, style), v in summary.items():
        print(f"{name:<12}{style:<8}{v['hit@1']:>7.1%}{v['hit@3']:>8.1%}{v['hit@5']:>8.1%}{v['mrr']:>8.3f}{v['零召回']:>8}")

    # 每个方案下口语版失败的具体题目（用于报告）
    print("\n=== 口语版逐题（C 方案）===")
    for r in [x for x in all_rows if x["variant"] == "C_expanded" and x["style"] == "口语版"]:
        mark = "OK " if r["hit@5"] else "MISS"
        print(f"{mark} {r['intent']:<8} rank={r['first_rank'] or '-':<3} {r['query']}  → {r['top5'][:110]}")

    print("\n输出：", out_csv)


if __name__ == "__main__":
    run()
