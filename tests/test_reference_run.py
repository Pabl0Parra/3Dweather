"""Compares our output with the reference site's captured run 2026111306.

Needs local material that is not in the repository (see .gitignore):
  reference/openmeteo-inputs/2026111306/   Open-Meteo inputs (a cache folder keyed by run), saved by tools/save_reference_inputs.py
  reference/thetidechart-capture/site/     the captured reference sprites and manifest
Day-chunk 0 of the a, b, t, s, w sprites and the whole c file were captured, so
frames 0-7 (hours 0-21) are compared, and all 8 daily ocean frames.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pipeline.build import build_run
from pipeline.grid import GLOBE
from pipeline.regrid import regrid
from pipeline.sources.openmeteo import OpenMeteoRun
from pipeline.sprites import unpack_frame

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "reference" / "openmeteo-inputs"  # cache root: <run>/<model>/...
CAPTURE = ROOT / "reference" / "thetidechart-capture" / "site"
REF_MANIFEST = CAPTURE / "wx__2026111306__globe.json"
RUN = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)
CUR_RUN = datetime(2026, 11, 12, tzinfo=timezone.utc)

pytestmark = [
    pytest.mark.reference,
    pytest.mark.skipif(not (INPUTS / "2026111306" / "ncep_gfs013" / "cloud_cover_low").is_dir()
                       or not REF_MANIFEST.exists(), reason="local reference/ material not present"),
]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return build_run(RUN, INPUTS, tmp_path_factory.mktemp("out"))


def ours(built, family):
    return Image.open(built / ("globe-c.webp" if family == "c" else f"globe-{family}0.webp"))


def theirs(family):
    return Image.open(CAPTURE / f"wx__2026111306__{'globe-c.webp' if family == 'c' else f'globe-{family}0.webp'}")


@pytest.fixture(scope="module")
def sea_mask():
    """Globe cells whose four native neighbours are all sea: open water, away from the coast fill."""
    src = OpenMeteoRun("ncep_gfswave025", RUN, INPUTS)
    valid = np.isfinite(src.field("wave_height", RUN)).astype(np.float32)
    return regrid(valid, src.source_grid, GLOBE) > 0.999


@pytest.fixture(scope="module")
def ocean_mask():
    src = OpenMeteoRun("meteofrance_currents", CUR_RUN, INPUTS, cache_run=RUN)
    valid = np.isfinite(src.field("ocean_u_current", RUN)).astype(np.float32)
    return regrid(valid, src.source_grid, GLOBE) > 0.999


def diffs(built, family, channel, mask=None, frames=range(8)):
    """Per frame: (share of identical bytes, mean absolute byte difference)."""
    a_img, b_img = ours(built, family), theirs(family)
    out = []
    for j in frames:
        a = unpack_frame(a_img, j)[..., channel].astype(int)
        b = unpack_frame(b_img, j)[..., channel].astype(int)
        if mask is not None:
            a, b = a[mask], b[mask]
        out.append(((a == b).mean(), np.abs(a - b).mean()))
    return out


def assert_close(rows, limit, what):
    for j, (_, mean_diff) in enumerate(rows):
        assert mean_diff <= limit, f"{what} frame {j}: mean byte difference {mean_diff:.3f}"


# --- waves (phase 1) ---

def test_chunk0_height_matches_reference(built, sea_mask):
    for j, (exact, mean_diff) in enumerate(diffs(built, "w", 0, sea_mask)):
        assert exact >= 0.99, f"frame {j}: {exact:.4f} of sea cells match exactly"
        assert mean_diff <= 0.1, f"frame {j}: mean byte difference {mean_diff:.3f}"


def test_chunk0_vectors_match_reference(built, sea_mask):
    for channel in (1, 2):
        assert_close(diffs(built, "w", channel, sea_mask), 1.0, f"wave vector {channel}")


# --- phase 3a layers: mean byte difference over all cells (sea cells for the ocean file) ---

def test_chunk0_wind_rain_match(built):
    assert_close(diffs(built, "a", 0), 0.1, "wind u")
    assert_close(diffs(built, "a", 1), 0.1, "wind v")
    assert_close(diffs(built, "a", 2), 2.0, "rain")


def test_chunk0_pressure_gust_match(built):
    assert_close(diffs(built, "b", 1), 2.0, "pressure")
    assert_close(diffs(built, "b", 2), 2.0, "gust")


def test_chunk0_cloud_is_our_own_rule(built):
    """No tested rule reproduced the reference cloud; ours stays within about 17 levels (ledger, spec §8)."""
    assert_close(diffs(built, "b", 0), 20.0, "cloud")


def test_chunk0_temperature_matches(built):
    assert_close(diffs(built, "t", 0), 0.1, "air temperature")


def test_ocean_file_matches(built, ocean_mask):
    for channel, what in ((0, "current u"), (1, "current v"), (2, "sea temperature")):
        assert_close(diffs(built, "c", channel, ocean_mask), 0.5, what)


def test_storm_overlap(built):
    """Our own rule (spec §8): storm cells overlap the reference's by about 38 % (ledger)."""
    a_img, b_img = ours(built, "s"), theirs("s")
    ious = []
    for j in range(1, 8):  # frame 0 has no GFS rain
        a = unpack_frame(a_img, j)[..., 0] > 0
        b = unpack_frame(b_img, j)[..., 0] > 0
        ious.append((a & b).sum() / max((a | b).sum(), 1))
    assert np.mean(ious) >= 0.35, ious


