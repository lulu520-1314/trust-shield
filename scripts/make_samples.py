"""
生成用于自测的合成样本：一对「使用前 / 使用后」图片 + 文案 + 评论区。

做的是「可控伪造」：我们知道改了什么、改在哪，因此可以反过来验证系统能否定位。
真实用于演示的素材后续替换为实拍/公开授权图。
"""
from __future__ import annotations

import os
import random

import cv2
import numpy as np

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tools.imgio import imread, imwrite

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "synthetic")


def _skin_base(w: int, h: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    # 肤色渐变底
    y = np.linspace(0, 1, h)[:, None]
    x = np.linspace(0, 1, w)[None, :]
    base = np.zeros((h, w, 3), np.float32)
    base[..., 0] = 150 + 40 * y + 10 * x          # B
    base[..., 1] = 175 + 35 * y + 12 * x          # G
    base[..., 2] = 205 + 30 * y + 15 * x          # R
    # 纹理噪声（模拟皮肤毛孔）
    noise = rng.normal(0, 6, (h, w, 1)).repeat(3, axis=2)
    base += noise
    # 柔和阴影（模拟脸颊轮廓）
    yy, xx = np.mgrid[0:h, 0:w]
    for cx, cy, r, k in [(w * 0.35, h * 0.45, w * 0.22, -28), (w * 0.7, h * 0.6, w * 0.18, 18)]:
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        base += (k * np.exp(-(d / r) ** 2))[..., None]
    return np.clip(base, 0, 255).astype(np.uint8)


def make_pair(idx: int = 1, tamper: bool = True) -> tuple[str, str, list[tuple[int, int, int, int]]]:
    w, h = 620, 780
    before = _skin_base(w, h, seed=idx)

    # 先存成高质量 JPEG（建立第一次压缩历史）
    p1 = os.path.join(OUT, f"sample_{idx:03d}_before.jpg")
    imwrite(p1, before, [cv2.IMWRITE_JPEG_QUALITY, 95])
    before = imread(p1)

    after = before.copy()
    boxes = []
    if tamper:
        # 局部提亮（模拟"变白"）+ 贴一块来自别处的纹理（模拟拼接）
        mask = np.zeros((h, w), np.uint8)
        cv2.ellipse(mask, (int(w * 0.42), int(h * 0.40)), (int(w * 0.26), int(h * 0.20)), 0, 0, 360, 255, -1)
        mask = cv2.GaussianBlur(mask, (61, 61), 0)
        m3 = (mask[..., None] / 255.0).astype(np.float32)
        bright = np.clip(after.astype(np.float32) + 26, 0, 255)
        after = (after * (1 - m3) + bright * m3).astype(np.uint8)
        # 关键：区域内做磨皮（美妆修图最典型的手法），同时破坏噪声与高频纹理
        blurred = cv2.GaussianBlur(after, (0, 0), 3.2)
        after = (after * (1 - m3) + blurred * m3).astype(np.uint8)
        boxes.append((int(w * 0.42 - w * 0.26), int(h * 0.40 - h * 0.20), int(w * 0.52), int(h * 0.40)))

        # 拼接块：从右下复制一块到左上
        src = after[int(h * 0.62):int(h * 0.72), int(w * 0.55):int(w * 0.70)].copy()
        dst_x, dst_y = int(w * 0.18), int(h * 0.70)
        after[dst_y:dst_y + src.shape[0], dst_x:dst_x + src.shape[1]] = src
        boxes.append((dst_x, dst_y, src.shape[1], src.shape[0]))

        # 二次压缩，制造压缩历史不一致
        p2 = os.path.join(OUT, f"sample_{idx:03d}_after.jpg")
        imwrite(p2, after, [cv2.IMWRITE_JPEG_QUALITY, 78])
    else:
        p2 = os.path.join(OUT, f"sample_{idx:03d}_after.jpg")
        imwrite(p2, after, [cv2.IMWRITE_JPEG_QUALITY, 95])

    return p1, p2, boxes


POST_TEXT = """姐妹们！这款美白精华真的绝绝子，我已经回购第三次了。
首先，它的质地非常清爽，上脸吸收很快，不会搓泥。
其次，坚持使用七天后，肌肤焕然一新，肤色提亮三个度，暗沉彻底消失。
值得一提的是，这款产品含有烟酰胺和玻尿酸，补水效果立竿见影。
最后，作为全网最低价的明星同款，闭眼入不会踩雷，强烈推荐给大家！
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
2026-10-18 20:09:11\tuser7765\t质地清爽，不搓泥，用了一周感觉皮肤透亮了一些，就是价格有点小贵
2026-10-18 21:30:00\tlisa_2019\t敏感肌用了没有泛红，但香味有点重
2026-10-18 22:10:00\tmomo\t我买的是小样，感觉和正装味道不太一样
2026-10-19 09:20:00\tkiki88\t用了一个月，斑点好像淡了一点点，但没宣传的那么夸张
"""


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    p1, p2, boxes = make_pair(1, tamper=True)
    with open(os.path.join(OUT, "sample_001_content.txt"), "w", encoding="utf-8") as f:
        f.write(POST_TEXT)
    with open(os.path.join(OUT, "sample_001_comments.txt"), "w", encoding="utf-8") as f:
        f.write(COMMENTS)
    # 一张干净对照图（不篡改）
    make_pair(2, tamper=False)
    print("before:", p1)
    print("after :", p2)
    print("boxes :", boxes)


if __name__ == "__main__":
    main()
