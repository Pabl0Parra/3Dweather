"""Compares our wave output with the reference site's captured run 2026111306.

Needs local material that is not in the repository (see .gitignore):
  reference/openmeteo-inputs/2026111306/   Open-Meteo inputs, saved by tools/save_reference_inputs.py
  reference/thetidechart-capture/site/     the captured reference sprite and manifest
Only day-chunk 0 of the reference sprites was captured, so frames 0-7 are compared.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pipeline.build import build_waves
from pipeline.grid import GLOBE
from pipeline.regrid import regrid_bilinear
from pipeline.sources.openmeteo import OpenMeteoRun
from pipeline.sprites import unpack_frame

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "reference" / "openmeteo-inputs" / "2026111306"
CAPTURE = ROOT / "reference" / "thetidechart-capture" / "site"
REF_SPRITE = CAPTURE / "wx__2026111306__globe-w0.webp"
REF_MANIFEST = CAPTURE / "wx__2026111306__globe.json"
RUN = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)

pytestmark = [
    pytest.mark.reference,
    pytest.mark.skipif(not (INPUTS / "ncep_gfswave025").is_dir() or not REF_SPRITE.exists(),
                       reason="local reference/ material not present"),
]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return build_waves(RUN, INPUTS, tmp_path_factory.mktemp("out"))


@pytest.fixture(scope="module")
def ours(built):
    return Image.open(built / "globe-w0.webp")


@pytest.fixture(scope="module")
def theirs():
    return Image.open(REF_SPRITE)


@pytest.fixture(scope="module")
def sea_mask():
    """Globe cells whose four native neighbours are all sea: open water, away from the coast fill."""
    src = OpenMeteoRun("ncep_gfswave025", RUN, INPUTS)
    valid = np.isfinite(src.field("wave_height", RUN)).astype(np.float32)
    return regrid_bilinear(valid, src.source_grid, GLOBE) > 0.999


def stats(ours, theirs, sea_mask, channel):
    out = []
    for j in range(8):
        a = unpack_frame(ours, j)[..., channel].astype(int)[sea_mask]
        b = unpack_frame(theirs, j)[..., channel].astype(int)[sea_mask]
        out.append(((a == b).mean(), np.abs(a - b).mean()))
    return out


def test_chunk0_height_matches_reference(ours, theirs, sea_mask):
    for j, (exact, mean_diff) in enumerate(stats(ours, theirs, sea_mask, 0)):
        assert exact >= 0.99, f"frame {j}: {exact:.4f} of sea cells match exactly"
        assert mean_diff <= 0.1, f"frame {j}: mean byte difference {mean_diff:.3f}"


def test_chunk0_vectors_match_reference(ours, theirs, sea_mask):
    for channel in (1, 2):
        for j, (_, mean_diff) in enumerate(stats(ours, theirs, sea_mask, channel)):
            assert mean_diff <= 1.0, f"frame {j} channel {channel}: mean byte difference {mean_diff:.3f}"


def test_peaks_match_reference(built):
    mine = json.loads((built / "globe.json").read_text())["peaks"]["wave"]
    ref = json.loads(REF_MANIFEST.read_text())["peaks"]["wave"]
    assert len(mine) == len(ref) == 169
    assert mine == ref  # every hour: same height, same cell


def test_manifest_grid_fields_identical(built):
    mine = json.loads((built / "globe.json").read_text())
    ref = json.loads(REF_MANIFEST.read_text())
    for key in ("w", "h", "north", "west", "dlon", "dlat", "every", "hours", "frames", "cols", "chunks"):
        assert mine[key] == ref[key], key
    assert mine["sources"]["wave"] == ref["sources"]["wave"]
