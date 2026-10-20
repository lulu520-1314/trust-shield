"""
一致性层 —— 量化「使用前 / 使用后」对比图与文案宣称是否对得上。

这是本方案的"语义一致性校验"落地方式，而且是可测量的：
把两张图的皮肤区域转到 CIELAB 空间，算色差 ΔE，
再把文案里的宣称（"7 天白 3 个度"）折算成期望 ΔE，两边对照。

比让视觉大模型"看图说像不像"更硬：给出的是能复算的数字。
"""
from __future__ import annotations

import re
from typing import Any

import cv2
import numpy as np

from app.tools.imgio import imread

# 一个「色号/度」在 LAB 空间约等于多少 ΔE（经验值，美妆行业常见区间 3~5）
DELTA_E_PER_LEVEL = 3.5

CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def skin_mask(img: np.ndarray) -> np.ndarray:
    """YCrCb 椭圆肤色模型，返回 uint8 掩码（255=皮肤）。"""
    ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    mask = ((cr >= 133) & (cr <= 175) & (cb >= 77) & (cb <= 130) & (y >= 50)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    return mask


def _mean_lab(img: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, float]:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    # OpenCV 的 LAB：L 0-255, a/b 0-255（需减 128 还原）
    sel = mask > 0
    if sel.sum() < 200:
        return np.array([0.0, 0.0, 0.0]), 0.0
    vals = lab[sel]
    mean = np.array([vals[:, 0].mean(), vals[:, 1].mean() - 128, vals[:, 2].mean() - 128])
    return mean, float(sel.mean())


def delta_e76(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(((a - b) ** 2).sum()))


def parse_claim(text: str) -> dict[str, Any]:
    """从文案里抽取功效宣称与期望色差。"""
    text = text or ""
    levels = None
    m = re.search(r"(白|提亮|淡化|改善)[^，。]{0,6}?([0-9一二两三四五六七八九十])\s*个?\s*(度|色号|色阶)", text)
    if m:
        v = m.group(2)
        levels = int(v) if v.isdigit() else CN_NUM.get(v, 1)
    else:
        m2 = re.search(r"(白|提亮|美白|淡斑|祛斑|透亮)", text)
        if m2:
            # 否定语境不算宣称："提亮效果一般"「没看出来」不是承诺
            ctx = text[max(0, m2.start() - 10): m2.end() + 12]
            if not re.search(r"没|不|无|一般|看不出|差|弱|失望", ctx):
                levels = 1

    days = None
    m3 = re.search(r"(\d+)\s*(天|日|周)", text)
    if m3:
        days = int(m3.group(1)) * (7 if m3.group(2) == "周" else 1)

    claimed_de = levels * DELTA_E_PER_LEVEL if levels else 0.0
    return {"levels": levels, "days": days, "claimed_delta_e": round(claimed_de, 2)}


def _resize_to(img: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    return cv2.resize(img, (shape[1], shape[0]), interpolation=cv2.INTER_AREA)


def analyze_pair(before_path: str, after_path: str, text: str = "") -> dict[str, Any]:
    """对比两张图（使用前 / 使用后）。"""
    from app.tools.pixel import lighting_direction

    b = imread(before_path, cv2.IMREAD_COLOR)
    a = imread(after_path, cv2.IMREAD_COLOR)
    if b is None or a is None:
        return {"available": False, "score": 0.0, "reason": "图片读取失败"}

    h = min(b.shape[0], a.shape[0], 1200)
    w = min(b.shape[1], a.shape[1], 1200)
    b, a = _resize_to(b, (h, w)), _resize_to(a, (h, w))

    mb, mb_ratio = _mean_lab(b, skin_mask(b))
    ma, ma_ratio = _mean_lab(a, skin_mask(a))
    de = delta_e76(mb, ma)
    d_l = float(ma[0] - mb[0])       # 亮度变化（正=变亮）
    d_a = float(ma[1] - mb[1])       # 红绿轴
    d_b = float(ma[2] - mb[2])       # 黄蓝轴（负=更蓝/更白）

    claim = parse_claim(text)
    over_ratio = None
    if claim["claimed_delta_e"] > 0:
        over_ratio = round(claim["claimed_delta_e"] / max(de, 0.8), 2)

    # 光照方向一致性
    lb, la = lighting_direction(b), lighting_direction(a)
    light_diff = abs(((lb["direction"] - la["direction"] + 90) % 180) - 90)

    # 两张图是否几乎相同（同一张图被当作"前后对比"）
    diff = cv2.absdiff(cv2.cvtColor(b, cv2.COLOR_BGR2GRAY), cv2.cvtColor(a, cv2.COLOR_BGR2GRAY))
    identical = float((diff > 14).mean()) < 0.003

    notes = []
    if claim["levels"]:
        notes.append(
            f"文案宣称「白 {claim['levels']} 个度」，折算期望色差 ΔE≈{claim['claimed_delta_e']}；"
            f"实测肤色色差 ΔE={de:.1f}（{'不足以支撑宣称' if de < claim['claimed_delta_e'] * 0.6 else '基本相符'}）"
        )
    else:
        notes.append(f"文案未给出量化色阶，实测肤色色差 ΔE={de:.1f}，其中亮度变化 ΔL*={d_l:+.1f}")
    if light_diff > 35:
        notes.append(f"两张图主光方向相差 {light_diff:.0f}°，不是同一光照条件下拍摄，不能作为严格前后对比")
    if identical:
        notes.append("两张图内容几乎完全一致，「前后对比」不成立")

    score = 0.0
    if over_ratio is not None and over_ratio > 1.2:
        score += min(0.82, (over_ratio - 1.2) / 2.0)
    if light_diff > 35:
        score += 0.25
    if identical:
        score += 0.8

    return {
        "available": True,
        "score": round(float(min(1.0, score)), 3),
        "delta_e": round(de, 2),
        "delta_l": round(d_l, 1),
        "delta_a": round(d_a, 1),
        "delta_b": round(d_b, 1),
        "before_lab": [round(float(x), 1) for x in mb],
        "after_lab": [round(float(x), 1) for x in ma],
        "skin_ratio": [round(mb_ratio, 3), round(ma_ratio, 3)],
        "claim": claim,
        "over_claim_ratio": over_ratio,
        "lighting": {"before": lb, "after": la, "diff_deg": round(float(light_diff), 1)},
        "identical": identical,
        "notes": notes,
    }
