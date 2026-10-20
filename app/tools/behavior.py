"""
行为层 —— 判断评论区「是不是被灌水/刷评」，定位异常簇并给出可核对的证据。

支持三种输入格式（自动识别）：
  1. 每行一条：纯文本
  2. 制表符/逗号分隔：时间 \t 账号 \t 内容（顺序不限，自动嗅探）
  3. 带 @ 昵称 或 "昵称：内容"
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

import numpy as np

TIME_RE = re.compile(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?|\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2})")
POS_WORDS = ["好用", "喜欢", "推荐", "回购", "惊喜", "满意", "棒", "绝了", "爱了", "值", "划算", "有效"]
NEG_WORDS = ["难用", "踩雷", "失望", "退货", "差评", "鸡肋", "过敏", "刺激", "假", "骗", "后悔"]


def _parse_line(line: str) -> dict[str, str]:
    line = line.strip()
    if not line:
        return {}
    rec = {"text": line, "time": "", "user": ""}

    m = TIME_RE.search(line)
    if m:
        rec["time"] = m.group(1)
        line = line.replace(m.group(1), " ")
        rec["text"] = line.strip(" \t,，|")

    # 制表符 / 竖线 / 逗号分隔
    for sep in ("\t", "|"):
        if sep in line:
            parts = [p.strip() for p in line.split(sep) if p.strip()]
            if len(parts) >= 2:
                rec["user"], rec["text"] = parts[0], parts[-1]
                return rec

    # "昵称：内容"
    m = re.match(r"^([^\s：:]{1,18})[：:]\s*(.+)$", line)
    if m and len(m.group(2)) > 3:
        rec["user"], rec["text"] = m.group(1), m.group(2)
        return rec

    return rec


def _shingles(text: str, k: int = 3) -> set[str]:
    t = re.sub(r"\s+", "", text)
    return {t[i:i + k] for i in range(max(0, len(t) - k + 1))}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _nickname_anomaly(name: str) -> float:
    """昵称异常度：随机串、纯数字、英文+数字混排、营销号后缀。"""
    if not name:
        return 0.0
    s = 0.0
    if re.search(r"\d{4,}$", name):
        s += 0.35
    if re.fullmatch(r"[a-zA-Z0-9_]{6,}", name) and re.search(r"\d", name):
        s += 0.35
    if re.search(r"(旗舰店|官方|专营|代购|批发|客服)", name):
        s += 0.4
    ent = -sum((c / max(len(name), 1)) * math.log2(c / max(len(name), 1)) for c in Counter(name).values())
    if ent > 4.0:
        s += 0.2
    return min(1.0, s)


def _sentiment(text: str) -> int:
    p = sum(w in text for w in POS_WORDS)
    n = sum(w in text for w in NEG_WORDS)
    return 1 if p > n else (-1 if n > p else 0)


def analyze_comments(raw: str) -> dict[str, Any]:
    rows = [r for r in (_parse_line(l) for l in raw.splitlines()) if r and len(r.get("text", "")) >= 2]
    n = len(rows)
    if n < 5:
        return {"available": False, "score": 0.0, "reason": "评论条数不足 5 条，无法做群体模式分析"}

    texts = [r["text"] for r in rows]
    users = [r.get("user", "") for r in rows]
    times = [r.get("time", "") for r in rows]

    # ---- 1. 模板相似度聚类
    sh = [_shingles(t) for t in texts]
    sim = np.zeros((n, n), np.float32)
    for i in range(n):
        for j in range(i + 1, n):
            v = _jaccard(sh[i], sh[j])
            sim[i, j] = sim[j, i] = v

    from sklearn.cluster import DBSCAN
    labels = DBSCAN(eps=0.55, min_samples=2, metric="precomputed").fit_predict(1.0 - sim)

    clusters = []
    for lb in sorted(set(labels)):
        if lb == -1:
            continue
        idx = [i for i, x in enumerate(labels) if x == lb]
        if len(idx) < 2:
            continue
        sub = sim[np.ix_(idx, idx)]
        off = sub[~np.eye(len(idx), dtype=bool)] if len(idx) > 1 else np.array([0.0])
        clusters.append({
            "id": f"c{int(lb)}",
            "size": len(idx),
            "avg_similarity": round(float(off.mean()), 3),
            "samples": [texts[i][:46] for i in idx[:4]],
            "times": [times[i] for i in idx if times[i]][:6],
        })
    clusters.sort(key=lambda c: -c["size"])

    clustered = sum(c["size"] for c in clusters)
    template_ratio = clustered / n

    # ---- 2. 时间规律
    timing = {"available": False}
    parsed = [t for t in times if t]
    if len(parsed) >= 3:
        try:
            import pandas as pd
            ts = pd.to_datetime(pd.Series(parsed), errors="coerce", format="mixed").dropna().sort_values()
            if len(ts) >= 3:
                gaps = ts.diff().dropna().dt.total_seconds().values
                gaps = gaps[gaps >= 0]
                if len(gaps) >= 2:
                    cv = float(np.std(gaps) / max(np.mean(gaps), 1e-6))
                    span_min = float((ts.iloc[-1] - ts.iloc[0]).total_seconds() / 60)
                    timing = {
                        "available": True,
                        "count": int(len(ts)),
                        "span_minutes": round(span_min, 1),
                        "gap_cv": round(cv, 3),
                        "median_gap_s": round(float(np.median(gaps)), 1),
                        "verdict": "高度规律（疑似定时投放）" if cv < 0.15 else ("较集中" if cv < 0.5 else "分布自然"),
                    }
        except Exception as e:
            timing = {"available": False, "reason": f"时间解析失败: {e}"}

    # ---- 2b. 短时爆发：任意 10 分钟窗口内集中了多少条
    burst = 0.0
    if timing.get("available") and len(parsed) >= 5:
        try:
            import pandas as pd
            ts = pd.to_datetime(pd.Series(parsed), errors="coerce", format="mixed").dropna().sort_values()
            ts = ts.reset_index(drop=True)
            w = pd.Timedelta(minutes=10)
            best = 0
            j = 0
            for i in range(len(ts)):
                while ts.iloc[i] - ts.iloc[j] > w:
                    j += 1
                best = max(best, i - j + 1)
            burst = best / len(ts)
        except Exception:
            burst = 0.0
    timing["burst_ratio"] = round(burst, 3)
    # 措辞要和结论一致：短时集中投放优先于"分布自然"
    if burst >= 0.50:
        timing["verdict"] = f"短时集中投放（{burst*100:.0f}% 的评论落在同一 10 分钟窗口）"
    elif timing.get("gap_cv", 9) < 0.15:
        timing["verdict"] = "高度规律（疑似定时投放）"
    elif timing.get("gap_cv", 9) < 0.50:
        timing["verdict"] = "发布较集中"
    else:
        timing["verdict"] = "整体分布自然，但存在局部集中"


    # ---- 3. 情感一致性
    sents = [_sentiment(t) for t in texts]
    pos_ratio = sum(1 for s in sents if s > 0) / n
    neg_ratio = sum(1 for s in sents if s < 0) / n
    same_polarity = max(pos_ratio, neg_ratio)
    avg_len = float(np.mean([len(t) for t in texts]))
    short_ratio = sum(1 for t in texts if len(t) <= 15) / n

    # ---- 4. 账号画像
    acct_scores = [(_nickname_anomaly(u), u) for u in users if u]
    acct_ratio = float(np.mean([s > 0.5 for s, _ in acct_scores])) if acct_scores else 0.0
    suspicious_accounts = sorted([{"user": u, "score": round(s, 2)} for s, u in acct_scores if s > 0.5],
                                 key=lambda x: -x["score"])[:6]

    # ---- 5. 综合评分
    s_template = min(1.0, max(0.0, (template_ratio - 0.10) / 0.55))
    s_timing = 0.0
    if timing.get("available"):
        s_timing = min(1.0, max(0.0, (0.55 - timing["gap_cv"]) / 0.45))
        if timing["span_minutes"] < 90 and timing["count"] > 15:
            s_timing = min(1.0, s_timing + 0.15)
    s_burst = min(1.0, max(0.0, (burst - 0.35) / 0.45))
    s_timing = max(s_timing, s_burst)
    s_sentiment = min(1.0, max(0.0, (same_polarity - 0.75) / 0.25)) * min(1.0, max(0.0, (26 - avg_len) / 16))
    s_account = min(1.0, acct_ratio * 1.6)

    score = 0.50 * s_template + 0.28 * s_timing + 0.12 * s_sentiment + 0.10 * s_account

    # ---- 6. 散点图坐标（TF-IDF + SVD 降到 2D）
    scatter = []
    try:
        import warnings
        warnings.filterwarnings("ignore")   # 评论完全相同时 SVD 会告警，属正常情况
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        X = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), min_df=1).fit_transform(texts)
        Z = TruncatedSVD(n_components=2, random_state=0).fit_transform(X)
        for i, (x, y) in enumerate(Z):
            scatter.append({"x": round(float(x), 3), "y": round(float(y), 3),
                            "c": int(labels[i]), "len": len(texts[i])})
    except Exception:
        pass

    return {
        "available": True,
        "score": round(float(min(1.0, score)), 4),
        "total": n,
        "template_ratio": round(template_ratio, 3),
        "clusters": clusters[:6],
        "timing": timing,
        "sentiment": {"pos": round(pos_ratio, 3), "neg": round(neg_ratio, 3),
                      "same_polarity": round(same_polarity, 3)},
        "length": {"avg": round(avg_len, 1), "short_ratio": round(short_ratio, 3)},
        "accounts": {"anomaly_ratio": round(acct_ratio, 3), "suspicious": suspicious_accounts},
        "sub_scores": {"模板化": round(s_template, 3), "时间规律": round(s_timing, 3),
                       "清一色": round(s_sentiment, 3), "账号异常": round(s_account, 3)},
        "scatter": scatter,
        "timeline": [{"t": t, "usr": u} for t, u in zip(times, users) if t],
        "labels": [int(x) for x in labels],
    }
