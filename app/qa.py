"""基于证据的问答。

不接大模型也能回答：所有回答都从本份报告的结构化证据里检索，
因此不会出现"编一个理由"的情况。

匹配顺序很关键：先匹配具体维度（一致性/评论/像素/文本），再匹配通用意图（原因/分数/处置），
否则「文本文体怎么算」会被「怎么算」抢走，答成评分说明。
"""
from __future__ import annotations

import re
from typing import Any

# 顺序 = 优先级
INTENTS = [
    ("consistency", r"一致|对比|色差|ΔE|delta|前后"),
    ("behavior", r"评论|水军|灌水|刷单|刷评|账号|投放"),
    ("pixel", r"像素|图片|图像|篡改|修图|磨皮|噪声|压缩|频域|ELA|痕迹"),
    ("text", r"文本|文案|文体|写作|模板|句子|AI\s*味"),
    ("compliance", r"合规|法律|法规|条款|广告法|条例|处罚|违规|下架"),
    ("location", r"哪里|哪一块|哪个区域|位置|改哪|定位|框"),
    ("evidence", r"为什么|凭什么|依据|理由|原因|怎么判|等级|证据"),
    ("confidence", r"准不准|置信|可信|准确率|误判|靠不靠谱|覆盖"),
    ("action", r"处置|怎么办|怎么处理|建议|该做什么|整改"),
    ("score", r"分数|评分|打分|分制|满分|多少分|怎么算|什么意思"),
    ("summary", r"总结|概括|结论|一句话|总体"),
]

DIM_NAME = {
    "pixel": "像素取证", "semantic": "文本文体", "consistency": "图文一致性",
    "rules": "合规规则", "behavior": "评论行为",
}


def _dims(rep: dict[str, Any]) -> dict[str, dict]:
    return {d["key"]: d for d in rep.get("dimensions", [])}


