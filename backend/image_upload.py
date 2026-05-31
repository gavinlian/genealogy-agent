"""上传图片解码与保存（兼容 data URL、PNG/JPEG/WebP）。"""

from __future__ import annotations

import base64
import binascii
import os
import re
import uuid
from typing import Tuple

_DATA_URL_RE = re.compile(r"^data:image/[\w+.-]+;base64,", re.I)


def normalize_image_base64(raw: str) -> str:
    """去掉 data URL 前缀、空白，并补齐 base64 padding。"""
    text = (raw or "").strip()
    if not text:
        raise ValueError("缺少图片数据")
    text = _DATA_URL_RE.sub("", text)
    text = re.sub(r"\s+", "", text)
    pad = (-len(text)) % 4
    if pad:
        text += "=" * pad
    return text


def decode_image_bytes(raw: str) -> bytes:
    """解码 base64 / data URL 为二进制。"""
    normalized = normalize_image_base64(raw)
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", normalized):
        raise ValueError("图片 base64 含非法字符")
    try:
        data = base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"图片 base64 无效：{exc}") from exc
    if not data:
        raise ValueError("图片数据为空")
    return data


def detect_image_ext(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"RIFF") and len(data) > 12 and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    return "jpg"


def save_upload_image(upload_dir: str, raw: str) -> Tuple[str, bytes]:
    """解码并写入 uploads 目录，返回 (filename, bytes)。"""
    data = decode_image_bytes(raw)
    if len(data) < 32:
        raise ValueError("图片文件过小或已损坏")
    if len(data) > 25 * 1024 * 1024:
        raise ValueError("图片过大（上限 25MB），请先压缩后上传")
    ext = detect_image_ext(data)
    filename = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, filename)
    with open(path, "wb") as f:
        f.write(data)
    return filename, data
