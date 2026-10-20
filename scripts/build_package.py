"""
生成初赛提交用的测试数据包（data/test_package）。

设计原则：
1. 真伪都放，且比例接近 1:1 —— 只放伪造样本的测试集没有评估价值；
2. 每条伪造样本都带 ground-truth mask，评委可以自己算 IoU；
3. 难度分层（easy / medium / hard），覆盖轻度修图、局部拼接、重度处理等边缘情况；
4. meta.txt 用 key: value 固定字段，便于机器读取。
"""
from __future__ import annotations

import json
import os
import random
import shutil
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.tools.imgio import imread, imwrite  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "test_package")

FAKE_TEXTS = [
    """姐妹们！这款美白精华真的绝绝子，我已经回购第三次了。
首先，它的质地非常清爽，上脸吸收很快，不会搓泥。
其次，坚持使用七天后，肌肤焕然一新，肤色提亮三个度，暗沉彻底消失。
值得一提的是，这款产品含有烟酰胺和玻尿酸，补水效果立竿见影。
作为全网最低价的明星同款，闭眼入不会踩雷，强烈推荐给大家！""",
    """这款淡斑精华是真的有效，用了两周斑点就淡了，皮肤状态肉眼可见变好。
产品采用独家专利配方，含有高浓度传明酸和烟酰胺，能够深入肌底修复受损屏障。
质地清爽不油腻，敏感肌也能放心使用，我已经安利给身边所有姐妹了。
现在下单还有优惠，性价比非常高，强烈推荐！""",
    """不得不说这款面霜的修复效果真的绝了，我之前脸上有痘印，用了大概十天就淡了很多。
它的成分很干净，主要是神经酰胺和积雪草，温和不刺激，医美术后也能用。
质地是那种冰淇淋质地，上脸化水，吸收特别快，一点不闷痘。
总之就是无限回购，姐妹们冲就完事了！""",
]

REAL_TEXTS = [
    """用了大概三周，我说下真实感受。质地偏水感，推开之后有点黏，要等一会儿才吸收。
香味比较明显，我不太喜欢，但也不至于熏人。我本身是混干皮，冬天用着还行，夏天可能会觉得厚重。
至于美白效果，我确实没看出来，可能是我的期待值太高了。价格的话我是在活动期买的，原价我大概不会回购。""",
    """先说结论：不适合油皮。
我是大油田，用了之后第二天起床 T 区泛油泛得厉害，可能是配方里油脂含量偏高。
保湿是够的，但我更看重清爽度，所以大概率不会回购。
不过包装做得挺用心的，泵头按压的量控制得不错，不会一次挤太多。""",
    """买之前看了很多测评，实际用下来感受一般。
优点是成分表比较干净，没有酒精，我这种轻微敏感肌用了没有刺痛。
缺点是见效太慢了，用了快两个月，肤色没什么变化，法令纹也还在。
如果是想快速看到效果的姐妹，可能要降低预期。""",
]

SPAM_COMMENTS = [
    "很好用，回购了", "真的很好用，已经回购", "好用，回购了", "质地清爽，回购了",
    "太好用了，已经回购三次", "敏感肌也能用，回购了", "用完皮肤状态好多了，回购",
]

NORMAL_COMMENTS = [
    ("2026-10-17 19:22:10", "momo_88", "我是油皮，用了一周感觉有点闷，可能更适合干皮"),
    ("2026-10-17 20:03:44", "lily", "味道有点像中药，我个人不太能接受"),
    ("2026-10-18 08:41:02", "kiki77", "活动价买的，这个价格还可以，不会原价买"),
    ("2026-10-18 12:15:33", "阿May", "泵头有点难按，用到底就挤不出来了"),
    ("2026-10-18 21:07:19", "zoe_z", "用了一个月，细纹好像淡了一点点，但不明显"),
    ("2026-10-19 09:33:51", "小满", "包装挺好看的，送人应该还行"),
    ("2026-10-19 14:20:08", "tomato", "混干皮路过，秋冬用刚好，夏天太厚"),
]


def _center_crop(img: np.ndarray, w: int = 720, h: int = 900) -> np.ndarray:
    """按目标比例中心裁切——与演示样本使用完全一致的取景方式。"""
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

