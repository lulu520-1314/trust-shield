"""额外生成一个「真实内容」对照样本，用于演示系统不会见谁都判假。"""
import json, os, sys
import cv2
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.tools.imgio import imread, imwrite

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "samples", "post_002")

REAL_TEXT = """用了大概三周，我说下真实感受。质地偏水感，推开之后有点黏，要等一会儿才吸收。
香味比较明显，我不太喜欢，但也不至于熏人。我本身是混干皮，冬天用着还行，夏天可能会觉得厚重。
至于提亮效果，我确实没看出来，可能是我的期待值太高了。价格的话我是在活动期买的，原价我大概不会回购。"""


def center_crop(img, w=720, h=900):
    ih, iw = img.shape[:2]
    target = w / h
    if iw / ih > target:
        nw = int(ih * target); x0 = (iw - nw) // 2; img = img[:, x0:x0 + nw]
    else:
        nh = int(iw / target); y0 = (ih - nh) // 2; img = img[y0:y0 + nh, :]
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)


def main():
    os.makedirs(OUT, exist_ok=True)
    a = center_crop(imread(os.path.join(RAW, "skin2.jpg")))
    imwrite(os.path.join(OUT, "before.jpg"), a, [cv2.IMWRITE_JPEG_QUALITY, 94])
    # 对照组：同一张图做整体影调微调（合法修图），没有任何局部改动
    b = np.clip(a.astype(np.float32) * 1.04 - 5, 0, 255).astype(np.uint8)
    imwrite(os.path.join(OUT, "after.jpg"), b, [cv2.IMWRITE_JPEG_QUALITY, 92])
    open(os.path.join(OUT, "content.txt"), "w", encoding="utf-8").write(REAL_TEXT)
    json.dump({"name": "真实测评 · 对照组", "scene": "post", "text_file": "content.txt",
               "images": ["before.jpg", "after.jpg"]},
              open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("post_002 ok")


if __name__ == "__main__":
    main()
