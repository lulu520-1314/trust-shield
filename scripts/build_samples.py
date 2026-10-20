"""
构建演示样本（data/samples/*）。

素材来源：
  data/raw/skin2.jpg —— 手部皮肤特写，Wikimedia Commons「Hand skin close up.jpg」
  data/raw/skin1.jpg —— 皮肤特写，Wikimedia Commons「Human skin close-up.jpg」

「伪造」是可控的：我们知道改了哪块、怎么改的，用来验证系统能否定位。
"""
from __future__ import annotations

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.tools.imgio import imread, imwrite  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "samples")
RAW = os.path.join(ROOT, "data", "raw")

POST_TEXT = """姐妹们！这款美白精华真的绝绝子，我已经回购第三次了。
首先，它的质地非常清爽，上脸吸收很快，不会搓泥。
其次，坚持使用七天后，肌肤焕然一新，肤色提亮三个度，暗沉彻底消失。
值得一提的是，这款产品含有烟酰胺和玻尿酸，补水效果立竿见影。
作为全网最低价的明星同款，闭眼入不会踩雷，强烈推荐给大家！
"""

COMMENTS = """2026-10-18 20:01:03\tuser8821\t很好用，回购了
2026-10-18 20:01:41\tuser9932\t很好用，回购了
2026-10-18 20:02:18\tuser7745\t很好用，已经回购了
2026-10-18 20:02:55\tuser6612\t很好用，回购了
2026-10-18 20:03:30\tuser5501\t真的很好用，回购了
2026-10-18 20:04:12\tuser4433\t很好用，回购了
2026-10-18 20:05:01\tuser3320\t好用，回购了
2026-10-18 20:05:47\tuser2218\t很好用，回购了
2026-10-18 20:06:30\tuser1109\t很好用，已经回购
2026-10-18 20:07:15\tuser9987\t很好用，回购了
2026-10-18 20:08:02\tuser8876\t很好用，回购了
2026-10-18 20:09:11\tuser7765\t质地清爽不搓泥，用了一周感觉皮肤透亮一点，就是价格小贵
2026-10-18 21:30:00\tlisa_2019\t敏感肌用了没有泛红，但香味有点重
2026-10-18 22:10:00\tmomo\t买的是小样，感觉和正装味道不太一样
2026-10-19 09:20:00\tkiki88\t用了一个月，斑点好像淡了一点点，没宣传的那么夸张
2026-10-19 10:02:11\tuser7723\t很好用，回购了
2026-10-19 10:03:40\tuser6614\t很好用，回购了
2026-10-19 10:04:22\tuser5515\t很好用，回购了
"""

COMMENT_POST = "这款精华真的绝绝子，7 天就能白一个度，敏感肌也能用，闭眼入！"


def _crop(src: str, w: int = 720, h: int = 900) -> np.ndarray:
    """按目标比例中心裁剪并缩放。"""
    img = imread(src)
    if img is None:
        raise FileNotFoundError(src)
    ih, iw = img.shape[:2]
    target = w / h
    if iw / ih > target:
        nw = int(ih * target)
        x0 = (iw - nw) // 2
        img = img[:, x0:x0 + nw]
    else:
        nh = int(iw / target)
        y0 = (ih - nh) // 2
        img = img[y0:y0 + nh, :]
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)


def make_post_sample() -> None:
    d = os.path.join(OUT, "post_001")
    os.makedirs(d, exist_ok=True)

    before = _crop(os.path.join(RAW, "skin2.jpg"))
    p1 = os.path.join(d, "before.jpg")
    imwrite(p1, before, [cv2.IMWRITE_JPEG_QUALITY, 96])
    before = imread(p1)

    h, w = before.shape[:2]
    after = before.copy()

    # 1) 面颊/手背区域：提亮 + 强磨皮（美妆修图的标准动作）
    mask = np.zeros((h, w), np.uint8)
    cv2.ellipse(mask, (int(w * 0.46), int(h * 0.43)), (int(w * 0.27), int(h * 0.21)), -12, 0, 360, 255, -1)
    mask = cv2.GaussianBlur(mask, (81, 81), 0)
    m3 = (mask[..., None] / 255.0).astype(np.float32)

    smooth = cv2.bilateralFilter(after, 31, 95, 95)
    smooth = cv2.medianBlur(smooth, 11)
    bright = np.clip(smooth.astype(np.float32) + 22, 0, 255)
    after = (after * (1 - m3) + bright * m3).astype(np.uint8)

    # 2) 拼接：把右下角一块纹理复制到左侧，制造不自然的边界
    src = after[int(h * 0.68):int(h * 0.78), int(w * 0.60):int(w * 0.76)].copy()
    dx, dy = int(w * 0.14), int(h * 0.70)
    after[dy:dy + src.shape[0], dx:dx + src.shape[1]] = src

    p2 = os.path.join(d, "after.jpg")
    imwrite(p2, after, [cv2.IMWRITE_JPEG_QUALITY, 76])

    with open(os.path.join(d, "content.txt"), "w", encoding="utf-8") as f:
        f.write(POST_TEXT)
    json.dump({"name": "美白对比图 · 高仿", "scene": "post", "text_file": "content.txt",
               "images": ["before.jpg", "after.jpg"]},
              open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("post_001 ok")


def make_comments_sample() -> None:
    d = os.path.join(OUT, "comments_001")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "comments.txt"), "w", encoding="utf-8") as f:
        f.write(COMMENTS)
    json.dump({"name": "清一色好评 · 水军", "scene": "comments", "text": COMMENT_POST,
               "comments_file": "comments.txt"},
              open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("comments_001 ok")


def make_material_sample() -> None:
    d = os.path.join(OUT, "material_001")
    os.makedirs(d, exist_ok=True)
    img = _crop(os.path.join(RAW, "skin2.jpg"))
    h, w = img.shape[:2]

    # 模拟"AI 局部重绘"：只在局部区域重画，制造与周围不一致的噪声/纹理
    # （全图平滑反而检测不到——局部取证本来就是针对局部改动）
    mask = np.zeros((h, w), np.uint8)
    cv2.ellipse(mask, (int(w * 0.48), int(h * 0.46)), (int(w * 0.24), int(h * 0.19)), 8, 0, 360, 255, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), max(4, int(w * 0.012)))
    m3 = (mask[..., None] / 255.0).astype(np.float32)

    repaint = cv2.GaussianBlur(img, (0, 0), 2.6)
    repaint = cv2.medianBlur(repaint, 13)
    lab = cv2.cvtColor(repaint, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab[..., 0] = np.clip((lab[..., 0] - 128) * 1.16 + 134, 0, 255)
    lab[..., 1] = np.clip((lab[..., 1] - 128) * 1.20 + 128, 0, 255)
    lab[..., 2] = np.clip((lab[..., 2] - 128) * 1.20 + 128, 0, 255)
    repaint = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)
    img = (img * (1 - m3) + repaint * m3).astype(np.uint8)

    imwrite(os.path.join(d, "image.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 86])
    json.dump({"name": "局部重绘素材 · 高仿", "scene": "material",
               "text": "这瓶精华真的绝绝子，用完直接白到发光，2026 年必入榜第一名！",
               "images": ["image.jpg"]},
              open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("material_001 ok")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    make_post_sample()
    make_comments_sample()
    make_material_sample()
