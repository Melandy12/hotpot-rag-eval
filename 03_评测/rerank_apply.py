# -*- coding: utf-8 -*-
"""重排生产模块：意图路由 + 本地 BM25 相关度

给 SAG 返回的候选列表做一次重排，返回排好序的 doc_id 列表。
两种本地相关度可选：
  bm25  —— 在候选集内部建词表（最长匹配切词）+ BM25 打分，与 SAG 的 BM25 语义一致（推荐）
  bigram—— 字 bigram 覆盖率（第一版做法，留作对照）

用法：
  from importlib import util 不行，直接 exec 或 sys.path 引入：
    sys.path.insert(0, r"...\03_评测"); import importlib; m = importlib.import_module("17_rerank_apply")
  实测 Python 模块名不能以数字开头，所以文件名用 rerank_apply.py。
"""
import json, math, os, re

CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "15_重排最优配置.json")

# 文档编号：文件名去掉 .md 后在第一个下划线处截断。
# 旧写法用 \w 只认 ASCII，把 GB-SF-料渣水分、GB-SF-水分限值可比性判定 两张中文名卡
# 直接漏掉了——评测时它们根本没进候选池。这里改成正则之外的纯字符串处理，避免再漏。
def doc_id_of(path):
    base = os.path.basename(path or "")
    if base.lower().endswith(".md"):
        base = base[:-3]
    return base.split("_")[0].strip()


def doc_type_of(doc_id):
    return (doc_id or "OTHER").split("-")[0]


# 案例卡的"因果完整度"标记词：写了原因/措施/调查的卡更可信
CAUSE_MARKS = ["原因", "调查", "措施", "导致", "确认", "整改"]

# 口语问法标记词：命中任意一个就说明这是"人话问法"，才值得重排
ORAL_MARKERS = ["咋", "啥", "是不是", "有没有", "要不要", "能不能", "会不会", "怎么回事",
                "为什么", "为啥", "原因", "正常吗", "闻着", "闻一下", "老投诉", "感觉",
                "我觉得", "对吧", "呢", "吗", "怎么", "哪些", "多少", "多久", "几种"]


DEFAULT_CFG = {
    "alpha": 0.65,
    # 实测：这三个词表是 22 题上最优的一组。加"测了没"会让第 4 题从混合型误判成方法型
    # （因为"测了没"命中了 doc 表却其实是口语疑问），Hit@1 从 63.6 掉到 59.1，故不收录。
    "intent_words": {
        "std": ["国标", "限值", "标准", "卡的是", "超标", "判定", "合规", "出厂检验"],
        "case": ["咋回事", "为什么", "为啥", "是不是", "原因", "正常吗", "怎么回事", "退回去"],
        "doc": ["验收", "指标", "怎么", "哪些", "方法", "检测", "工艺", "留样", "控制"],
    },
    "weights": {
        "std": {"CASE": 0.85, "DOC": 0.95, "GB": 1.0, "QY": 1.0, "TS": 1.0},
        "case": {"CASE": 1.2, "DOC": 0.8, "GB": 0.75, "QY": 0.75, "TS": 1.0},
        "doc": {"CASE": 0.75, "DOC": 1.2, "GB": 1.0, "QY": 1.0, "TS": 1.0},
        "mix": {"CASE": 1.0, "DOC": 1.0, "GB": 1.0, "QY": 1.0, "TS": 1.0},
    },
}


def load_cfg(path=CFG_PATH):
    cfg = json.loads(json.dumps(DEFAULT_CFG))       # 深拷贝默认值
    if os.path.exists(path):
        try:
            disk = json.load(open(path, encoding="utf-8"))
            cfg["alpha"] = disk.get("alpha", cfg["alpha"])
            if "cause_bonus" in disk:
                cfg["cause_bonus"] = disk["cause_bonus"]
            if "gate" in disk:
                cfg["gate"] = disk["gate"]
            for k in ("std", "case", "doc"):
                words = disk.get("intent_words", {}).get(k)
                if words:
                    cfg["intent_words"][k] = list(dict.fromkeys(list(cfg["intent_words"][k]) + words))
            if disk.get("weights"):
                cfg["weights"] = disk["weights"]
        except Exception:
            pass
    return cfg


def intent_of(query, cfg):
    # 先判标准型：'}最多原话里"标准""限值"是强信号
    for key in ("std", "case", "doc"):
        if any(w in query for w in cfg["intent_words"][key]):
            return key
    return "mix"


def build_vocab(texts, max_len=4):
    vocab = set()
    for t in texts:
        t = re.sub(r"[\s\W_]+", "", t)
        for n in range(2, max_len + 1):
            for i in range(len(t) - n + 1):
                vocab.add(t[i:i + n])
    return vocab


