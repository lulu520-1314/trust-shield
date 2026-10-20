"""
语义层 —— 判断一段种草文案「是不是模板化/AI 生成」，并且说清楚是哪几条特征导致的。

不做黑盒分类器：所有分数都来自可数的文体特征，
前端会把每个特征的「贡献度」画成条形图，评委能逐条对照原文。

（说明：权重为人工标定，用于相对排序而非绝对概率；报告中会明确标注这一点。）
"""
from __future__ import annotations

import re
from typing import Any

# 模型化写作的连接词（AI 与模板软文高频）
CONNECTORS = ["首先", "其次", "然后", "最后", "总之", "综上", "总而言之", "值得一提的是",
              "不仅如此", "与此同时", "此外", "因此", "从而", "不仅", "而且", "无论是", "还是"]

# 种草模板短语（软文与 AI 都爱用，但堆叠过多即异常）
TEMPLATES = ["绝绝子", "闭眼入", "姐妹们", "宝子们", "亲测", "回购", "种草", "踩雷", "安利",
             "入股不亏", "无限回购", "真的会谢", "谁懂啊", "好用到哭", "yyds", "天花板",
             "可以说是", "不得不说", "讲真", "实话实说", "真心推荐", "强烈推荐"]

# 夸张 / 绝对化用语
EXAGGERATION = ["最好", "第一", "顶级", "唯一", "独家", "史上", "永久", "彻底", "瞬间", "立刻",
                "马上", "秒变", "立竿见影", "根除", "100%", "百分百", "绝对"]

# 成分与具体信息词（真人种草更常提具体成分/规格）
INGREDIENTS = ["烟酰胺", "玻尿酸", "透明质酸", "水杨酸", "果酸", "神经酰胺", "视黄醇", "a醇",
               "维c", "vc", "胜肽", "多肽", "传明酸", "熊果苷", "角鲨烷", "氨基酸", "甘油",
               "二裂酵母", "积雪草", "咖啡因", "壬二酸", "spf", "pa+", "eGF".lower()]

UNIT_RE = re.compile(r"\d+\s*(ml|g|mg|元|块|天|周|个月|次|瓶|支|片|袋|%|度|倍)", re.I)
NUM_RE = re.compile(r"\d+(\.\d+)?")
SENT_SPLIT = re.compile(r"[。！？!?\n]+")


def _clip01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


def _density(count: float, per_chars: float) -> float:
    """每百字密度。"""
    return count / max(per_chars / 100.0, 0.1)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT.split(text) if len(s.strip()) >= 6]


