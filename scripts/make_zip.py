"""把 data/test_package 打成提交用的 zip。

用 Python 的 zipfile 而不是 Compress-Archive：后者在 Windows 上写入的是
反斜杠路径，Linux / macOS 解压时会把 "sample_001\\meta.txt" 当成文件名。
"""
from __future__ import annotations

import os
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "data", "test_package")
DST = os.path.join(BASE, "deliverables", "测试数据包.zip")


def main() -> None:
    if not os.path.isdir(SRC):
        raise SystemExit(f"找不到数据包目录：{SRC}")

    files = []
    for root, dirs, names in os.walk(SRC):
        dirs.sort()
        for n in sorted(names):
            full = os.path.join(root, n)
            rel = os.path.relpath(full, SRC).replace("\\", "/")
            files.append((full, rel))

    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for full, rel in files:
            z.write(full, rel)

    size = os.path.getsize(DST) / 1024 / 1024
    print(f"打包完成：{len(files)} 个文件 → {DST}  {size:.1f} MB")

    with zipfile.ZipFile(DST) as z:
        names = z.namelist()
        bad = [n for n in names if "\\" in n]
        samples = sorted({n.split("/")[0] for n in names if n.startswith("sample_")})
        print(f"反斜杠路径：{len(bad)} 个（应为 0）")
        print(f"样本目录：{len(samples)} 个（{samples[0]} … {samples[-1]}）")
        print(f"根目录文件：{[n for n in names if '/' not in n]}")


if __name__ == "__main__":
    main()
