"""
规则层 —— 美妆广告合规引擎。

纯正则 + 上下文判定，零算力、零幻觉，输出的是可以直接写进处置工单的违规条目：
命中了哪条法规、原文哪几个字、为什么违规。

规则依据：
  《中华人民共和国广告法》第九条（绝对化用语）、第二十八条（虚假广告）
  《化妆品监督管理条例》第十六条（特殊化妆品注册）、第四十三条（不得宣称医疗作用）
  《化妆品功效宣称评价规范》（功效宣称需有评价依据）
"""
from __future__ import annotations

import re
from typing import Any

# (规则ID, 名称, 依据, 严重度, 正则, 说明)
RULES: list[dict[str, Any]] = [
    {
        "id": "absolute_wording", "name": "绝对化用语", "clause": "《广告法》第九条", "severity": "high",
        "pattern": r"(最好|最佳|最低|最高|最强|最强效|第一品牌|排名第一|销量第一|全网最低|史上最|"
                   r"顶级|顶尖|国家级|世界级|绝无仅有|独一无二|独家配方|唯一|首选|冠军|"
                   r"100%|百分百|永久|彻底根除|绝对安全|零风险)",
        "note": "广告不得使用「国家级」「最高级」「最佳」等绝对化用语。",
    },
    {
        "id": "medical_claim", "name": "宣称医疗作用", "clause": "《化妆品监督管理条例》第四十三条", "severity": "high",
        "pattern": r"(治疗|治愈|消炎|杀菌|抗菌|抗过敏|脱敏|药妆|医学护肤|医用级|处方|药用|"
                   r"修复(痘坑|疤痕|创面|损伤)|生发|激活细胞|排毒)",
        "note": "化妆品不得明示或暗示具有医疗作用。",
    },
    {
        "id": "special_cosmetic", "name": "特殊化妆品未标批号", "clause": "《化妆品监督管理条例》第十六条", "severity": "high",
        "pattern": r"(美白|祛斑|淡斑|防晒|染发|烫发|防脱|育发)",
        "note": "美白、祛斑、防晒、染发、烫发、防脱发属特殊化妆品，须标注「国妆特字」注册编号。",
        "requires": {"absent": r"国妆特字|国妆特进字"},
    },
    {
        "id": "efficacy_time", "name": "量化功效承诺缺乏依据", "clause": "《化妆品功效宣称评价规范》", "severity": "medium",
        "pattern": r"(\d+\s*(天|日|周|个月)\s*(内|后)?\s*(见效|变白|美白|祛斑|淡斑|祛痘|去皱|紧致)|"
                   r"白\s*[0-9一二两三四五六七八九十]+\s*个?\s*(度|色号|色阶)|"
                   r"立竿见影|立刻见效|瞬间美白|秒变|一擦就白)",
        "note": "功效宣称应有评价依据，短期见效类承诺通常无法提供依据。",
    },
    {
        "id": "fake_endorsement", "name": "无法核验的专家背书", "clause": "《广告法》第二十八条", "severity": "medium",
        "pattern": r"(皮肤科(主任|专家|医生)|三甲医院|诺贝尔|中科院|院士|临床验证|医学认证|"
                   r"专供|院线同款|医生推荐)",
        "note": "以虚构或无法核验的机构、专家名义作推荐证明，可能构成虚假广告。",
    },
    {
        "id": "before_after", "name": "前后对比图缺少提示", "clause": "平台社区公约 / 广告真实性", "severity": "low",
        "pattern": r"(使用前|使用后|前后对比|before|after)",
        "note": "使用效果对比图应标注「效果因人而异」，且不得通过修图夸大差异。",
        "requires": {"absent": r"因人而异|仅供参考|个体差异"},
    },
]

COMPILED = [(r, re.compile(r["pattern"], re.I)) for r in RULES]


def check_text(text: str) -> dict[str, Any]:
    """对文案做合规扫描。返回命中列表 + 覆盖率信息。"""
    text = text or ""
    hits = []
    for rule, pat in COMPILED:
        for m in pat.finditer(text):
            # 反向条件：例如文中已标注「国妆特字」，则不判特殊化妆品缺失
            req = rule.get("requires")
            if req and req.get("absent") and re.search(req["absent"], text, re.I):
                continue
            # 「第一次」「第一天」不是绝对化用语
            if rule["id"] == "absolute_wording":
                after = text[m.end(): m.end() + 2]
                if m.group(0) in ("第一",) and after[:1] in "次天个眼批步":
                    continue
            # 取「命中词所在的那一小句」，而不是硬切 14 个字——
            # 否则会从半个词开始，看起来像断章取义。
            start, end = m.start(), m.end()
            DELIM = "。！？；\n，"
            lo = max(text.rfind(c, 0, start) for c in DELIM) + 1
            rights = [i for i in (text.find(c, end) for c in DELIM) if i != -1]
            hi = min(rights) if rights else len(text)
            ctx = re.sub(r"\s+", " ", text[lo:hi]).strip()
            if len(ctx) > 34:
                pad = max(4, (34 - (end - start)) // 2)
                a, b = max(lo, start - pad), min(hi, end + pad)
                ctx = ("…" if a > lo else "") + text[a:b].strip() + ("…" if b < hi else "")

            hits.append({
                "rule": rule["id"],
                "name": rule["name"],
                "clause": rule["clause"],
                "severity": rule["severity"],
                "text": m.group(0),
                "context": ctx,
                "span": [m.start(), m.end()],
                "note": rule["note"],
            })

    # 去重（同一条规则同一处）
    seen, uniq = set(), []
    for h in hits:
        key = (h["rule"], h["span"][0])
        if key not in seen:
            seen.add(key)
            uniq.append(h)

    weight = {"high": 1.0, "medium": 0.55, "low": 0.25}
    score = min(1.0, sum(weight[h["severity"]] for h in uniq) / 2.0)

    return {
        "available": True,
        "score": round(score, 3),
        "hits": uniq,
        "by_severity": {k: sum(1 for h in uniq if h["severity"] == k) for k in ("high", "medium", "low")},
    }
