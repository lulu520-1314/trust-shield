"""
像素层取证 —— 判断一张图「有没有被局部改过 / 是不是生成的 / 改在哪」。

设计原则：不训练检测模型，全部使用可解释的取证信号。
每个信号都能回答「凭什么」，并且能画成图给评委看。

七个维度：
  ela        错误级别分析（JPEG 重压缩误差）
  noise      噪声残差一致性（传感器噪声是否被破坏）
  smooth     高频细节缺失（磨皮/重绘最典型的特征）
  freq       频域指纹（功率谱斜率 / 高频能量）
  copymove   拷贝-移动检测（SIFT 自匹配）
  meta       EXIF 与生成器指纹
  lighting   光照方向（用于前后对比图的拍摄一致性）

所有局部信号都在同一套 32×32 块网格上计算，因此可以直接融合、定位。
"""
from __future__ import annotations

import hashlib
import os
from typing import Any

import cv2
import numpy as np

from app.tools.imgio import imread, imwrite

cv2.setNumThreads(4)

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                         "data", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

MAX_SIDE = 1200
BLOCK = 32

# 权重（局部信号参与融合定位，全局信号参与整体打分）
WEIGHTS = {"ela": 0.26, "noise": 0.24, "smooth": 0.20, "freq": 0.12, "copymove": 0.10, "meta": 0.08}


# ---------------------------------------------------------------- 基础工具

def _load(path: str) -> tuple[np.ndarray, np.ndarray]:
    img = imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"无法读取图片: {path}")
    h, w = img.shape[:2]
    if max(h, w) > MAX_SIDE:
        s = MAX_SIDE / max(h, w)
        small = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    else:
        small = img
    return img, small


def _blocks(map2d: np.ndarray, fn=np.mean) -> np.ndarray:
    h, w = map2d.shape[:2]
    bh, bw = h // BLOCK, w // BLOCK
    if bh < 2 or bw < 2:
        return np.zeros((1, 1), np.float32)
    t = map2d[: bh * BLOCK, : bw * BLOCK]
    return fn(t.reshape(bh, BLOCK, bw, BLOCK), axis=(1, 3)).astype(np.float32)


