"""Packs frames into the sprite sheets the globe reads: lossless WebP, 4 columns."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .grid import GLOBE

EVERY = 3
HOURS = 168
FRAMES = 57
COLS = 4
CHUNKS = [8, 8, 8, 8, 8, 8, 9]


def chunk_frames(chunk: int) -> range:
    """Global frame indices held by one day-chunk."""
    start = sum(CHUNKS[:chunk])
    return range(start, start + CHUNKS[chunk])


def pack_chunk(frames: list[np.ndarray]) -> Image.Image:
    """Frame j goes to column j % 4, row j // 4. Unused cells stay black."""
    rows = -(-len(frames) // COLS)
    sheet = np.zeros((rows * GLOBE.h, COLS * GLOBE.w, 3), dtype=np.uint8)
    for j, frame in enumerate(frames):
        y, x = (j // COLS) * GLOBE.h, (j % COLS) * GLOBE.w
        sheet[y:y + GLOBE.h, x:x + GLOBE.w] = frame
    return Image.fromarray(sheet, "RGB")


def save_sprite(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    img.save(part, format="WEBP", lossless=True, quality=100, method=6, exact=True)
    part.replace(path)


def unpack_frame(img: Image.Image, j: int) -> np.ndarray:
    y, x = (j // COLS) * GLOBE.h, (j % COLS) * GLOBE.w
    return np.asarray(img.convert("RGB"))[y:y + GLOBE.h, x:x + GLOBE.w]
