"""通过 GitHub Git Data API 提交整个工作树（github.com 的 git 端口不可达时的替代方案）。

用法：
    GH_TOKEN=xxx python scripts/push_via_api.py
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = os.environ.get("GH_TOKEN", "")
OWNER = "lulu520-1314"
REPO = "trust-shield"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"
MSG = os.environ.get("PUSH_MSG", "chore: 同步仓库内容")
WORKERS = int(os.environ.get("PUSH_WORKERS", "4"))

if not TOKEN:
    sys.exit("缺少 GH_TOKEN")


def call(method: str, url: str, payload: dict | None = None, retry: int = 5):
    data = json.dumps(payload).encode() if payload is not None else None
    last = None
    for attempt in range(retry):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {TOKEN}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            last = f"{e.code}: {body[:200]}"
            if e.code in (401, 403, 429, 500, 502, 503):
                time.sleep(2.0 * (attempt + 1))
                continue
            raise RuntimeError(f"{method} {url} -> {last}")
        except Exception as e:  # noqa: BLE001
            last = str(e)
            time.sleep(2.0 * (attempt + 1))
            continue
    raise RuntimeError(f"{method} {url} -> {last}")


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p.decode("utf-8") for p in out.split(b"\x00") if p]


def make_blob(path: str) -> dict:
    with open(path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    r = call("POST", f"{API}/git/blobs", {"content": content, "encoding": "base64"})
    return {"path": path.replace("\\", "/"), "mode": "100644", "type": "blob", "sha": r["sha"]}


def main() -> None:
    files = tracked_files()
    print(f"待上传 {len(files)} 个文件（并发 {WORKERS}）")

    entries, failed = [], []
    # 大文件（>2MB）单独串行上传：并发时 GitHub 会偶发 400 malformed request
    big = [p for p in files if os.path.getsize(p) > 2 * 1024 * 1024]
    rest = [p for p in files if p not in big]
    for p in big:
        try:
            entries.append(make_blob(p))
            print(f"  大文件已上传 {p}")
        except Exception as e:  # noqa: BLE001
            failed.append((p, str(e)[:120]))

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(make_blob, p): p for p in rest}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                entries.append(fut.result())
                done += 1
                if done % 50 == 0:
                    print(f"  已上传 {done}/{len(rest)}")
            except Exception as e:  # noqa: BLE001
                failed.append((p, str(e)[:120]))

    if failed:
        print(f"失败 {len(failed)} 个：")
        for p, e in failed[:6]:
            print("  ", p, e)
        sys.exit(1)

    tree = call("POST", f"{API}/git/trees", {"tree": entries})
    print(f"tree: {tree['sha']}")

    parents = []
    try:
        ref = call("GET", f"{API}/git/ref/heads/main")
        parents = [ref["object"]["sha"]]
    except RuntimeError:
        parents = []

    commit = call("POST", f"{API}/git/commits",
                  {"message": MSG, "tree": tree["sha"], "parents": parents})
    print(f"commit: {commit['sha']}")

    if parents:
        call("PATCH", f"{API}/git/refs/heads/main", {"sha": commit["sha"], "force": True})
    else:
        call("POST", f"{API}/git/refs", {"ref": "refs/heads/main", "sha": commit["sha"]})
    print("已更新 refs/heads/main")


if __name__ == "__main__":
    main()