# --- manifest ---

def cells_apart(p, q):
    (y1, x1), (y2, x2) = GLOBE.cell_of(p[1], p[2]), GLOBE.cell_of(q[1], q[2])
    dx = min(abs(x1 - x2), GLOBE.w - abs(x1 - x2))
    return max(abs(y1 - y2), dx)


def peak_agreement(built, key, hours=None):
    mine = json.loads((built / "globe.json").read_text())["peaks"][key]
    ref = json.loads(REF_MANIFEST.read_text())["peaks"][key]
    assert len(mine) == len(ref), key
    hours = hours if hours is not None else range(len(ref))
    bad = [h for h in hours if abs(mine[h][0] - ref[h][0]) > 0.5 or cells_apart(mine[h], ref[h]) > 2]
    return bad


def test_wave_peaks_identical(built):
    mine = json.loads((built / "globe.json").read_text())["peaks"]["wave"]
    assert mine == json.loads(REF_MANIFEST.read_text())["peaks"]["wave"]


@pytest.mark.parametrize("key", ["wind", "hot", "cold", "current"])
def test_peaks_match_every_hour(built, key):
    assert peak_agreement(built, key) == []


def peak_series(built, key):
    mine = json.loads((built / "globe.json").read_text())["peaks"][key]
    return mine, json.loads(REF_MANIFEST.read_text())["peaks"][key]


def test_sea_temperature_peak_values_match(built):
    """Values agree every hour; where two spots tie for the maximum the cell may differ."""
    mine, ref = peak_series(built, "sea_hot")
    assert all(abs(a[0] - b[0]) <= 0.5 for a, b in zip(mine, ref))


def test_gust_peaks_close(built):
    """IFS regridding differs slightly at the extremes (measured: median 1.2 m/s, 12 of 85 hours more than 2 cells away)."""
    mine, ref = peak_series(built, "gust")
    diffs = sorted(abs(a[0] - b[0]) for a, b in zip(mine, ref))
    assert diffs[len(diffs) // 2] <= 1.5
    assert sum(cells_apart(a, b) <= 2 for a, b in zip(mine, ref)) >= 0.8 * len(ref)


def test_rain_peaks_match_outside_hours_72_to_119(built):
    """Hours 72-119 differ (see spec §9: the reference's hourly rain there is not reproducible)."""
    bad = [h for h in peak_agreement(built, "rain") if not 72 <= h <= 119]
    assert len(bad) <= 3, bad


def test_low_pressure_peaks_match_while_ifs_runs(built):
    mine, ref = peak_series(built, "low")
    assert all(abs(mine[h][0] - ref[h][0]) <= 0.5 for h in range(0, 139))
    assert peak_agreement(built, "low", range(3, 139)) == []


def test_manifest_fields_identical(built):
    mine = json.loads((built / "globe.json").read_text())
    ref = json.loads(REF_MANIFEST.read_text())
    for key in ("w", "h", "north", "west", "dlon", "dlat", "every", "hours", "frames", "cols", "chunks",
                "pressure", "gust", "waves", "gustHours", "currents", "currentEvery", "storms", "currentFrames",
                "sources"):
        assert mine[key] == ref[key], key
