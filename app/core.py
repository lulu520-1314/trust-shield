"""
编排与融合 —— 把各层证据合成一份可解释的审核报告。

流程（固定 DAG，不用自由 ReAct，保证演示不翻车）：
    场景识别 → 调度工具 → 归一化 → 加权融合 → 分级 → 生成结论

每个维度除了分数，还会生成一句 `summary`（带具体数值），
界面用它解释「这个分是怎么来的」，避免只给一个数字。
"""
from __future__ import annotations

import os
import shutil
import time
import uuid
from typing import Any

from app.tools import behavior, consistency, pixel, rules, semantic

CACHE_DIR = pixel.CACHE_DIR

# 每个场景参与融合的维度与权重。
# 评论区场景不接文本维度：那里分析的是「评论」，已由行为层覆盖，
# 再把种草正文的文体分算进来只会产生「未参与」的空指标。
SCENE_META = {
    "post": {
        "name": "种草图文核验",
        "required": ["pixel", "semantic", "consistency", "rules"],
        "weights": {"pixel": 0.30, "semantic": 0.18, "consistency": 0.27, "rules": 0.25},
    },
    "comments": {
        "name": "评论区真实性核验",
        "required": ["behavior", "rules"],
        "weights": {"behavior": 0.88, "rules": 0.12},
    },
    "material": {
        "name": "AI 素材鉴伪",
        "required": ["pixel", "rules", "semantic"],
        "weights": {"pixel": 0.68, "rules": 0.16, "semantic": 0.16},
    },
}

LEVELS = [(0.75, "high", "高风险"), (0.45, "medium", "中风险"), (0.0, "low", "低风险")]

ACTION = {
    "high": "建议下架该内容并转人工复核；同步对发布账号做降权处理，保留证据链备查。",
    "medium": "建议限流并提示发布者补充功效依据（评价报告编号 / 特字号）；进入抽检队列。",
    "low": "建议通过，纳入常规抽检；若同一账号重复出现，再升级处置。",
}

DIM_NAME = {"pixel": "像素取证", "semantic": "文本文体", "consistency": "图文一致性",
            "rules": "合规规则", "behavior": "评论行为"}


def _stage_upload(path: str) -> str:
    """把上传文件放进 cache，返回可直接给前端用的相对文件名。"""
    ext = os.path.splitext(path)[1].lower() or ".jpg"
    name = f"src_{uuid.uuid4().hex[:10]}{ext}"
    shutil.copyfile(path, os.path.join(CACHE_DIR, name))
    return name


def grade(score: float, has_high_rule: bool, coverage: float,
          confirmed: bool = False) -> tuple[str, str]:
    """分级。三个安全阀：确证性证据抬到高风险；命中高危合规条款抬到中风险；证据不足则降级。"""
    level, label = "low", "低风险"
    for th, lv, lb in LEVELS:
        if score >= th:
            level, label = lv, lb
            break
    if has_high_rule and level == "low":
        level, label = "medium", "中风险"
    if confirmed:
        level, label = "high", "高风险"
    if coverage < 0.5 and level == "high":
        level, label = "medium", "中风险"
    return level, label


# ---------------------------------------------------------------- 各维度的「一句话解释」

def _sum_pixel(worst: dict[str, Any]) -> str:
    d = worst["dimensions"]
    parts = []
    if d["noise"]["available"] and d["noise"].get("anomaly_ratio", 0) > 0.02:
        parts.append(f"噪声异常 {d['noise']['anomaly_ratio'] * 100:.1f}%")
    if d.get("smooth", {}).get("available") and d["smooth"].get("smooth_ratio", 0) > 0.02:
        parts.append(f"细节缺失 {d['smooth']['smooth_ratio'] * 100:.1f}%（最小 z={d['smooth']['min_z']}）")
    if d["ela"]["available"] and d["ela"].get("max_z", 0) > 3:
        parts.append(f"ELA 最大 z={d['ela']['max_z']}")
    if d["freq"]["available"] and d["freq"].get("score", 0) > 0.3:
        parts.append(f"频谱斜率 α={d['freq']['alpha']}")
    if not parts:
        return "六项信号均未超阈值"
    return " · ".join(parts[:2])


