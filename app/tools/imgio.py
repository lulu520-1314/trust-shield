"""Unicode 路径安全的图片读写。

OpenCV 在 Windows 上用 imread/imwrite 时无法处理非 ASCII 路径（例如「桌面」），
统一走 numpy 缓冲，彻底绕开。
"""
from __future__ import annotations

import os

import cv2
import numpy as np


def imread(path: str, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)


def imwrite(path: str, img: np.ndarray, params: list[int] | None = None) -> bool:
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img, params or [])
    if not ok:
        return False
    buf.tofile(path)
    return True
