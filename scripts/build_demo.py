"""把应用打包成纯静态演示版，输出到 docs/，供 GitHub Pages 托管。

做法：
  1. 直接用 core.analyze 现算 4 组样例报告，连同图片/热图资产一起复制到 docs/cache/
  2. 复制前端资源，把 /static/ 与 /cache/ 改成相对路径
  3. 注入 demo-shim.js：拦截 fetch，把 /api/* 换成预置 JSON（页面本身一行代码都不用改）
  4. 预生成问答答案（调 qa.answer），保证演示时提问有内容
"""
from __future__ import annotations

import json
import os
import re
import shutil

from app import core, qa

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(BASE, "app", "web")
SAMPLES = os.path.join(BASE, "data", "samples")
CACHE = os.path.join(BASE, "app", "cache") if os.path.isdir(os.path.join(BASE, "app", "cache")) else core.CACHE_DIR
DOCS = os.path.join(BASE, "docs")

EXTRA_QUESTIONS = ["这个分数怎么来的", "为什么不是高风险", "证据够不够", "能不能再准一点"]

SCENE_CHIPS = {
    "post": ["为什么判这个等级", "改在哪一块", "文本文体怎么算的", "平台该怎么处置"],
    "comments": ["这些评论哪里异常", "发布节奏说明什么", "平台该怎么处置"],
    "material": ["这张图哪里有问题", "是不是 AI 生成", "平台该怎么处置"],
}


def load_samples() -> list[dict]:
    out = []
    for name in sorted(os.listdir(SAMPLES)):
        d = os.path.join(SAMPLES, name)
        meta_file = os.path.join(d, "meta.json")
        if not os.path.isfile(meta_file):
            continue
        with open(meta_file, encoding="utf-8") as f:
            meta = json.load(f)
        text = meta.get("text", "")
        if meta.get("text_file"):
            p = os.path.join(d, meta["text_file"])
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    text = f.read()
        comments = meta.get("comments", "")
        if meta.get("comments_file"):
            p = os.path.join(d, meta["comments_file"])
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    comments = f.read()
        imgs = [os.path.join(d, p) for p in meta.get("images", [])]
        scene = meta.get("scene", "post")
        rep = core.analyze(scene, text=text, image_paths=imgs, comments_text=comments,
                           title=meta.get("name", name))
        rep["id"] = name
        rep["inputs"] = {"text": text, "comments": comments,
                         "images": [im["url"] for im in rep.get("images", [])], "scene": scene}
        out.append({"id": name, "name": meta.get("name", name), "scene": scene, "report": rep})
    return out


def copy_assets(reports: list[dict]) -> int:
    dst = os.path.join(DOCS, "cache")
    os.makedirs(dst, exist_ok=True)
    n = 0
    for rep in reports:
        for im in rep.get("images", []):
            names = [im["url"]] + list((im.get("heat") or {}).values())
            for fn in names:
                src = os.path.join(CACHE, fn)
                if os.path.isfile(src):
                    shutil.copyfile(src, os.path.join(dst, fn))
                    n += 1
    return n


def build_answers(samples: list[dict]) -> dict[str, str]:
    answers = {}
    for s in samples:
        qs = SCENE_CHIPS.get(s["scene"], SCENE_CHIPS["post"]) + EXTRA_QUESTIONS
        for q in qs:
            answers[f"{s['id']}||{q}"] = qa.answer(s["report"], q)
    return answers


def main() -> None:
    samples = load_samples()
    copied = copy_assets([s["report"] for s in samples])
    answers = build_answers(samples)

    payload = {
        "samples": {sc: [{"id": s["id"], "name": s["name"]} for s in samples if s["scene"] == sc]
                    for sc in ("post", "comments", "material")},
        "reports": {s["id"]: s["report"] for s in samples},
        "answers": answers,
    }
    with open(os.path.join(DOCS, "demo-data.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write("window.__DEMO__ = ")
        json.dump(payload, f, ensure_ascii=False)
        f.write(";\n")

    # 前端资源
    html = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
    html = html.replace("/static/style.css", "./style.css")
    html = html.replace("/static/vendor/echarts.min.js", "./vendor/echarts.min.js")
    # 数据必须先于 shim 加载，否则 shim 初始化时读到的 __DEMO__ 还是空的
    html = html.replace('/static/app.js', './demo-data.js"></script>\n  <script src="./demo-shim.js"></script>\n  <script src="./app.js')
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(html)

    js = open(os.path.join(WEB, "app.js"), encoding="utf-8").read()
    js = js.replace("'/cache/'", "'./cache/'")
    with open(os.path.join(DOCS, "app.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write(js)

    css = open(os.path.join(WEB, "style.css"), encoding="utf-8").read()
    css += """
/* ---- 静态演示版 ---- */
.demo-banner {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin: 0 14px 10px; padding: 9px 12px; border-radius: 9px;
  background: rgba(255,176,32,.10); border: 1px solid rgba(255,176,32,.35);
  color: #ffd98a; font-size: 11.5px; line-height: 1.6;
}
.demo-banner b { color: #ffb020; }
.demo-banner a { color: #9fc8ff; }
body.demo #dropZone, body.demo .field-row .doc-btn, body.demo #btnDoc { display: none; }
"""
    with open(os.path.join(DOCS, "style.css"), "w", encoding="utf-8", newline="\n") as f:
        f.write(css)

    os.makedirs(os.path.join(DOCS, "vendor"), exist_ok=True)
    shutil.copyfile(os.path.join(WEB, "vendor", "echarts.min.js"),
                    os.path.join(DOCS, "vendor", "echarts.min.js"))
    shutil.copyfile(os.path.join(BASE, "scripts", "demo-shim.js"),
                    os.path.join(DOCS, "demo-shim.js"))

    print(f"样例 {len(samples)} 组，资产 {copied} 个文件，问答 {len(answers)} 条")


if __name__ == "__main__":
    main()