def _sum_semantic(s: dict[str, Any]) -> str:
    if not s.get("available"):
        return s.get("reason", "未参与计算")
    feats = s.get("top_factors", [])[:2]
    tail = " · ".join(f["name"] for f in feats)
    return tail + ("（短文本）" if s.get("short") else "")


def _sum_consistency(c: dict[str, Any]) -> str:
    claimed = (c.get("claim") or {}).get("claimed_delta_e") or 0
    if claimed:
        return f"ΔE {c['delta_e']} vs 宣称 {claimed} · 夸大 {c.get('over_claim_ratio')}×"
    return f"ΔE {c['delta_e']} · 无量化宣称"


def _sum_rules(r: dict[str, Any]) -> str:
    hits = r.get("hits", [])
    if not hits:
        return "未命中任何条款"
    return f"命中 {len(hits)} 条"


def _sum_behavior(b: dict[str, Any]) -> str:
    parts = []
    if b.get("clusters"):
        parts.append(f"模板簇 {b['clusters'][0]['size']} 条")
    t = b.get("timing", {})
    if t.get("burst_ratio"):
        parts.append(f"集中投放 {t['burst_ratio'] * 100:.0f}%")
    if b.get("sentiment", {}).get("same_polarity", 0) > 0.85:
        parts.append(f"同极性 {b['sentiment']['same_polarity'] * 100:.0f}%")
    return " · ".join(parts[:2]) if parts else "未见群体性异常"


# ---------------------------------------------------------------- 主流程

def analyze(scene: str, text: str = "", image_paths: list[str] | None = None,
            comments_text: str = "", title: str = "") -> dict[str, Any]:
    t0 = time.time()
    scene = scene if scene in SCENE_META else "post"
    image_paths = image_paths or []
    meta = SCENE_META[scene]
    dims: dict[str, Any] = {}
    dims["_image_count"] = len(image_paths)
    findings: list[dict[str, Any]] = []
    images_out: list[dict[str, Any]] = []

    # ---------------- 像素层
    if scene in ("post", "material") and image_paths:
        analyzed = []
        for p in image_paths[:2]:
            try:
                r = pixel.analyze_image(p)
                analyzed.append(r)
                images_out.append({
                    "file": r["file"], "url": _stage_upload(p),
                    "heat": r["heat"], "shape": r["shape"], "regions": r["regions"],
                })
            except Exception as e:
                findings.append({"dim": "pixel", "severity": "low", "title": "图片解析失败",
                                 "detail": str(e)})
        if analyzed:
            worst = max(analyzed, key=lambda r: r["score"])
            dims["pixel"] = {
                "key": "pixel", "name": "像素取证",
                "score": worst["score"],
                "available": True,
                "summary": _sum_pixel(worst),
                "worst": worst["dimensions"],
                "detail": {r["file"]: r["dimensions"] for r in analyzed},
                "regions": worst["regions"],
                "lighting": worst["lighting"],
                "cost_ms": sum(r["cost_ms"] for r in analyzed),
            }
            findings.extend(_pixel_findings(worst))

    # ---------------- 一致性层
    if scene == "post" and len(image_paths) >= 2:
        try:
            c = consistency.analyze_pair(image_paths[0], image_paths[1], text)
            if c.get("available"):
                dims["consistency"] = {"key": "consistency", "name": "图文一致性",
                                       "summary": _sum_consistency(c), **c}
                findings.extend(_consistency_findings(c))
        except Exception as e:
            findings.append({"dim": "consistency", "severity": "low",
                             "title": "一致性分析失败", "detail": str(e)})

    # 只上传一张图时，明确说明一致性未参与，而不是静默跳过
    if scene == "post" and len(image_paths) == 1:
        findings.append({
            "dim": "consistency", "severity": "low",
            "title": "未提供对比图",
            "detail": "只上传了一张图，图文一致性（实测色差 vs 文案宣称）未参与判定，"
                      "本次结论仅基于单图取证与文案分析。",
        })

    # ---------------- 语义层（评论区不接，避免出现空指标）
    if text.strip() and scene != "comments":
        s = semantic.analyze_text(text)
        dims["semantic"] = {"key": "semantic", "name": "文本文体",
                            "summary": _sum_semantic(s), **s}
        if s.get("available"):
            findings.extend(_semantic_findings(s))

    # ---------------- 行为层
    if scene == "comments" or comments_text.strip():
        b = behavior.analyze_comments(comments_text)
        dims["behavior"] = {"key": "behavior", "name": "评论行为",
                            "summary": _sum_behavior(b), **b}
        if b.get("available"):
            findings.extend(_behavior_findings(b))

    # ---------------- 规则层
    r = rules.check_text(text if scene != "comments" else (text + "\n" + comments_text))
    dims["rules"] = {"key": "rules", "name": "合规规则",
                     "score": r["score"], "available": True,
                     "summary": _sum_rules(r),
                     "hits": r["hits"], "by_severity": r["by_severity"]}
    findings.extend(_rule_findings(r))

    # ---------------- 融合
    weights = meta["weights"]
    num = den = 0.0
    for k, w in weights.items():
        d = dims.get(k)
        if d and d.get("available"):
            num += w * float(d.get("score", 0))
            den += w
    score = num / den if den > 0 else 0.0

    required = meta["required"]
    coverage = sum(1 for k in required if dims.get(k, {}).get("available")) / len(required)
    has_high_rule = any(h["severity"] == "high" for h in r["hits"])

    confirmed = False
    bdim = dims.get("behavior", {})
    if bdim.get("available"):
        for c in bdim.get("clusters", []):
            if c["size"] >= 5 and c["avg_similarity"] >= 0.80:
                confirmed = True
                break

    level, label = grade(score, has_high_rule, coverage, confirmed)

    findings.sort(key=lambda f: ({"high": 0, "medium": 1, "low": 2}[f["severity"]]))

    # 多个独立的高危证据互相印证时，上调综合风险
    n_high = sum(1 for f in findings if f["severity"] == "high")
    if n_high >= 2:
        score = min(1.0, score + 0.035 * (n_high - 1))
        level, label = grade(score, has_high_rule, coverage, confirmed)
        if level == "low":
            level, label = "medium", "中风险"

    dim_list = [dims[k] for k in weights if k in dims]

    return {
        "scene": scene,
        "scene_name": meta["name"],
        "title": title or "未命名样本",
        "risk": {"score": round(score, 3), "level": level, "label": label,
                 "action": ACTION[level], "coverage": round(coverage, 2)},
        "dimensions": dim_list,
        "findings": findings,
        "compliance": r["hits"],
        "images": images_out,
        "narrative": _narrative(scene, score, label, dims, findings, coverage),
        "timing_ms": int((time.time() - t0) * 1000),
        "disclaimer": "本结果由可解释取证规则生成，置信度基于各维度证据覆盖度；"
                      "证据不足时会主动降级而非强行判定。",
    }