def analyze_text(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    n = len(text)
    sents = split_sentences(text)
    if n < 20 or len(sents) < 1:
        return {"available": False, "score": 0.0,
                "reason": "文本过短（少于 20 字），无法提取文体特征"}

    lens = [len(s) for s in sents]
    mean_len = sum(lens) / len(lens)
    var = sum((x - mean_len) ** 2 for x in lens) / len(lens)
    sent_cv = (var ** 0.5) / max(mean_len, 1e-6)

    # 段落均齐度
    paras = [p for p in text.split("\n") if p.strip()]
    plens = [len(p) for p in paras]
    if len(plens) >= 2:
        pm = sum(plens) / len(plens)
        para_cv = (sum((x - pm) ** 2 for x in plens) / len(plens)) ** 0.5 / max(pm, 1e-6)
    else:
        para_cv = 0.5

    low = text.lower()
    conn = sum(low.count(w) for w in CONNECTORS)
    tmpl = sum(low.count(w) for w in TEMPLATES)
    exag = sum(low.count(w) for w in EXAGGERATION)
    ingr = sum(low.count(w) for w in INGREDIENTS)
    units = len(UNIT_RE.findall(text))
    numbers = len(NUM_RE.findall(text))
    first_person = sum(low.count(w) for w in ["我", "本人", "自己", "俺", "咱"])

    # 重复 4-gram 比例
    grams = [text[i:i + 4] for i in range(max(0, n - 3))]
    rep_ratio = 1 - (len(set(grams)) / max(len(grams), 1))

    # 词汇丰富度（去重字比例）
    ttr = len(set(text)) / max(n, 1)

    concreteness = _density(ingr + units + numbers, n)
    features = [
        {"key": "sent_cv", "name": "句长变异系数", "value": round(sent_cv, 3),
         "ai_score": _clip01((0.50 - sent_cv) / 0.35), "weight": 0.18,
         "note": "人写的句子长短错落；模板/AI 句式整齐"},
        {"key": "concreteness", "name": "信息具体度", "value": round(concreteness, 2),
         "ai_score": _clip01((2.2 - concreteness) / 2.2), "weight": 0.18,
         "note": "每百字提到的成分/规格/数字越多，越像真实体验"},
        {"key": "first_person", "name": "第一人称密度", "value": round(_density(first_person, n), 2),
         "ai_score": _clip01((1.6 - _density(first_person, n)) / 1.6), "weight": 0.15,
         "note": "真实种草大量使用「我用了两周…」"},
        {"key": "connectors", "name": "连接词密度", "value": round(_density(conn, n), 2),
         "ai_score": _clip01(_density(conn, n) / 3.0), "weight": 0.13,
         "note": "「首先/其次/总之」是结构化写作的标志"},
        {"key": "templates", "name": "模板短语密度", "value": round(_density(tmpl, n), 2),
         "ai_score": _clip01(_density(tmpl, n) / 4.0), "weight": 0.09,
         "note": "「绝绝子/闭眼入」等营销模板"},
        {"key": "repetition", "name": "4-gram 重复率", "value": round(rep_ratio, 3),
         "ai_score": _clip01(rep_ratio / 0.12), "weight": 0.08,
         "note": "AIGC 长文容易自我复读"},
        {"key": "ttr", "name": "用字丰富度", "value": round(ttr, 3),
         "ai_score": _clip01((0.55 - ttr) / 0.30), "weight": 0.07,
         "note": "用字越单一越像机器生成"},
        {"key": "para_cv", "name": "段落均齐度", "value": round(para_cv, 3),
         "ai_score": _clip01((0.55 - para_cv) / 0.45), "weight": 0.07,
         "note": "AI 偏爱每段长度相近的总分总结构"},
        {"key": "exaggeration", "name": "夸张用语密度", "value": round(_density(exag, n), 2),
         "ai_score": _clip01(_density(exag, n) / 2.5), "weight": 0.05,
         "note": "「秒变/彻底/100%」等绝对化表达"},
    ]

    # 只有一句话时，「句长变异」「段落均齐」没有统计意义，剔除后重新归一权重，
    # 否则单句文本会被这两项顶成"极端可疑"。
    if len(sents) < 2:
        features = [f for f in features if f["key"] not in ("sent_cv", "para_cv")]

    score = sum(f["weight"] * f["ai_score"] for f in features) / sum(f["weight"] for f in features)
    for f in features:
        f["contribution"] = round(f["weight"] * f["ai_score"], 4)

    top = sorted(features, key=lambda f: -f["contribution"])[:4]

    # 逐句打分：哪几句最"工程化"
    sent_rows = []
    for s in sents:
        c = sum(low2.count(w) for w in CONNECTORS for low2 in [s.lower()])
        t = sum(s.lower().count(w) for w in TEMPLATES)
        e = sum(s.lower().count(w) for w in EXAGGERATION)
        s_score = min(1.0, 0.45 * min(1.0, c / 1.0) + 0.3 * min(1.0, t / 2.0) + 0.25 * min(1.0, e / 2.0))
        if s_score > 0.15:
            sent_rows.append({"text": s[:80], "score": round(s_score, 3),
                              "hit": [w for w in CONNECTORS + TEMPLATES + EXAGGERATION if w in s.lower()]})
    sent_rows.sort(key=lambda r: -r["score"])

    return {
        "available": True,
        "short": n < 60 or len(sents) < 3,
        "score": round(score, 4),
        "chars": n,
        "sentences": len(sents),
        "features": features,
        "top_factors": [{"name": f["name"], "contribution": f["contribution"], "note": f["note"]} for f in top],
        "suspicious_sentences": sent_rows[:3],
        "caveat": "文体评分基于人工标定权重，用于相对排序；不作为单独判定依据。",
    }
