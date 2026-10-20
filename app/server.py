"""FastAPI 服务：静态页面 + 分析接口 + 示例样本 + 基于证据的问答。"""
from __future__ import annotations

import json
import os
import shutil
import tempfile

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import core, qa

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
CACHE = core.CACHE_DIR
SAMPLES = os.path.join(BASE, "data", "samples")

os.makedirs(CACHE, exist_ok=True)
os.makedirs(SAMPLES, exist_ok=True)

app = FastAPI(title="信任守护师 · 美妆内容真实性核验")
REPORTS: dict[str, dict] = {}
SAMPLE_CACHE: dict[str, dict] = {}

app.mount("/static", StaticFiles(directory=WEB), name="static")
app.mount("/cache", StaticFiles(directory=CACHE), name="cache")

# 静态演示版（docs/ 由 scripts/build_demo.py 生成，GitHub Pages 也用这份）
DEMO = os.path.join(BASE, "docs")
if os.path.isdir(DEMO):
    app.mount("/demo", StaticFiles(directory=DEMO, html=True), name="demo")


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"))


@app.post("/api/analyze")
async def api_analyze(scene: str = Form("post"), text: str = Form(""),
                      comments: str = Form(""), files: list[UploadFile] = File(default=[])):
    paths: list[str] = []
    tmp = tempfile.mkdtemp(prefix="trustshield_")
    try:
        for f in files:
            ext = os.path.splitext(f.filename or "")[1] or ".jpg"
            p = os.path.join(tmp, f"up_{len(paths)}{ext}")
            with open(p, "wb") as w:
                shutil.copyfileobj(f.file, w)
            paths.append(p)
        rep = core.analyze(scene, text=text, image_paths=paths, comments_text=comments)
        rid = f"r{len(REPORTS) + 1}"
        rep["id"] = rid
        REPORTS[rid] = rep
        return JSONResponse(rep)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)


@app.get("/api/samples")
def api_samples(scene: str = "post"):
    out = []
    if os.path.isdir(SAMPLES):
        for name in sorted(os.listdir(SAMPLES)):
            d = os.path.join(SAMPLES, name)
            meta_file = os.path.join(d, "meta.json")
            if not os.path.isfile(meta_file):
                continue
            try:
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                continue
            if meta.get("scene") != scene:
                continue
            out.append({"id": name, "name": meta.get("name", name)})
    return out


@app.get("/api/sample/{sid}")
def api_sample(sid: str):
    if sid in SAMPLE_CACHE:
        return JSONResponse(SAMPLE_CACHE[sid])
    d = os.path.join(SAMPLES, sid)
    meta_file = os.path.join(d, "meta.json")
    if not os.path.isfile(meta_file):
        return JSONResponse({"error": "样本不存在"}, status_code=404)
    try:
        with open(meta_file, encoding="utf-8") as f:
            meta = json.load(f)
        text = meta.get("text", "")
        if meta.get("text_file") and os.path.isfile(os.path.join(d, meta["text_file"])):
            with open(os.path.join(d, meta["text_file"]), encoding="utf-8") as f:
                text = f.read()
        comments = meta.get("comments", "")
        if meta.get("comments_file") and os.path.isfile(os.path.join(d, meta["comments_file"])):
            with open(os.path.join(d, meta["comments_file"]), encoding="utf-8") as f:
                comments = f.read()
        imgs = [os.path.join(d, p) for p in meta.get("images", [])]

        rep = core.analyze(meta.get("scene", "post"), text=text, image_paths=imgs,
                           comments_text=comments, title=meta.get("name", sid))
        rid = f"r{len(REPORTS) + 1}"
        rep["id"] = rid
        rep["inputs"] = {"text": text, "comments": comments,
                         "images": [im["url"] for im in rep.get("images", [])],
                         "scene": meta.get("scene", "post")}
        REPORTS[rid] = rep
        SAMPLE_CACHE[sid] = rep
        return JSONResponse(rep)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)


@app.post("/api/ask")
async def api_ask(payload: dict):
    rid = payload.get("id")
    q = payload.get("q", "")
    rep = REPORTS.get(rid)
    if not rep:
        return JSONResponse({"answer": "请先完成一次核验，我才能基于证据回答。"})
    return JSONResponse({"answer": qa.answer(rep, q)})


MAX_DOC_BYTES = 8 * 1024 * 1024
MAX_DOC_CHARS = 20000
TEXT_EXTS = {".txt", ".md", ".markdown", ".csv", ".log", ".text"}


def _decode_text(raw: bytes) -> str:
    """中文 txt 常见 GBK/GB18030，按可靠性依次尝试。"""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _docx_text(path: str) -> str:
    """.docx 本质是 zip，直接取 word/document.xml 里的文本，不引入额外依赖。"""
    import zipfile
    from xml.etree import ElementTree as ET

    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    lines = []
    for p in root.iter(f"{ns}p"):
        buf = [(t.text or "") for t in p.iter(f"{ns}t")]
        line = "".join(buf).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


@app.post("/api/extract")
async def api_extract(file: UploadFile = File(...)):
    """从文档里抽正文：.txt / .md / .docx。"""
    name = file.filename or "upload.txt"
    ext = os.path.splitext(name)[1].lower()
    raw = await file.read()

    if len(raw) > MAX_DOC_BYTES:
        return JSONResponse({"error": "文件超过 8 MB，请先裁剪后再导入"}, status_code=413)

    try:
        if ext == ".docx":
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
            try:
                tmp.write(raw)
                tmp.close()
                text = _docx_text(tmp.name)
            finally:
                os.unlink(tmp.name)
        elif ext == ".doc":
            return JSONResponse({"error": "旧版 .doc 无法直接解析，请另存为 .docx 或 .txt"}, status_code=400)
        elif ext == ".pdf":
            return JSONResponse({"error": "暂不支持 PDF，请复制正文，或另存为 .docx / .txt"}, status_code=400)
        else:
            text = _decode_text(raw)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"解析失败：{type(e).__name__}"}, status_code=400)

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return JSONResponse({"error": "文件里没有读到文字（可能是扫描件或图片型 PDF）"}, status_code=400)

    truncated = len(text) > MAX_DOC_CHARS
    text = text[:MAX_DOC_CHARS]
    return {"name": name, "ext": ext, "chars": len(text), "truncated": truncated, "text": text}


@app.get("/api/health")
def health():
    return {"ok": True, "reports": len(REPORTS)}