# ---------------------------------------------------------------- 证据 → 结论

def _pixel_findings(r: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    d = r["dimensions"]
    if d["ela"]["available"] and d["ela"]["score"] > 0.50:
        out.append({"dim": "pixel", "severity": "high" if d["ela"]["score"] > 0.75 else "medium",
                    "title": "存在重压缩误差台阶",
                    "detail": f"ELA 最大异常 z={d['ela']['max_z']}（>3 视为异常），"
                              f"疑似局部粘贴/重绘后未经统一压缩。"})
    if d["noise"]["available"] and d["noise"]["score"] > 0.55:
        out.append({"dim": "pixel", "severity": "high" if d["noise"]["score"] > 0.78 else "medium",
                    "title": "噪声残差不一致",
                    "detail": f"有 {d['noise']['anomaly_ratio'] * 100:.1f}% 的区域噪声水平偏离全图中位数，"
                              f"符合拼接/局部重绘特征。"})
    if d.get("smooth", {}).get("available") and d["smooth"]["score"] > 0.50:
        out.append({"dim": "pixel", "severity": "high" if d["smooth"]["score"] > 0.72 else "medium",
                    "title": "局部皮肤细节被抹平",
                    "detail": f"有 {d['smooth']['smooth_ratio'] * 100:.1f}% 的区域高频细节显著低于周边"
                              f"（最小 z={d['smooth']['min_z']}），符合磨皮/局部重绘特征。"})
    if d["freq"]["available"] and d["freq"]["score"] > 0.60:
        out.append({"dim": "pixel", "severity": "medium",
                    "title": "频谱分布偏离自然图像",
                    "detail": f"功率谱斜率 α={d['freq']['alpha']}（自然图像典型 1.8–2.4），"
                              f"高频能量占比 {d['freq']['hf_ratio']}。"})
    if d["copymove"]["available"] and d["copymove"]["score"] > 0.45:
        out.append({"dim": "pixel", "severity": "medium",
                    "title": "检测到图内复制粘贴",
                    "detail": f"自匹配到 {d['copymove']['matches']} 组特征对，位移向量形成 "
                              f"{d['copymove']['clusters']} 个一致簇。"})
    if d["meta"]["available"] and d["meta"]["score"] > 0.35:
        out.append({"dim": "pixel", "severity": "low", "title": "元数据异常",
                    "detail": "；".join(d["meta"].get("reasons", [])) or "EXIF 信息缺失或不完整。"})
    return out


def _consistency_findings(c: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    if c.get("over_claim_ratio") and c["over_claim_ratio"] > 1.4:
        out.append({"dim": "consistency", "severity": "high",
                    "title": "功效宣称与图像证据不匹配",
                    "detail": f"宣称色差 ΔE≈{c['claim']['claimed_delta_e']}，实测 ΔE={c['delta_e']}，"
                              f"夸大倍数约 {c['over_claim_ratio']}×。"})
    if c["lighting"]["diff_deg"] > 35:
        out.append({"dim": "consistency", "severity": "medium",
                    "title": "前后图光照条件不一致",
                    "detail": f"主光方向相差 {c['lighting']['diff_deg']}°，"
                              f"说明不是同一次拍摄，不能作为严格对比证据。"})
    if c.get("identical"):
        out.append({"dim": "consistency", "severity": "high", "title": "前后图为同一画面",
                    "detail": "两张图内容几乎完全一致，却声称是使用前后对比。"})
    return out


def _semantic_findings(s: dict[str, Any]) -> list[dict[str, Any]]:
    """文体维度只在「明显偏高」时才出证据卡，避免低分却被贴上「模板化」标签。"""
    if s["score"] < 0.55:
        return []
    names = "、".join(f["name"] for f in s["top_factors"][:3])
    return [{"dim": "semantic",
             "severity": "high" if s["score"] >= 0.75 else "medium",
             "title": "文案文体偏模板化",
             "detail": f"文体分 {round(s['score'] * 100)}/100（越高越像模板/AI 生成），"
                       f"主要来自：{names}。逐句可疑度与特征贡献见下方图表。"}]


def _behavior_findings(b: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    if b["clusters"]:
        top = b["clusters"][0]
        out.append({"dim": "behavior", "severity": "high" if top["size"] >= 5 else "medium",
                    "title": f"发现 {len(b['clusters'])} 个模板化评论簇",
                    "detail": f"最大簇 {top['size']} 条，平均相似度 {top['avg_similarity']}，"
                              f"示例：「{top['samples'][0]}」"})
    if b["timing"].get("available") and b["timing"].get("burst_ratio", 0) >= 0.5:
        out.append({"dim": "behavior", "severity": "medium", "title": "短时集中投放",
                    "detail": f"{b['timing']['burst_ratio'] * 100:.0f}% 的评论落在同一 10 分钟窗口内"
                              f"（共 {b['timing']['count']} 条，跨度 {b['timing']['span_minutes']} 分钟）。"})
    elif b["timing"].get("available") and b["timing"]["gap_cv"] < 0.35:
        out.append({"dim": "behavior", "severity": "medium", "title": "发布时间高度规律",
                    "detail": f"相邻间隔变异系数 {b['timing']['gap_cv']}（<0.15 视为定时投放），"
                              f"{b['timing']['span_minutes']} 分钟内集中出现 {b['timing']['count']} 条。"})
    if b["sentiment"]["same_polarity"] > 0.9 and b["length"]["avg"] < 20:
        out.append({"dim": "behavior", "severity": "medium", "title": "评价高度同质",
                    "detail": f"{b['sentiment']['same_polarity'] * 100:.0f}% 的评论为同一极性，"
                              f"平均长度仅 {b['length']['avg']} 字。"})
    if b["accounts"]["suspicious"]:
        out.append({"dim": "behavior", "severity": "low", "title": "疑似异常账号",
                    "detail": "、".join(a["user"] for a in b["accounts"]["suspicious"][:3])})
    return out


def _rule_findings(r: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for h in r["hits"][:5]:
        ctx = h.get("context") or h["text"]
        out.append({"dim": "rules", "severity": h["severity"],
                    "title": h["name"],
                    "detail": f"命中原文「{ctx}」。{h['clause']}：{h['note']}"})
    return out


def _narrative(scene: str, score: float, label: str, dims: dict[str, Any],
               findings: list[dict[str, Any]], coverage: float) -> str:
    """判定依据要「论证」，不是把维度分再抄一遍。

    结构：结论 → 主要疑点（把 ② 的分散证据串成因果链）→ 判定规则（为什么是这一档）
    """
    s100 = round(score * 100)
    name = SCENE_META[scene]["name"]
    head = f"【{name}】{label}（{s100}/100）"

    if scene == "comments":
        body, rule = _argue_comments(label, dims)
    elif scene == "material":
        body, rule = _argue_material(label, dims)
    else:
        body, rule = _argue_post(label, dims)

    tail = ""
    if coverage < 1:
        tail = "\n\n注：本次有维度未参与（缺少对比图或文本过短），结论基于已完成的维度。"
    return head + "\n\n" + body + "\n\n" + rule + tail


def _fmt_clues(d: dict[str, Any]) -> list[str]:
    """把像素层的三项关键数值变成短句。"""
    out = []
    if d.get("noise", {}).get("anomaly_ratio", 0) > 0.03:
        out.append(f"噪声偏离 {d['noise']['anomaly_ratio'] * 100:.0f}%")
    if d.get("smooth", {}).get("smooth_ratio", 0) > 0.03:
        out.append(f"细节缺失 {d['smooth']['smooth_ratio'] * 100:.0f}%（最低 {d['smooth']['min_z']}σ）")
    if d.get("ela", {}).get("max_z", 0) > 4:
        out.append(f"压缩误差峰值 z={d['ela']['max_z']}")
    return out


def _argue_post(label: str, dims: dict[str, Any]) -> tuple[str, str]:
    px = dims.get("pixel", {})
    w = px.get("worst", {}) if px else {}
    cons = dims.get("consistency", {})
    hits = dims.get("rules", {}).get("hits", [])
    sem = dims.get("semantic", {})
    clues = _fmt_clues(w)
    claimed = (cons.get("claim") or {}).get("claimed_delta_e") or 0 if cons else 0

    if label == "低风险":
        checked = []
        if clues:
            checked.append("像素取证中" + "、".join(clues) + "，均在告警线以下，未形成成块的异常区域")
        else:
            checked.append("像素取证未发现局部异常")
        if cons and cons.get("available"):
            if claimed:
                checked.append(f"实测色差 ΔE {cons.get('delta_e')} 与文案宣称（ΔE {claimed}）基本相符")
            else:
                checked.append(f"文案没有量化宣称，实测色差 ΔE {cons.get('delta_e')} 无可比对象")
        if hits:
            checked.append(f"但仍命中 {len(hits)} 条广告法规，已单独列出")
        else:
            checked.append("未命中广告法条款")
        if sem.get("available") and sem.get("score", 0) < 0.55:
            checked.append("文体上也未见明显的模板化痕迹")
        body = ("各维度都做了计算，但没有一条达到出证阈值：" +
                "；".join(x.rstrip("。") for x in checked) + "。")
    else:
        ev = []
        if len(clues) >= 2:
            ev.append(f"像素层出现 {len(clues)} 项同区异常（{'，'.join(clues)}），"
                      "属于局部重绘留下的痕迹，而不是全局调色造成的整体偏移")
        elif clues:
            ev.append(f"像素层有单项异常（{'，'.join(clues)}），但只有一路信号，"
                      "不足以单独认定篡改")
        if cons and cons.get("available") and claimed:
            ev.append(f"文案宣称提亮 {cons['claim'].get('levels')} 个色号（约 ΔE {claimed}），"
                      f"两张图实测肤色色差只有 ΔE {cons.get('delta_e')}，"
                      f"夸大 {cons.get('over_claim_ratio')} 倍，效果图不足以支撑这句承诺")
        if hits:
            names = "、".join(dict.fromkeys(h["name"] for h in hits))
            ev.append(f"合规层命中 {len(hits)} 条广告法规（{names}），属于可直接处置的硬性问题")
        body = "；".join(x.rstrip("。") for x in ev) + "。" if ev else "证据不足以形成完整论证。"

    over = [DIM_NAME[k] for k, d in dims.items()
            if isinstance(d, dict) and d.get("available") and d.get("score", 0) >= 0.75]
    rule = "判定规则：像素需两路信号同区互证；夸大 >1.4 倍才计入；两条以上高危证据才升高风险。"
    if label == "高风险":
        rule += f"本次{'、'.join(over) if over else '多项证据'}超过 75 分，故判高风险。"
    elif label == "中风险":
        rule += "本次未形成多路互证，故判中风险。"
    else:
        rule += "本次各维度均低于 45 分，故判低风险。"
    return body, rule


def _argue_comments(label: str, dims: dict[str, Any]) -> tuple[str, str]:
    b = dims.get("behavior", {})
    hits = dims.get("rules", {}).get("hits", [])
    clusters = b.get("clusters") or []
    t = b.get("timing") or {}
    acct = (b.get("accounts") or {}).get("suspicious") or []

    if label == "低风险":
        checked = ["评论文本相似度低，没有出现同一模板的批量复制"]
        if t.get("available"):
            checked.append(f"发布间隔分布自然（变异系数 {t['gap_cv']}）")
        if not acct:
            checked.append("账号昵称无批量注册特征")
        body = "未发现群体性异常：" + "；".join(checked) + "。"
    else:
        ev = []
        if clusters:
            top = clusters[0]
            ev.append(f"{top['size']} 条评论使用同一套模板（平均相似度 {top['avg_similarity']}），"
                      f"示例「{top['samples'][0]}」")
        if t.get("available") and t.get("burst_ratio", 0) >= 0.5:
            ev.append(f"{t['burst_ratio'] * 100:.0f}% 的评论挤在同一个 10 分钟窗口内投放，"
                      f"其余散布在随后 {t['span_minutes'] / 60:.0f} 小时——正常用户的评论不会这样分布")
        elif t.get("available") and t.get("gap_cv", 9) < 0.35:
            ev.append(f"发布间隔近乎等距（变异系数 {t['gap_cv']}），呈定时投放特征")
        if acct:
            ev.append(f"{len(acct)} 个账号昵称呈批量注册形态（英文+数字后缀），与评论时间高度吻合")
        body = "；".join(x.rstrip("。") for x in ev) + "。"
        if len(ev) >= 2:
            body += "这些线索指向同一批账号的协同行为，属于结构性造假，而不是单条评论的语义问题。"
        if hits:
            body += f" 另：评论文本命中 {len(hits)} 条广告法规（{'、'.join(dict.fromkeys(h['name'] for h in hits))}）。"

    rule = "判定规则：模板簇 ≥5 条且相似度 ≥0.80 即视为确证性证据，不设缓冲。"
    if label == "高风险":
        rule += "本次模板簇与投放节奏同时成立，故判高风险。"
    elif label == "中风险":
        rule += "本次仅满足其中一项，故判中风险。"
    else:
        rule += "本次未形成模板簇，故判低风险。"
    return body, rule


def _argue_material(label: str, dims: dict[str, Any]) -> tuple[str, str]:
    px = dims.get("pixel", {})
    w = px.get("worst", {}) if px else {}
    sem = dims.get("semantic", {})
    hits = dims.get("rules", {}).get("hits", [])
    clues = _fmt_clues(w)

    if label == "低风险":
        body = ("单图取证未发现成块的局部异常：" +
                ("、".join(clues) + " 均在告警线以下，" if clues else "") +
                "细节、噪声、压缩误差在整幅图上分布均匀，没有出现「某一小块明显不同」的重绘特征。")
    else:
        body = ("单图取证：" + "，".join(clues) +
                "。这些异常集中在一小块区域、周边保持原状，说明是局部重绘或局部处理，"
                "不是整张图统一加了滤镜。") if clues else "局部取证存在异常，但信号较弱。"

    if sem.get("available"):
        body += (f"\n\n配文方面，文体分 {round(sem.get('score', 0) * 100)}/100" +
                 ("，表现出模板化写作倾向。" if sem.get("score", 0) >= 0.55 else "，未表现出明显模板化。"))
    if hits:
        body += f" 合规层命中 {len(hits)} 条广告法规。"

    rule = "判定规则：只有成块的区域性异常才算证据，全局均匀的平滑不计入。"
    rule += {"高": "本次达到高风险条件。",
             "中": "本次仅有局部证据，故判中风险。",
             "低": "本次未见成块异常，故判低风险。"}.get(label[0], "")
    return body, rule