def _norm01(x: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return x.astype(np.float32)
    lo, hi = np.percentile(x, 2), np.percentile(x, 98)
    if hi - lo < 1e-6:
        return np.zeros_like(x, dtype=np.float32)
    return np.clip((x - lo) / (hi - lo), 0, 1).astype(np.float32)


def _upsample(grid: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    h, w = shape
    if grid.shape[0] < 2 or grid.shape[1] < 2:
        return np.zeros((h, w), np.float32)
    return cv2.resize(grid.astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)


def _save_overlay(name: str, score_map: np.ndarray) -> str:
    # 不做归一化：热力图强度要反映"绝对可疑度"，否则干净图片也会被拉满
    m = np.clip((score_map - 0.20) / 0.60, 0, 1).astype(np.float32)
    color = cv2.applyColorMap((m * 255).astype(np.uint8), cv2.COLORMAP_JET)
    b, g, r = cv2.split(color)
    rgba = cv2.merge([b, g, r, (m * 215).astype(np.uint8)])
    imwrite(os.path.join(CACHE_DIR, name), rgba)
    return name


def _zscore(grid: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
    """稳健 z 分数（中位数 / MAD）。

    注意 MAD 会退化：画面足够均匀时 MAD≈0，过去用 `+1e-6` 当分母，
    微分波动会被放大成 z=85 万这种荒谬值，于是干净照片被误判成"重压缩台阶"。
    这里改用数据自身的分位数给一个尺度下限，并把 z 截断在合理范围内。
    """
    vals = grid[valid] if valid is not None and valid.sum() > 4 else grid.ravel()
    med = float(np.median(vals))
    # 只挡掉 MAD 完全退化成 0 的情况（除数不能是 1e-6），
    # 不给分位数下限——那会连噪声/磨皮两个检测器一起削弱。
    mad = max(float(np.median(np.abs(vals - med))) * 1.4826, 1e-3)
    z = np.clip((grid - med) / mad, -200.0, 200.0)
    if valid is not None:
        z = np.where(valid, z, 0.0)
    return z


def _s2(z: np.ndarray) -> np.ndarray:
    """z 分数 → [0,1] 可疑度：|z|=3.0 起步，7.0 封顶。"""
    return np.clip((np.abs(z) - 3.0) / 4.0, 0, 1).astype(np.float32)


def _s_smooth(z: np.ndarray) -> np.ndarray:
    """磨皮是单侧异常（细节只会变少），用更敏感的映射。"""
    return np.clip((-z - 1.8) / 3.0, 0, 1).astype(np.float32)


# ---------------------------------------------------------------- 1. ELA

def analysis_ela(img: np.ndarray, tag: str = "") -> dict[str, Any]:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return {"available": False, "score": 0.0}
    resaved = cv2.imdecode(buf, cv2.IMREAD_COLOR)

    diff = np.max(cv2.absdiff(img, resaved).astype(np.float32), axis=2)
    diff = cv2.GaussianBlur(diff, (5, 5), 0)

    grid = _blocks(diff)
    med = float(np.median(grid))
    # 绝对幅度闸门：整幅图的压缩误差起伏不到 1.5 个灰阶时，
    # 说明源图几乎没有被 JPEG 压过（或全图均匀），不存在"重压缩台阶"，
    # 此时 z 分数再大也是噪声——真实皮肤特写就栽在这里。
    dev98 = float(np.percentile(np.abs(grid - med), 98))
    z = _zscore(grid)
    if dev98 < 1.5:
        score = 0.0
    else:
        score = float(np.clip((np.percentile(np.abs(z), 98) - 2.5) / 3.5, 0, 1))

    idx = np.dstack(np.unravel_index(np.argsort(-np.abs(z).ravel())[:5], z.shape))[0]
    return {
        "available": True,
        "score": round(score, 4),
        "mean": round(float(diff.mean()), 2),
        "dev98": round(dev98, 2),
        "max_z": round(float(np.abs(z).max()), 2),
        "hotspots": [{"row": int(r), "col": int(c), "z": round(float(z[r, c]), 2)} for r, c in idx],
        "grid": z,
        "heat": _save_overlay(f"{tag}_ela.png", _upsample(_s2(z), diff.shape)),
    }


# ---------------------------------------------------------------- 2. 噪声残差

def analysis_noise(img: np.ndarray, tag: str = "") -> dict[str, Any]:
    den = cv2.bilateralFilter(img, 9, 75, 75)
    res = (img.astype(np.float32) - den.astype(np.float32)).mean(axis=2)

    raw_var = _blocks(res ** 2)
    var_grid = np.log10(raw_var + 1.0)          # 对数域：方差分布长尾，线性 z 会被压平
    luma_grid = _blocks(img.mean(axis=2))
    valid = (luma_grid > 28) & (luma_grid < 246)

    z = _zscore(var_grid, valid)
    anomaly = float((np.abs(z[valid]) > 3.0).mean()) if valid.sum() else 0.0
    score = float(np.clip((anomaly - 0.05) / 0.20, 0, 1))

    return {
        "available": True,
        "score": round(score, 4),
        "median_var": round(float(np.median(raw_var[valid])) if valid.sum() else 0.0, 2),
        "anomaly_ratio": round(anomaly, 4),
        "max_abs_z": round(float(np.abs(z).max()), 2),
        "grid": z,
        "heat": _save_overlay(f"{tag}_noise.png", _upsample(_s2(z), img.shape[:2])),
    }


# ---------------------------------------------------------------- 3. 磨皮 / 局部平滑

def analysis_smooth(img: np.ndarray, tag: str = "") -> dict[str, Any]:
    """
    高频细节缺失检测 —— 美妆修图最常见的手法是磨皮：
    皮肤区域的高频纹理（毛孔、细纹）被抹平，Laplacian 方差显著低于周边。
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    raw = _blocks(lap ** 2)
    grid = np.log10(raw + 1.0)                  # 同上：对数域
    luma = _blocks(gray)

    valid = (luma > 40) & (luma < 240)
    z = _zscore(grid, valid)          # 负值 = 比周边更平滑

    low_ratio = float(((z < -3.0) & valid).sum() / max(valid.sum(), 1))
    score = float(np.clip((low_ratio - 0.03) / 0.12, 0, 1))

    idx = np.dstack(np.unravel_index(np.argsort(z.ravel())[:5], z.shape))[0]
    return {
        "available": True,
        "score": round(score, 4),
        "smooth_ratio": round(low_ratio, 4),
        "median_detail": round(float(np.median(raw)) if raw.size else 0.0, 1),
        "min_z": round(float(z[valid].min()) if valid.sum() else 0.0, 2),
        "smoothest": [{"row": int(r), "col": int(c), "z": round(float(z[r, c]), 2)} for r, c in idx],
        "grid": z,                     # 负 z 表示更平滑
        "heat": _save_overlay(f"{tag}_smooth.png", _upsample(_s_smooth(z), img.shape[:2])),
    }


# ---------------------------------------------------------------- 4. 频域指纹

def analysis_freq(img: np.ndarray) -> dict[str, Any]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape
    win = np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)
    F = np.fft.fftshift(np.fft.fft2(gray * win))
    mag = np.abs(F)                      # 不能用 log1p，否则破坏幂律

    cy, cx = h // 2, w // 2
    y, x = np.indices((h, w))
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2).astype(np.int32)
    r_max = min(cy, cx)

    radial = np.bincount(r.ravel(), weights=mag.ravel(), minlength=r_max + 2)
    count = np.bincount(r.ravel(), minlength=r_max + 2) + 1e-9
    profile = radial / count

    lo, hi = 3, max(6, int(r_max * 0.6))
    rr = np.arange(lo, hi)
    lp = np.log(profile[lo:hi] + 1e-9)
    lr = np.log(rr.astype(np.float64))
    slope, intercept = np.polyfit(lr, lp, 1)
    alpha = float(-slope)
    resid = lp - (slope * lr + intercept)
    peak_z = float(np.max(np.abs(resid)) / (resid.std() + 1e-6)) if resid.size > 5 else 0.0

    hf = float(profile[int(r_max * 0.5): r_max].sum() / (profile[1:r_max].sum() + 1e-9))

    # 只惩罚「过于平滑」：alpha 偏高说明高频被抹掉（生成图/强磨皮）；
    # alpha 偏低是高频纹理（织物、皮肤特写）的正常表现，不能作为异常。
    alpha_dev = max(0.0, alpha - 2.4) / 1.0
    score = float(np.clip(0.75 * np.clip(alpha_dev, 0, 1)
                          + 0.25 * np.clip((peak_z - 3.0) / 5.0, 0, 1), 0, 1))

    return {
        "available": True,
        "score": round(score, 4),
        "alpha": round(alpha, 3),
        "hf_ratio": round(hf, 4),
        "peak_z": round(peak_z, 2),
        "natural_alpha_range": [1.8, 2.4],
        "profile": [round(float(v), 2) for v in profile[1: min(r_max, 90)]],
    }


# ---------------------------------------------------------------- 5. 拷贝-移动

def analysis_copymove(gray: np.ndarray) -> dict[str, Any]:
    try:
        sift = cv2.SIFT_create(nfeatures=1500)
    except Exception:
        return {"available": False, "score": 0.0, "reason": "SIFT 不可用", "points": []}

    kp, des = sift.detectAndCompute(gray, None)
    if des is None or len(kp) < 20:
        return {"available": False, "score": 0.0, "reason": "特征点过少", "points": []}

    knn = cv2.BFMatcher(cv2.NORM_L2).knnMatch(des, des, k=8)
    h, w = gray.shape
    min_dist = 0.08 * max(h, w)
    good = []
    for group in knn:
        if len(group) < 2:
            continue
        for m in group[1:]:
            p1, p2 = kp[m.queryIdx].pt, kp[m.trainIdx].pt
            if m.distance < 0.55 * group[0].distance and np.hypot(p1[0] - p2[0], p1[1] - p2[1]) > min_dist:
                good.append((p1, p2))

    clusters = 0
    if len(good) >= 8:
        from sklearn.cluster import DBSCAN
        vecs = np.array([[p2[0] - p1[0], p2[1] - p1[1]] for p1, p2 in good], np.float32)
        labels = DBSCAN(eps=max(12.0, 0.02 * max(h, w)), min_samples=4).fit_predict(vecs)
        clusters = len([l for l in set(labels) if l != -1])

    score = float(np.clip(len(good) / 35.0, 0, 1) * (0.5 + 0.5 * min(1.0, clusters)))

    pts = []
    for p1, p2 in good[:16]:
        pts += [[int(p1[0]), int(p1[1])], [int(p2[0]), int(p2[1])]]

    return {
        "available": True,
        "score": round(score, 4),
        "keypoints": len(kp),
        "matches": len(good),
        "clusters": clusters,
        "pairs": [[[int(a[0]), int(a[1])], [int(b[0]), int(b[1])]] for a, b in good[:12]],
        "points": pts,
    }


# ---------------------------------------------------------------- 6. 元数据

GENERATOR_HINTS = ["stable diffusion", "midjourney", "dall", "photoshop", "美图", "snapseed",
                   "firefly", "comfyui", "novelai", "sd webui", "lightroom", "meitu"]


def analysis_meta(path: str) -> dict[str, Any]:
    from PIL import Image
    from PIL.ExifTags import TAGS

    info: dict[str, str] = {}
    try:
        with Image.open(path) as im:
            for k, v in im.getexif().items():
                if isinstance(v, (str, int, float)):
                    info[str(TAGS.get(k, k))] = str(v)[:80]
            fmt, size = im.format, im.size
    except Exception:
        return {"available": False, "score": 0.0, "reasons": []}

    hay = " ".join(f"{k}={v}" for k, v in info.items()).lower()
    hits = [g for g in GENERATOR_HINTS if g in hay]
    has_camera = any(k in info for k in ("Make", "Model"))

    score, reasons = 0.0, []
    if hits:
        score = min(1.0, 0.6 + 0.15 * len(hits))
        reasons.append(f"EXIF 中出现图像工具/生成器标识：{', '.join(hits)}")
    if not info:
        score = max(score, 0.25)
        reasons.append("完全没有 EXIF 信息（实拍照片通常带相机与拍摄参数）")
    elif not has_camera:
        score = max(score, 0.18)
        reasons.append("EXIF 存在但缺少相机厂商/型号字段")

    return {"available": True, "score": round(score, 4), "format": fmt, "size": size,
            "exif_keys": list(info.keys())[:12], "hits": hits, "reasons": reasons}


# ---------------------------------------------------------------- 7. 光照方向

def lighting_direction(img: np.ndarray) -> dict[str, Any]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=5)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=5)
    mag = np.hypot(gx, gy)
    ang = (np.arctan2(gy, gx) * 180 / np.pi) % 360

    theta = np.deg2rad(ang)
    cx = float((mag * np.cos(2 * theta)).sum())
    cy = float((mag * np.sin(2 * theta)).sum())
    mean_dir = (np.rad2deg(np.arctan2(cy, cx)) / 2) % 180

    hist, _ = np.histogram(ang, bins=36, range=(0, 360), weights=mag)
    return {"direction": round(float(mean_dir), 1),
            "concentration": round(float(hist.max() / (hist.sum() + 1e-9)), 3)}


# ---------------------------------------------------------------- 融合

def _regions(fused: np.ndarray, img_shape: tuple[int, int], top_k: int = 4) -> list[dict[str, Any]]:
    m = (fused > 0.40).astype(np.uint8)
    if m.sum() == 0:
        return []
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    h, w = img_shape
    bh, bw = max(h // BLOCK, 1), max(w // BLOCK, 1)
    out = []
    for i in range(1, n):
        x, y, ww, hh, area = stats[i]
        if area < 2:
            continue
        sub = fused[y:y + hh, x:x + ww]
        out.append({
            "bbox": [int(x * BLOCK), int(y * BLOCK), int(ww * BLOCK), int(hh * BLOCK)],
            "block_area": int(area),
            "area_ratio": round(float(area / max(bh * bw, 1)), 4),
            "peak": round(float(sub.max()), 3),
            "mean": round(float(sub.mean()), 3),
        })
    out.sort(key=lambda r: -r["peak"] * (r["block_area"] ** 0.3))
    return out[:top_k]


def analyze_image(path: str) -> dict[str, Any]:
    import time
    t0 = time.time()

    orig, img = _load(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 每个文件一个短指纹，避免两张图的热图互相覆盖
    tag = hashlib.md5(os.path.basename(path).encode("utf-8")).hexdigest()[:8]

    ela = analysis_ela(img, tag)
    noise = analysis_noise(img, tag)
    smooth = analysis_smooth(img, tag)
    freq = analysis_freq(img)
    cm = analysis_copymove(gray)
    meta = analysis_meta(path)
    light = lighting_direction(img)

    dims = {"ela": ela, "noise": noise, "smooth": smooth, "freq": freq, "copymove": cm, "meta": meta}
    avail = {k: v for k, v in dims.items() if v.get("available")}
    total_w = sum(WEIGHTS[k] for k in avail)
    score = sum(WEIGHTS[k] * avail[k].get("score", 0) for k in avail) / max(total_w, 1e-6)

    # 磨皮只对肤色区域有意义：浅色背景本身就没有纹理，不能判成"被磨皮"
    skin_block = None
    try:
        from app.tools.consistency import skin_mask
        skin = skin_mask(img).astype(np.float32) / 255.0
        skin_block = _blocks(skin) > 0.60
    except Exception:
        skin_block = None

    # 块级融合：三个局部信号在统一网格上加权
    fused = None
    acc = 0.0
    agree = None
    for k, w in (("ela", 0.40), ("noise", 0.32), ("smooth", 0.28)):
        g = dims[k].get("grid")
        if g is None:
            continue
        s = _s_smooth(g) if k == "smooth" else _s2(g)
        if k == "smooth" and skin_block is not None and s.shape == skin_block.shape:
            s = s * skin_block.astype(np.float32)
        fused = s * w if fused is None else fused + s * w
        acc += w
        hit = (s > 0.40).astype(np.float32)
        agree = hit if agree is None else agree + hit
    if fused is not None and acc > 0:
        fused = fused / acc
        # 多信号互证：只有 1 个信号异常时大幅抑制（正常纹理常出现单点异常）
        fused = fused * np.clip(agree - 1.0, 0.22, 1.0)
        for x, y in cm.get("points", []):
            bx, by = int(x / BLOCK), int(y / BLOCK)
            if 0 <= by < fused.shape[0] and 0 <= bx < fused.shape[1]:
                fused[by, bx] = min(1.0, fused[by, bx] + 0.35)
    else:
        fused = np.zeros((max(gray.shape[0] // BLOCK, 1), max(gray.shape[1] // BLOCK, 1)), np.float32)

    fused_heat = _save_overlay(f"{tag}_fused.png", _upsample(fused, img.shape[:2]))
    regions = _regions(fused, img.shape[:2])

    # 局部证据强度：面积小但信号确凿的篡改，同样应该把整图分数顶上去
    region_strength = 0.0
    for r in regions:
        s = (0.55 * r["peak"] + 0.45 * r["mean"]) * 1.3 * min(1.0, r["area_ratio"] / 0.03)
        region_strength = max(region_strength, s)
    score = max(score, region_strength)

    return {
        "path": path,
        "file": os.path.basename(path),
        "shape": [int(img.shape[1]), int(img.shape[0])],
        "score": round(float(np.clip(score, 0, 1)), 4),
        "dimensions": {k: _strip(v) for k, v in dims.items()},
        "lighting": light,
        "regions": regions,
        "heat": {"fused": fused_heat, "ela": ela.get("heat"),
                 "noise": noise.get("heat"), "smooth": smooth.get("heat")},
        "cost_ms": int((time.time() - t0) * 1000),
    }


def _strip(res: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in res.items() if k not in ("grid",)}