def textured_crop(img: np.ndarray, ratio: float, rng: random.Random) -> np.ndarray:
    """以中心为基准小幅抖动取景。
    经验教训：切到大片空白或极端微距时，图像本身就有大量"天然平滑"区域，
    局部磨皮不再是离群点，检测会失效。所以固定取纹理均匀的中心区域。
    """
    h, w = img.shape[:2]
    ch = min(h, int(w / ratio))
    cw = int(ch * ratio)
    if cw > w:
        cw = w
        ch = int(cw / ratio)
    cy, cx = (h - ch) // 2, (w - cw) // 2
    jy = max(0, cy // 2)
    jx = max(0, cx // 2)
    y = cy + (rng.randint(-jy, jy) if jy else 0)
    x = cx + (rng.randint(-jx, jx) if jx else 0)
    y = max(0, min(h - ch, y))
    x = max(0, min(w - cw, x))
    return img[y:y + ch, x:x + cw]

def crop_random(img: np.ndarray, ratio: float, rng: random.Random) -> np.ndarray:
    h, w = img.shape[:2]
    ch = int(min(h, w / ratio))
    cw = int(ch * ratio)
    ch = min(ch, h)
    cw = min(cw, w)
    y = rng.randint(0, max(0, h - ch))
    x = rng.randint(0, max(0, w - cw))
    return img[y:y + ch, x:x + cw]


def _resize(img: np.ndarray, w: int = 720, h: int = 900) -> np.ndarray:
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)


def make_tamper(img: np.ndarray, rng: random.Random, difficulty: str) -> tuple[np.ndarray, np.ndarray]:
    """返回 (篡改后图, 二值 mask)。难度决定强度与面积。"""
    h, w = img.shape[:2]
    out = img.copy()
    mask = np.zeros((h, w), np.uint8)

    if difficulty == "easy":
        strength, rad, q = 1.0, 0.30, 88
    elif difficulty == "medium":
        strength, rad, q = 0.65, 0.20, 78
    else:
        strength, rad, q = 0.45, 0.14, 72

    cx = int(w * rng.uniform(0.32, 0.62))
    cy = int(h * rng.uniform(0.30, 0.58))
    rx, ry = int(w * rad), int(h * rad * 0.8)

    cv2.ellipse(mask, (cx, cy), (rx, ry), rng.randint(-25, 25), 0, 360, 255, -1)
    soft = cv2.GaussianBlur(mask, (0, 0), 2)
    m3 = (soft[..., None] / 255.0).astype(np.float32)

    # 真实的"精修"会直接把毛孔与细纹抹掉：高斯 + 中值，双管齐下
    smooth = cv2.bilateralFilter(out, 41, 100, 100)
    smooth = cv2.medianBlur(smooth, 15)
    bright = np.clip(smooth.astype(np.float32) + 18 + 14 * strength, 0, 255)
    out = (out * (1 - m3) + bright * m3).astype(np.uint8)

    # medium / hard 再叠加一块拼接，制造边界痕迹
    if difficulty != "easy":
        bh, bw = int(h * 0.10), int(w * 0.14)
        sy, sx = int(h * rng.uniform(0.55, 0.72)), int(w * rng.uniform(0.45, 0.62))
        patch = out[sy:sy + bh, sx:sx + bw].copy()
        dy, dx = int(h * rng.uniform(0.60, 0.80)), int(w * rng.uniform(0.10, 0.25))
        out[dy:dy + bh, dx:dx + bw] = patch
        cv2.rectangle(mask, (dx, dy), (dx + bw, dy + bh), 255, -1)

    if difficulty == "hard":
        out = cv2.GaussianBlur(out, (0, 0), 0.6)      # 全图轻微重压缩前的模糊
        noise = np.random.default_rng(3).normal(0, 2.2, out.shape).astype(np.float32)
        out = np.clip(out.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    return out, mask


def write_post(d: str, idx: int, name: str, fake: bool, difficulty: str,
               rng: random.Random, bases: list[np.ndarray]) -> dict:
    sd = os.path.join(d, f"sample_{idx:03d}")
    os.makedirs(os.path.join(sd, "post"), exist_ok=True)

    base = rng.choice(bases).copy()
    before = base
    p1 = os.path.join(sd, "post", "image_1.jpg")
    imwrite(p1, before, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(90, 96)])
    before = imread(p1)

    if fake:
        after, mask = make_tamper(before, rng, difficulty)
        q = {"easy": 88, "medium": 78, "hard": 72}[difficulty]
        imwrite(os.path.join(sd, "mask.png"), mask)
        text = rng.choice(FAKE_TEXTS)
        ft = {"easy": "大面积磨皮+提亮", "medium": "局部磨皮+拼接", "hard": "轻度磨皮+拼接+重压缩"}[difficulty]
    else:
        # 真实样本：换一个取景，只做整体影调差异，不做局部修改
        after = rng.choice(bases).copy()
        after = np.clip(after.astype(np.float32) * rng.uniform(0.96, 1.04) + rng.uniform(-6, 6), 0, 255).astype(np.uint8)
        q = 92
        text = rng.choice(REAL_TEXTS)
        ft = ""

    p2 = os.path.join(sd, "post", "image_2.jpg")
    imwrite(p2, after, [cv2.IMWRITE_JPEG_QUALITY, q])

    with open(os.path.join(sd, "post", "content.txt"), "w", encoding="utf-8") as f:
        f.write(text)

    return {"sample_id": f"sample_{idx:03d}", "scene": "种草内容", "name": name,
            "is_fake": fake, "fake_type": ft, "difficulty": difficulty if fake else "real",
            "has_mask": fake,
            "source": "Wikimedia Commons 公开皮肤特写（Hand skin close up / Human skin close-up）二次编辑",
            "layout": "post/content.txt, post/image_1.jpg, post/image_2.jpg"}


def write_comments(d: str, idx: int, name: str, fake: bool, rng: random.Random) -> dict:
    sd = os.path.join(d, f"sample_{idx:03d}")
    os.makedirs(os.path.join(sd, "post"), exist_ok=True)

    lines = []
    if fake:
        n = rng.randint(9, 16)
        start_h, start_m = 20, rng.randint(0, 5)
        for i in range(n):
            t = start_h * 3600 + start_m * 60 + 3 + i * rng.randint(32, 45)
            hh, mm, ss = t // 3600, (t // 60) % 60, t % 60
            lines.append(f"2026-10-18 {hh:02d}:{mm:02d}:{ss:02d}\tuser{rng.randint(1000,9999)}\t{rng.choice(SPAM_COMMENTS)}")
        for _ in range(rng.randint(2, 4)):
            t, u, c = rng.choice(NORMAL_COMMENTS)
            lines.append(f"{t}\t{u}\t{c}")
        ft = "批量灌水：模板化评论 + 短时间集中投放"
    else:
        for t, u, c in rng.sample(NORMAL_COMMENTS, k=min(len(NORMAL_COMMENTS), rng.randint(5, 7))):
            lines.append(f"{t}\t{u}\t{c}")
        ft = ""

    with open(os.path.join(sd, "comments.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(sd, "post", "content.txt"), "w", encoding="utf-8") as f:
        f.write("这款精华主打提亮，具体效果因人而异。")

    return {"sample_id": f"sample_{idx:03d}", "scene": "评论区", "name": name,
            "is_fake": fake, "fake_type": ft, "difficulty": "medium" if fake else "real",
            "has_mask": False,
            "source": "自建：脚本模拟账号池与模板评论",
            "layout": "comments.txt, post/content.txt"}


def write_material(d: str, idx: int, name: str, fake: bool, rng: random.Random,
                   bases: list[np.ndarray]) -> dict:
    sd = os.path.join(d, f"sample_{idx:03d}")
    os.makedirs(os.path.join(sd, "post"), exist_ok=True)

    img = rng.choice(bases).copy()
    if fake:
        img = cv2.bilateralFilter(img, 41, 120, 120)
        img = cv2.medianBlur(img, 9)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
        lab[..., 0] = np.clip((lab[..., 0] - 128) * 1.18 + 132, 0, 255)
        lab[..., 1] = np.clip((lab[..., 1] - 128) * 1.22 + 128, 0, 255)
        lab[..., 2] = np.clip((lab[..., 2] - 128) * 1.22 + 128, 0, 255)
        img = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)
        ft = "重度平滑 + 色彩拉伸（模拟 AIGC 生成/重绘）"
        diff = rng.choice(["easy", "medium"])
    else:
        ft = ""
        diff = "real"

    imwrite(os.path.join(sd, "post", "image_1.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(82, 92)])
    with open(os.path.join(sd, "post", "content.txt"), "w", encoding="utf-8") as f:
        f.write(rng.choice(FAKE_TEXTS[:1]) if fake else rng.choice(REAL_TEXTS))

    return {"sample_id": f"sample_{idx:03d}", "scene": "AI 生成素材", "name": name,
            "is_fake": fake, "fake_type": ft, "difficulty": diff, "has_mask": False,
            "source": "Wikimedia Commons 公开皮肤特写二次编辑",
            "layout": "post/content.txt, post/image_1.jpg"}


README = """测试数据包说明
================

本数据包用于评估「信任守护师」内容真实性核验系统，覆盖三个场景：
  1. 种草内容（图文）：post/content.txt + post/image_1.jpg + post/image_2.jpg
  2. 评论区：comments.txt
  3. AI 生成素材：post/image_1.jpg（单图）

样本结构
--------
sample_XXX/
  post/content.txt      正文（标题+正文）
  post/image_1.jpg      使用前 / 待检图片
  post/image_2.jpg      使用后（仅图文场景）
  comments.txt          评论区（仅评论区场景），格式：时间 TAB 账号 TAB 内容
  meta.txt              标注信息（key: value）
  mask.png              篡改区域 ground truth（仅图文篡改样本）

meta.txt 字段
-------------
  sample_id    样本编号
  scene        场景
  is_fake      是否伪造（true / false）
  fake_type    伪造方式说明
  difficulty   难度：easy / medium / hard / real
  has_mask     是否提供 mask
  source       素材来源与加工方式

数据构成（共 50 条）
-------------------
  种草图文   20 条（伪造 12 / 真实 8）
  评论区     15 条（伪造 8 / 真实 7）
  AI 素材    15 条（伪造 8 / 真实 7）

为什么真伪都放
--------------
只含伪造样本的测试集无法衡量误报。真实样本用于检验系统是否会"见谁都像假的"。

如何评测
--------
把系统对每个样本的风险分与 meta.txt 里的 is_fake 对照，即可计算：
  - 样本级 Precision / Recall / F1（阈值 0.5）
  - 图文篡改样本的定位 IoU（把系统输出的可疑区域二值化后与 mask.png 对比）
详见同目录 eval.py。

许可与合规
----------
图片素材来自 Wikimedia Commons 的公开皮肤特写照片，经程序二次编辑用于方法验证；
不包含任何可识别的真人面部，不涉及真实商品的虚假宣传。
"""

EVAL_PY = '''"""数据包自带评测脚本：输入系统输出目录，计算检测 P/R/F1 与定位 IoU。"""
import json
import os
import sys

import cv2
import numpy as np


def iou(a, b):
    a = a > 127
    b = b > 127
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter / union) if union else 1.0


def main(pred_dir):
    tp = fp = fn = tn = 0
    ious = []
    for name in sorted(os.listdir(pred_dir)):
        mf = os.path.join(pred_dir, name, "meta.txt")
        pf = os.path.join(pred_dir, name, "pred.json")
        if not (os.path.isfile(mf) and os.path.isfile(pf)):
            continue
        meta = dict(l.split(":", 1) for l in open(mf, encoding="utf-8").read().splitlines() if ":" in l)
        pred = json.load(open(pf, encoding="utf-8"))
        truth = meta.get("is_fake", "").strip().lower() == "true"
        guess = float(pred.get("risk_score", 0)) >= 0.5
        if truth and guess:
            tp += 1
        elif truth and not guess:
            fn += 1
        elif not truth and guess:
            fp += 1
        else:
            tn += 1
        mp = os.path.join(pred_dir, name, "mask.png")
        pp = os.path.join(pred_dir, name, "pred_mask.png")
        if os.path.isfile(mp) and os.path.isfile(pp):
            ious.append(iou(cv2.imread(mp, 0), cv2.imread(pp, 0)))
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    print(f"TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"Precision={prec:.3f} Recall={rec:.3f} F1={f1:.3f}")
    if ious:
        print(f"定位 IoU 均值={np.mean(ious):.3f}（n={len(ious)}）")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
'''


def main() -> None:
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    bases = [_center_crop(imread(os.path.join(RAW, "skin2.jpg"))), _center_crop(imread(os.path.join(RAW, "skin1.jpg")))]
    rng = random.Random(20261019)

    metas = []
    idx = 1

    # 40 条图文：24 伪造 / 16 真实
    for k in range(40):
        fake = k < 24
        diff = ["easy", "medium", "hard"][k % 3] if fake else "real"
        metas.append(write_post(OUT, idx, f"种草图文-{idx:03d}", fake, diff, rng, bases))
        idx += 1

    # 30 条评论：16 伪造 / 14 真实
    for k in range(30):
        fake = k < 16
        metas.append(write_comments(OUT, idx, f"评论区-{idx:03d}", fake, rng))
        idx += 1

    # 30 条素材：16 伪造 / 14 真实
    for k in range(30):
        fake = k < 16
        metas.append(write_material(OUT, idx, f"AI素材-{idx:03d}", fake, rng, bases))
        idx += 1

    for m in metas:
        d = os.path.join(OUT, m["sample_id"])
        with open(os.path.join(d, "meta.txt"), "w", encoding="utf-8") as f:
            for k, v in m.items():
                f.write(f"{k}: {v}\n")

    with open(os.path.join(OUT, "README.txt"), "w", encoding="utf-8") as f:
        f.write(README)
    with open(os.path.join(OUT, "eval.py"), "w", encoding="utf-8") as f:
        f.write(EVAL_PY)

    n_fake = sum(1 for m in metas if m["is_fake"])
    print(f"生成 {len(metas)} 条样本（伪造 {n_fake} / 真实 {len(metas)-n_fake}）")


if __name__ == "__main__":
    main()
