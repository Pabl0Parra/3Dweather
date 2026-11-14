import numpy as np
from PIL import Image

from pipeline.sprites import chunk_frames, pack_chunk, save_sprite, unpack_frame


def test_chunk_ranges():
    assert list(chunk_frames(0)) == list(range(0, 8)) and list(chunk_frames(6)) == list(range(48, 57))


def test_layout_and_lossless_roundtrip(tmp_path):
    rng = np.random.default_rng(0)
    frames = [rng.integers(0, 256, (384, 768, 3), dtype=np.uint8) for _ in range(9)]
    img = pack_chunk(frames)
    assert img.size == (3072, 1152)
    save_sprite(img, tmp_path / "globe-w6.webp")
    back = Image.open(tmp_path / "globe-w6.webp")
    assert all((unpack_frame(back, j) == frames[j]).all() for j in range(9))
    assert not (tmp_path / "globe-w6.webp.part").exists()


def test_eight_frames_make_two_rows():
    assert pack_chunk([np.zeros((384, 768, 3), np.uint8)] * 8).size == (3072, 768)
