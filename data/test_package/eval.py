"""数据包自带评测脚本：输入系统输出目录，计算检测 P/R/F1 与定位 IoU。"""
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
