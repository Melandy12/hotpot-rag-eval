# -*- coding: utf-8 -*-
"""本地问答链路：SAG 检索（BM25+JEV）→ 本地 Qwen2.5-7B 生成带引用答案
用法: python answer_local.py "问题"
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rerank_apply import rerank_smart, needs_rerank, doc_id_of, doc_type_of, load_cfg      # noqa: E402

SAG = os.environ.get("ZJ_SAG_BIN", "<请配置 SAG 命令行路径 sag.exe>")
KB = os.path.join(ROOT, '01_knowledge_base_v2_sag')
OLLAMA = "http://127.0.0.1:11434/v1/chat/completions"
MODEL = "qwen25-7b-local"


SYN = os.path.join(ROOT, '03_评测/03_同义词扩展词典.json')


def expand(query, limit=2):
    """把口语词按词典展开成语料里真实存在的规范词

    limit=2 是评测定下来的 K=2（只取词典里排前两位的扩展词）。取全部扩展词会把
    无关候选（"黑色碎屑""色素"）拉进来，反而把真正的案例挤出前五。
    """
    with open(SYN, "r", encoding="utf-8") as f:
        d = json.load(f)
    terms = []
    for key, vals in d.items():
        if key.startswith("_"):
            continue
        if key in query:
            terms.extend(vals)
    terms = [t for t in dict.fromkeys(terms) if t not in query]
    return terms[:limit]


def retrieve(query, k=5, cand=15, use_rerank=True):
    """检索：SAG 取候选 → 重排闸门（口语问法才重排）→ 取前 k 条做证据"""
    terms = expand(query)
    q = query + (" " + " ".join(terms) if terms else "")
    if terms:
        print("扩展词:", " ".join(terms), flush=True)
    out = subprocess.run([SAG, q, KB, "--max-results", str(cand), "--json"],
                         capture_output=True, timeout=600)
    txt = out.stdout.decode("utf-8", "ignore").strip()
    if not txt:
        raise RuntimeError("检索无输出: " + out.stderr.decode("utf-8", "ignore")[:300])
    start = txt.find("{")
    data = json.loads(txt[start:])
    items = []
    for r in data.get("results", data.get("chunks", []))[:cand]:
        path = r.get("filepath") or r.get("path") or ""
        did = doc_id_of(path)
        items.append({
            "id": did,
            "type": doc_type_of(did),
            "path": os.path.basename(path),
            "heading": r.get("heading", ""),
            "content": (r.get("content") or "")[:1200],
        })
    if use_rerank and len(items) > 1:
        try:
            ids = rerank_smart(q, items)
            order = {did: i for i, did in enumerate(ids)}
            items = sorted(items, key=lambda it: order.get(it["id"], 999))
            gate_on = bool(load_cfg().get("gate", {}).get("enabled", False))
            state = "闸门关闭，用原序" if (gate_on and not needs_rerank(q)) else (
                "闸门开启，按口语判定" if gate_on else "全程启用")
            print("重排: %s（%d 候选）" % (state, len(ids)), flush=True)
        except Exception as e:
            print("重排跳过:", e, flush=True)
    items, note = usage_side_reorder(query, items)
    if note:
        print(note, flush=True)
    items, wnote = water_caliber_boost(query, items)
    if wnote:
        print(wnote, flush=True)
    return items[:k]


def usage_side_reorder(q, items):
    """按提问所处环节，把「原因类型」对口的案例排到前面

    两个环节的现象词高度相似（都含"发黑""变色""不香"），纯词法分不开，
    但标题里的 `原因：` 字段分得开：

    - **使用端**（煮 / 加热 / 下锅 / 涮）：原因几乎都在工艺侧
      （混入水分、炒制时间不足、乳化不彻底），排在光照、包装、储运类之前。
    - **货架端**（放两个月 / 储存 / 保质期 / 久了）：原因几乎都在储运与氧化侧
      （油脂氧化、透氧包装、光照降解、吸潮），排在炒制、均质、配比类之前。

    只在案例卡之间重排，组内保持原顺序，标准/文献不参与分组。
    """
    PROC = ("水分", "炒制", "工艺", "灭菌", "均质", "配比", "真空", "温度", "渣", "乳化")
    STORE = ("光照", "储存", "货架", "物流", "运输", "包装", "灯", "冷藏")

    def cause_of(it):
        m = re.search(r"原因[^｜|]*[:：]([^｜|]+)", it["heading"] or "")
        return m.group(1) if m else ""

    usage = re.search(r"煮|加热|下锅|涮|开锅|烧|一煮", q)
    shelf = re.search(r"放[了]?[一三两几\d]+个|两个月|三个月|存放|储存|保质期|货架|久了|时间长了|不香", q)

    if usage:
        proc, rest, store = [], [], []
        for it in items:
            c = cause_of(it)
            if it["type"] != "CASE" or not c:
                rest.append(it)
            elif any(w in c for w in PROC) and not any(w in c for w in STORE):
                proc.append(it)
            elif any(w in c for w in STORE):
                store.append(it)
            else:
                rest.append(it)
        out = proc + rest + store
        tag = "使用端→工艺归因优先"
    elif shelf:
        keep = ("氧化", "哈喇", "透氧", "包装", "光照", "储存", "货架", "冷藏",
                "降解", "劣变", "挥发", "吸潮", "湿度", "损耗", "衰减")
        # 问"不香/风味"时，色素氧化、光照变色这类颜色归因不算对口答案
        flavor = re.search(r"不香|香气|风味|味道|香味", q)
        coloronly = ("色素", "光照", "颜色", "发暗", "无光泽")
        a, b, c3 = [], [], []
        for it in items:
            cz = cause_of(it)
            if it["type"] != "CASE" or not cz:
                b.append(it)
            elif any(w in cz for w in keep) and not (flavor and any(w in cz for w in coloronly)):
                a.append(it)
            elif any(w in cz for w in PROC):
                c3.append(it)
            else:
                b.append(it)
        out = a + b + c3
        tag = "货架端→氧化储运归因优先"
    else:
        return items, None

    # 只让案例卡在"案例卡自己的位次"之间换，文献/标准/时序卡的位次完全不动
    # （否则规则会把 DOC/GB 挤到前面，gold 被顶出前五，指标和答案两头都不讨好）
    slots = [i for i, it in enumerate(items) if it["type"] == "CASE"]
    cases = [it for it in out if it["type"] == "CASE"]
    res = list(items)
    for idx, it in zip(slots, cases):
        res[idx] = it
    out = res

    moved = out[0]["id"] != items[0]["id"]
    return out, ("%s，案例卡首位 %s" % (tag, out[0]["id"]) if moved else None)


def water_caliber_boost(q, items):
    """问"水分限值/超标"时，强制把两张口径卡提到最前

    领域事实：水分在国内没有统一红线（15 条企标 10~45 不等），红太阳企标本身不设水分，
    唯一能引的是 GB/T 45662-2025 表 1 且只能"参照"。纯词法检索经常只召回"限值从哪来"的解释卡，
    7B 就会答成"没有限值，建议咨询生产商"——少了两件必须说的话：参照值是多少、为什么不判定。
    所以这里用确定性规则把口径卡顶上去，跟环节归因同理，不依赖模型。
    """
    if not re.search(r"水分", q):
        return items, None
    if not re.search(r"限值|超标|多少|判定|合格|上限|临界", q):
        return items, None
    WANT = ("GB-SF-料渣水分", "GB-T-45662-2025")
    have = [it for it in items if any(w in it["id"] or w in str(it.get("path", "")) for w in WANT)]
    if not have:
        return items, None
    rest = [it for it in items if it not in have]
    # 同卡多片只保留第一片，避免一张卡占满证据位
    seen, keep = set(), []
    for it in have:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        keep.append(it)
    out = keep + rest
    out = out[:len(items)]
    return out, "水分口径→强制置顶 %s" % "、".join(it["id"] for it in keep)


def build_prompt(q, items):
    ctx = "\n\n".join("[证据%d] 文件：%s\n标题：%s\n正文：\n%s" % (i + 1, it["path"], it["heading"], it["content"])
                      for i, it in enumerate(items))
    sys_msg = ("你是火锅底料工艺与质量分析助手。下面给你从知识库检索到的证据，请直接回答用户的问题。\n"
               "规则：\n"
               "1) 先用一到三句话给结论，再列依据（每条依据后面标注【证据N】），最后给可执行的措施。\n"
               "2) 证据中与问题相关的条文、原因、措施，即使措辞与提问不同（例如“颜色发黑严重”“底部黑色碎屑”可以用来解释“汤发黑”），"
               "也必须采用；“火锅底料属于复合调味料”这类标准适用性表述要直接用。\n"
               "3) 多条证据都沾边时，优先引用标题里写清了“原因”和“措施”的那几条，只描述现象、没给原因的证据放后面或不用。\n"
               "4) 只有当全部证据都与问题无关时，才回复“知识库中没有对应记录”。\n"
               "6) 如果多条证据都给出了原因，要把原因逐条列全（通常 3~5 条），不要只挑一两条就下结论。\n"
               "7) 问“某个指标有没有限值/超多少算超标”时，必须按这个顺序说：先写“限值未核定（不判定）”，"
               "再给参照值（写清依据的标准编号与表号），最后说清为什么不判定（标准实施日期晚于数据、或没有企业内控文件）。"
               "禁止只说“国标没规定、建议咨询生产商”。")
    user_msg = "证据材料：\n%s\n\n问题：%s" % (ctx, q)
    return sys_msg, user_msg


def ask(q):
    items = retrieve(q)
    sys_msg, user_msg = build_prompt(q, items)
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}],
        "temperature": 0.2,
        "max_tokens": 800,
    }
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read())
    return items, resp["choices"][0]["message"]["content"]


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "黑水是咋回事，煮出来汤是黑的"
    items, ans = ask(q)
    print("问题:", q)
    print("命中证据:")
    for i, it in enumerate(items, 1):
        print("  [证据%d] %s | %s" % (i, it["path"], it["heading"]))
    print("\n答案:\n" + ans)