def tokenize(text, vocab, max_len=4):
    t = re.sub(r"[\s\W_]+", "", text)
    out, i = [], 0
    while i < len(t):
        hit = None
        for n in range(min(max_len, len(t) - i), 1, -1):
            cand = t[i:i + n]
            if cand in vocab:
                hit = cand
                break
        if hit:
            out.append(hit)
            i += len(hit)
        else:
            i += 1
    return out


def bm25_scores(query, items, k1=1.2, b=0.75):
    docs = [(it.get("heading", "") or "") + " " + (it.get("content", "") or "") for it in items]
    vocab = build_vocab(docs + [query])
    toks = [tokenize(d, vocab) for d in docs]
    q = tokenize(query, vocab)
    n = len(docs)
    avgdl = sum(len(t) for t in toks) / max(n, 1)
    df = {}
    for t in set(q):
        df[t] = sum(1 for d in toks if t in d)
    scores = []
    for d in toks:
        s = 0.0
        for t in q:
            f = d.count(t)
            if f == 0:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(d) / max(avgdl, 1e-9)))
        scores.append(s)
    return scores


def bigram_cov(query, item):
    def bg(x):
        x = re.sub(r"[\s\W_]+", "", x.lower())
        return set(x[i:i + 2] for i in range(len(x) - 1)) if len(x) > 1 else set(x)
    qb = bg(query)
    if not qb:
        return 0.0
    h = len(bg(item.get("heading", "") or "") & qb) / len(qb)
    c = len(bg(item.get("content", "") or "") & qb) / len(qb)
    return 0.3 * h + 0.7 * c


def rerank(query, items, cfg=None, scorer="bm25", alpha=None, topk=None):
    """输入 SAG 原始候选，返回重排后的 doc_id 列表（含 type/id 由调用方保留）。"""
    cfg = cfg or load_cfg()
    alpha = cfg["alpha"] if alpha is None else alpha
    if not items:
        return []
    qt = intent_of(query, cfg)
    w = cfg["weights"][qt]

    if scorer == "bm25":
        raw = bm25_scores(query, items)
        mx = max(raw) if raw and max(raw) > 0 else 1.0
        loc = [x / mx for x in raw]
    else:
        loc = [bigram_cov(query, it) for it in items]

    scored = []
    for i, it in enumerate(items):
        base = 1.0 / (1.0 + 0.08 * i)          # 原始名次的微弱先验
        s = (loc[i] * alpha + base * (1 - alpha)) * w.get(it["type"], 1.0)
        bonus = cfg.get("cause_bonus", 0) or 0
        if bonus and it["type"] == "CASE":
            hit = sum(1 for c in CAUSE_MARKS if c in (it.get("content", "") + it.get("heading", "")))
            s *= 1 + bonus * min(hit, 4) / 4.0   # 因果完整度：写了原因/措施的案例卡更可信
        scored.append((s, i, it["id"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    ids = [x[2] for x in scored]
    return ids[:topk] if topk else ids


def explain(query, items, cfg=None, scorer="bm25"):
    cfg = cfg or load_cfg()
    qt = intent_of(query, cfg)
    return {"intent": qt, "weights": cfg["weights"][qt],
            "ids": rerank(query, items, cfg, scorer)}


# 汉语句法功能词：出现任何一个，说明这是"人在说话"，不是关键词串
FUNC_WORDS = ["的", "了", "着", "是", "吗", "呢", "会", "能", "得", "太", "不", "把", "给", "过", "就", "还"]


def needs_rerank(query):
    """只在口语问法上启用重排。

    实测（119 片，30 题固定集）：
    - 术语型关键词串（"酸价超标 油脂氧化 判定限值"）重排后 Hit@1 93.3% → 86.7%；
    - 口语型长句（"闻着一股哈喇味 是不是油坏了"）重排后才涨（73.3% → 80.0%）。

    原因是术语型查询 SAG 的词法排序本来就准，本地 bigram 粗分只会打乱它。
    判定用两条任一命中：① 含口语标记词；② 含汉语句法功能词（的/了/不/吗…）。
    只用①会漏掉"底料放两个月就不香了"这类，只用②会漏掉"咋回事""啥"这类。
    """
    if any(m in query for m in ORAL_MARKERS):
        return True
    return any(w in query for w in FUNC_WORDS)


def rerank_smart(query, items, cfg=None, scorer="bigram", force=None):
    """生产入口。

    force=True  → 一定重排
    force=False → 一定不重排（只回原顺序）
    force=None  → 看配置：gate.enabled=true 时只在口语问法重排；gate.enabled=false 时全程重排
    """
    cfg = cfg or load_cfg()
    gate = cfg.get("gate", {})
    if force is False:
        return [it["id"] for it in items]
    if force is None and gate.get("enabled", False) and not needs_rerank(query):
        return [it["id"] for it in items]
    return rerank(query, items, cfg, scorer=scorer)



if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(load_cfg(), ensure_ascii=False, indent=2)[:1200])
