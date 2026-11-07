"""Local LoRA frame-filtering primitives, no network or model required for tests."""
from __future__ import annotations

import base64
import io
import json
import math
import re
from dataclasses import dataclass
from PIL import Image, ImageFilter, ImageOps
import numpy as np

MAX_FRAME_BYTES = 1_250_000
MAX_FRAME_PIXELS = 2_200_000
DEFAULT_MODEL = 'qwen2.5vl:3b'


def clean_prompt(text: str) -> str:
    val = str(text).strip()
    if not 3 <= len(val) <= 900:
        raise ValueError('请提供3至900字的画面筛选要求')
    return val


def make_rule(prompt: str, old: dict | None = None) -> dict:
    """Simple *explicit* controls; semantic interpretation is done by the VLM."""
    prompt = clean_prompt(prompt)
    old = old or {}
    interval = float(old.get('interval_seconds', 4.0))
    match = re.search(r'(?:每隔?|间隔)\s*(\d+(?:\.\d+)?)\s*秒', prompt)
    if match:
        interval = float(match.group(1))
    capmatch = re.search(r'(?:最多|不超过|上限)\s*(?:保留|保存|采集|提取)?\s*(\d+)\s*(?:张|帧)', prompt)
    limit = int(capmatch.group(1)) if capmatch else int(old.get('max_frames', 120))
    return {
        'prompt': prompt,
        'interval_seconds': max(1.0, min(20.0, interval)),
        'max_frames': max(1, min(500, limit)),
        'dedup_hamming': max(0, min(20, int(old.get('dedup_hamming', 6)))),
        'min_sharpness': max(0.0, min(300.0, float(old.get('min_sharpness', 20.0)))),
        'model': DEFAULT_MODEL,
        'instructions': [clean_prompt(x) for x in old.get('instructions',[])[:12]] if isinstance(old.get('instructions'),list) else [],
    }


def read_image(data_url: str) -> tuple[Image.Image, bytes]:
    if not isinstance(data_url, str) or not data_url.startswith('data:image/jpeg;base64,'):
        raise ValueError('仅接受本地标签页捕获的 JPEG 图像')
    raw_b64 = data_url.split(',', 1)[1]
    if len(raw_b64) > 1_800_000:
        raise ValueError('图片包过大')
    try:
        raw = base64.b64decode(raw_b64, validate=True)
        if not 100 <= len(raw) <= MAX_FRAME_BYTES:
            raise ValueError('图片大小超限')
        image = Image.open(io.BytesIO(raw))
        if image.format != 'JPEG':
            raise ValueError('仅支持JPEG数据')
        if image.width * image.height > MAX_FRAME_PIXELS or image.width < 100 or image.height < 100:
            raise ValueError('图片分辨率不符合要求')
        image.load()
        return ImageOps.exif_transpose(image).convert('RGB'), raw
    except (OSError, ValueError, base64.binascii.Error) as exc:
        raise ValueError('JPEG解码失败或超过限制') from exc


def quality(image: Image.Image) -> tuple[float, int]:
    gray = ImageOps.grayscale(image).resize((160, 90))
    edges = np.asarray(gray.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    sharpness = float(np.var(edges))
    tiny = np.asarray(gray.resize((9, 8)), dtype=np.int16)
    bits = tiny[:, 1:] > tiny[:, :-1]
    h = 0
    for bit in bits.flat:
        h = (h << 1) | int(bit)
    return sharpness, h


def hamming(a: int, b: int) -> int:
    return (int(a) ^ int(b)).bit_count()


def parse_model_json(text: str) -> dict:
    if not isinstance(text, str):
        raise ValueError('模型返回的内容不是文本')
    trimmed = text.strip()
    trimmed = re.sub(r'^```(?:json)?\s*|\s*```$', '', trimmed, flags=re.I)
    try:
        item = json.loads(trimmed)
    except (json.JSONDecodeError, TypeError):
        found = re.search(r'\{[^{}]{1,3000}\}', trimmed, flags=re.S)
        if not found:
            raise ValueError('视觉模型没有返回可解析的JSON')
        item = json.loads(found.group())
    if not isinstance(item, dict) or not isinstance(item.get('match'), bool):
        raise ValueError('视觉模型没有给出明确的 match true/false')
    desc = str(item.get('caption', '')).strip().replace('\n', ' ')[:360]
    if item['match'] and len(desc) < 4:
        raise ValueError('模型接受画面但未生成有效标注')
    return {'match': item['match'], 'caption': desc, 'reason': str(item.get('reason',''))[:180]}


def safe_url(value: str) -> str:
    value = str(value or '')[:1600]
    if not re.match(r'^https://[^\s<>]+$', value):
        raise ValueError('只接受 HTTPS 视频来源地址')
    return value
