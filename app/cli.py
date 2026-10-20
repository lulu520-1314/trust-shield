"""命令行入口：对单个样本跑完整链路，打印结构化结果并落盘热力图。

用法：
    python -m app.cli --scene post --text "文案..." --images a.jpg b.jpg
    python -m app.cli --scene comments --comments comments.txt
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import analyze  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="post", choices=["post", "comments", "material"])
    ap.add_argument("--text", default="")
    ap.add_argument("--text-file", default="")
    ap.add_argument("--comments", default="")
    ap.add_argument("--images", nargs="*", default=[])
    ap.add_argument("--title", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    text = args.text
    if args.text_file and os.path.exists(args.text_file):
        with open(args.text_file, encoding="utf-8") as f:
            text = f.read()
    comments = args.comments
    if args.comments and os.path.exists(args.comments):
        with open(args.comments, encoding="utf-8") as f:
            comments = f.read()

    report = analyze(args.scene, text=text, image_paths=args.images,
                     comments_text=comments, title=args.title)
    out = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
    print(out)


if __name__ == "__main__":
    main()