def answer(rep: dict[str, Any], q: str) -> str:
    q = (q or "").strip()
    intent = "unknown"
    for name, pat in INTENTS:
        if re.search(pat, q, re.I):
            intent = name
            break

    dims = _dims(rep)
    findings = rep.get("findings", [])
    risk = rep.get("risk", {})
    score = float(risk.get("score", 0))
    s100 = round(score * 100)
    label = risk.get("label", "")

    # ---------------- 评分体系
    if intent == "score":
        avail = [d for d in rep.get("dimensions", []) if d.get("available")]
        w = "、".join(f"{DIM_NAME.get(d['key'], d['key'])} {round(d.get('score', 0) * 100)}"
                     for d in avail)
        return (f"综合分 **{s100} / 100**（{label}）。分档：0–44 低风险，45–74 中风险，75–100 高风险。\n\n"
                f"参与计算的维度：{w}。\n"
                f"算法是「按场景权重加权平均」——例如评论场景以行为层为主，图文场景像素与一致性占大头。\n\n"
                f"证据覆盖 {risk.get('coverage', 0) * 100:.0f}%：没算的维度不会假装算过，"
                f"覆盖不足时结论会自动降一级。")

    # ---------------- 为什么 / 依据
    if intent == "evidence":
        if not findings:
            return f"本次没有足以支撑风险的异常特征，所以给低风险（{s100}/100）。"
        lines = [f"{i + 1}. {f['title']}——{f['detail'].rstrip('。')}" for i, f in enumerate(findings[:4])]
        return (f"判 **{label}（{s100}/100）**，主要依据这几条：\n" + "\n".join(lines) +
                f"\n\n这些证据覆盖了 {risk.get('coverage', 0) * 100:.0f}% 的应检维度。"
                f"单条证据可能误报，所以系统要求多条互相印证才升级到高风险。")

    # ---------------- 定位
    if intent == "location":
        out = []
        for im in rep.get("images", []):
            for i, r in enumerate(im.get("regions", [])[:3]):
                x, y, w, h = r["bbox"]
                out.append(f"{im['file']} 第 {i + 1} 处：左上角 ({x},{y})，{w}×{h}，可疑度 {r['peak'] * 100:.0f}%")
        if not out:
            return "本次没有检出明确的局部篡改区域（也可能是改动过于全局，或证据不足）。"
        return "检出的可疑区域：\n" + "\n".join(out) + "\n\n中间「融合热图」里的红框就是它们，可以拖透明度对照原图。"

    # ---------------- 图文一致性
    if intent == "consistency":
        d = dims.get("consistency")
        if not d or not d.get("available"):
            return "这次没做图文一致性分析——需要同时提供「使用前」和「使用后」两张图。"
        claim = d.get("claim", {})
        ratio = d.get("over_claim_ratio")
        return (f"实测肤色色差 **ΔE = {d.get('delta_e')}**，文案宣称折算 **ΔE ≈ {claim.get('claimed_delta_e')}**"
                + (f"，夸大 **{ratio} 倍**。" if ratio else "。") +
                f"\n两张图主光方向相差 {d.get('lighting', {}).get('diff_deg')}°。"
                f"\n算法：把皮肤区域转到 CIELAB 空间求平均色差，再按「一个色号 ≈ ΔE 3.5」换算成文案里的'度'。")

    # ---------------- 评论区
    if intent == "behavior":
        d = dims.get("behavior")
        if not d or not d.get("available"):
            return "这份报告没有评论区分析。"
        sub = d.get("sub_scores", {})
        t = d.get("timing", {})
        return (f"评论行为 **{round(d.get('score', 0) * 100)} / 100**。\n"
                f"模板化 {round(sub.get('模板化', 0) * 100)}、时间规律 {round(sub.get('时间规律', 0) * 100)}、"
                f"清一色 {round(sub.get('清一色', 0) * 100)}、账号异常 {round(sub.get('账号异常', 0) * 100)}。\n"
                f"共 {d.get('total')} 条，{round(d.get('template_ratio', 0) * 100)}% 落在模板簇里；"
                f"发布节奏：{t.get('verdict', '无时间信息')}。")

    # ---------------- 像素
    if intent == "pixel":
        d = dims.get("pixel")
        if not d or not d.get("available"):
            return "这份报告没有像素取证结果（本次未上传图片）。"
        rows = []
        for fn, dd in (d.get("detail") or {}).items():
            hot = [f"{k}={round(v['score'] * 100)}" for k, v in dd.items()
                   if isinstance(v, dict) and v.get("available") and v.get("score", 0) > 0.2]
            rows.append(f"{fn}：{'、'.join(hot) if hot else '各维度都不高'}")
        return (f"像素取证 **{round(d['score'] * 100)} / 100**。\n" + "\n".join(rows) +
                "\n\n噪声残差看'这块区域的噪声是否和周围不一样'，磨皮检测看'毛孔纹理是不是被抹掉了'，"
                "ELA 看'压缩历史是否一致'——三个信号在同一块区域同时异常，才认定为篡改。")

    # ---------------- 文本
    if intent == "text":
        d = dims.get("semantic")
        if not d or not d.get("available"):
            return "这份报告里文本文体没有参与计算——文案少于 40 字或少于 2 句时，文体特征不具备统计意义。"
        feats = sorted(d.get("features", []), key=lambda f: -f.get("contribution", 0))[:3]
        lines = [f"· {f['name']}：{f['note']}（贡献度 {f['contribution']}）" for f in feats]
        return (f"文本文体 **{round(d['score'] * 100)} / 100**（越高越像模板/AI 生成）。\n"
                + "\n".join(lines) +
                "\n\n注意：这一维只回答'写得像不像机器'，不回答'内容真假'，所以权重不高。")

    # ---------------- 合规
    if intent == "compliance":
        hits = rep.get("compliance", [])
        if not hits:
            return "本次没有命中广告法规条款。"
        lines = [f"· {h['name']}：「{h['text']}」——{h['clause']}" for h in hits[:5]]
        return "命中 " + str(len(hits)) + " 条：\n" + "\n".join(lines)

    # ---------------- 置信度
    if intent == "confidence":
        cov = risk.get("coverage", 0)
        missing = [DIM_NAME[k] for k in ("pixel", "semantic", "consistency", "rules")
                   if not dims.get(k, {}).get("available")]
        extra = f"\n未参与的维度：{'、'.join(missing)}。" if missing else ""
        return (f"证据覆盖率 {cov * 100:.0f}%。覆盖不足时系统会主动降级，而不是硬给高分。{extra}\n"
                f"每个分数都能在证据卡片里追溯到具体数值——这是它和黑盒检测器最大的区别。")

    # ---------------- 处置
    if intent == "action":
        return f"当前判定 **{label}**（{s100}/100）。\n{risk.get('action', '')}"

    if intent == "summary":
        return rep.get("narrative", "暂无结论。")

    # ---------------- 兜底：按关键词检索证据
    tokens = [t for t in re.split(r"[\s，。？?！!、]+", q) if len(t) >= 2]
    hits = [f"· {f['title']}——{f['detail'].rstrip('。')}" for f in findings
            if any(t in (f.get("title", "") + f.get("detail", "")) for t in tokens)]
    if hits:
        return "在本次证据里找到相关内容：\n" + "\n".join(hits[:5])

    return (f"这个问题我没法从本次证据里直接回答。当前结论：{label}（{s100}/100）。\n"
            "可以试试：为什么判这个等级 / 改在哪一块 / 文本文体怎么算的 / 平台该怎么处置。")
