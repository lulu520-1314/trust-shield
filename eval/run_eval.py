"""
在自建测试包上跑完整评测：检测 P/R/F1 + 篡改定位 IoU + 分场景表现。

用法：python eval/run_eval.py [package_dir]
输出：eval/last_report.json 与终端汇总表。
"""
from __future__ import annotations

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core import analyze  # noqa: E402
from app.tools.imgio import imread  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "test_package")


def read_meta(d: str) -> dict[str, str]:
    p = os.path.join(d, "meta.txt")
    out: dict[str, str] = {}
    if os.path.isfile(p):
        for line in open(p, encoding="utf-8").read().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip()
    return out


def pred_mask_from_regions(regions: list[dict], shape: tuple[int, int]) -> np.ndarray:
    m = np.zeros(shape, np.uint8)
    for r in regions:
        x, y, w, h = r["bbox"]
        m[max(0, y):y + h, max(0, x):x + w] = 255
    return m


def iou(a: np.ndarray, b: np.ndarray) -> float:
    a = a > 127
    b = b > 127
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 1.0


def main() -> None:
    rows = []
    for name in sorted(os.listdir(PKG)):
        d = os.path.join(PKG, name)
        if not os.path.isdir(d):
            continue
        meta = read_meta(d)
        scene_cn = meta.get("scene", "")
        is_fake = meta.get("is_fake", "false").lower() == "true"

        text = ""
        cp = os.path.join(d, "post", "content.txt")
        if os.path.isfile(cp):
            text = open(cp, encoding="utf-8").read()
        comments = ""
        mp = os.path.join(d, "comments.txt")
        if os.path.isfile(mp):
            comments = open(mp, encoding="utf-8").read()

        imgs = []
        for fn in ("image_1.jpg", "image_2.jpg"):
            p = os.path.join(d, "post", fn)
            if os.path.isfile(p):
                imgs.append(p)

        if "评论" in scene_cn:
            scene = "comments"
        elif "素材" in scene_cn:
            scene = "material"
        else:
            scene = "post"

        rep = analyze(scene, text=text, image_paths=imgs, comments_text=comments, title=name)
        pred_fake = rep["risk"]["score"] >= 0.5

        row = {"sample": name, "scene": scene, "truth": is_fake, "score": rep["risk"]["score"],
               "level": rep["risk"]["level"], "pred": pred_fake,
               "difficulty": meta.get("difficulty", ""), "iou": None}

        mask_p = os.path.join(d, "mask.png")
        if os.path.isfile(mask_p) and rep.get("images"):
            gt = imread(mask_p, cv2.IMREAD_GRAYSCALE)
            pred_regions = rep["images"][-1].get("regions", [])
            shape = (rep["images"][-1]["shape"][1], rep["images"][-1]["shape"][0])
            pm = pred_mask_from_regions(pred_regions, shape)
            if gt is not None:
                gt = cv2.resize(gt, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
                row["iou"] = round(iou(gt, pm), 3)
        rows.append(row)

    tp = sum(1 for r in rows if r["truth"] and r["pred"])
    fn = sum(1 for r in rows if r["truth"] and not r["pred"])
    fp = sum(1 for r in rows if not r["truth"] and r["pred"])
    tn = sum(1 for r in rows if not r["truth"] and not r["pred"])
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)

    ious = [r["iou"] for r in rows if r["iou"] is not None]
    print(f"样本 {len(rows)} 条 | TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"Precision={prec:.3f}  Recall={rec:.3f}  F1={f1:.3f}")
    if ious:
        print(f"定位 IoU 均值={np.mean(ious):.3f}  中位数={np.median(ious):.3f}  n={len(ious)}")

    print("\n分场景：")
    for s in ("post", "comments", "material"):
        sub = [r for r in rows if r["scene"] == s]
        if not sub:
            continue
        stp = sum(1 for r in sub if r["truth"] and r["pred"])
        sfn = sum(1 for r in sub if r["truth"] and not r["pred"])
        sfp = sum(1 for r in sub if not r["truth"] and r["pred"])
        stn = sum(1 for r in sub if not r["truth"] and not r["pred"])
        sp = stp / max(stp + sfp, 1)
        sr = stp / max(stp + sfn, 1)
        sf = 2 * sp * sr / max(sp + sr, 1e-9)
        print(f"  {s:9} n={len(sub):2d}  P={sp:.2f} R={sr:.2f} F1={sf:.2f}")

    print("\n分难度（伪造样本）：")
    for diff in ("easy", "medium", "hard"):
        sub = [r for r in rows if r["truth"] and r["difficulty"] == diff]
        if sub:
            print(f"  {diff:7} n={len(sub):2d} 召回={sum(1 for r in sub if r['pred'])/len(sub):.2f}")

    out = os.path.join(ROOT, "eval", "last_report.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"summary": {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                           "precision": prec, "recall": rec, "f1": f1,
                           "iou_mean": float(np.mean(ious)) if ious else None},
               "rows": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n明细已写入 {out}")


if __name__ == "__main__":
    main()
