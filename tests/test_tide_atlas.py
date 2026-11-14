import json
import math
from pathlib import Path

import h5py
import numpy as np
import pytest
from PIL import Image

from pipeline.tide_atlas import (ATLAS_H, ATLAS_W, build_tide_atlas, drop_artifacts, encode_atlas,
                                 read_constituent, to_atlas_grid)
from pipeline.tide_astro import CONSTITUENTS

STEP = 0.25  # synthetic files use 1/4 degree nodes (EOT20 uses 1/8); same layout otherwise


def write_eot(folder: Path, name: str, amp_cm, phase_deg):
    """An EOT20-style file: nodes lat -90..90, lon 0..360 inclusive, 0 = land."""
    lat = np.arange(-90, 90 + STEP / 2, STEP)
    lon = np.arange(0, 360 + STEP / 2, STEP)
    shape = (lat.size, lon.size)
    folder.mkdir(parents=True, exist_ok=True)
    with h5py.File(folder / f"{name.upper()}_ocean_eot20.nc", "w") as f:
        f["lat"], f["lon"] = lat, lon
        f["amplitude"] = np.broadcast_to(amp_cm, shape) if np.ndim(amp_cm) == 0 else amp_cm
        f["phase"] = np.broadcast_to(phase_deg, shape) if np.ndim(phase_deg) == 0 else phase_deg
    return lat, lon


def test_read_constituent_puts_lon_minus180_first_and_north_up(tmp_path):
    lat = np.arange(-90, 90 + STEP / 2, STEP)
    lon = np.arange(0, 360 + STEP / 2, STEP)
    amp = np.tile(lon, (lat.size, 1)) + 1.0  # amplitude encodes the longitude
    write_eot(tmp_path, "m2", amp, 0.0)
    la, lo, a, p = read_constituent(tmp_path, "m2")
    assert la[0] == 90 and la[-1] == -90 and lo[0] == -180 and lo[-1] == 180
    assert a[0, 0] == pytest.approx((180 + 1.0) / 100) and a[0, -1] == pytest.approx((180 + 1.0) / 100)  # cm -> m
    assert a[0, lo.tolist().index(0.0)] == pytest.approx(0.01)


def test_constant_field_regrids_exactly(tmp_path):
    write_eot(tmp_path, "m2", 120.0, 30.0)
    X, Y, sea = to_atlas_grid(*read_constituent(tmp_path, "m2"))
    assert X.shape == (ATLAS_H, ATLAS_W) == (360, 720) and sea.all()
    assert np.allclose(X, 1.2 * math.cos(math.radians(30))) and np.allclose(Y, 1.2 * math.sin(math.radians(30)))


def test_coastal_cells_average_only_their_sea_nodes(tmp_path):
    lat = np.arange(-90, 90 + STEP / 2, STEP)
    lon = np.arange(0, 360 + STEP / 2, STEP)
    amp = np.full((lat.size, lon.size), 100.0)
    amp[:, (lon > 10.0) & (lon < 10.5)] = 0.0       # land strip inside the cell 10..10.5 E
    amp[:, (lon > 20.0 - 1e-9) & (lon < 20.5 + 1e-9)] = 0.0  # every node of the cell 20..20.5 E is land
    amp[:, (lon > 10.5) & (lon < 11)] = 300.0
    write_eot(tmp_path, "m2", amp, 0.0)
    X, Y, sea = to_atlas_grid(*read_constituent(tmp_path, "m2"))
    col = lambda e: int(round((e + 179.75) / 0.5))
    assert X[100, col(10.25)] == pytest.approx(1.0)  # only the edge nodes (1 m) are sea
    assert not sea[100, col(20.25)] and X[100, col(20.25)] == 0 and Y[100, col(20.25)] == 0
    assert sea[100, col(30.25)]


def test_no_blend_across_the_antimeridian(tmp_path):
    lat = np.arange(-90, 90 + STEP / 2, STEP)
    lon = np.arange(0, 360 + STEP / 2, STEP)
    amp = np.where(lon[None, :] < 180, 50.0, 200.0) * np.ones((lat.size, 1))  # east half 0.5 m, west half 2 m
    write_eot(tmp_path, "m2", amp, 0.0)
    X, _, _ = to_atlas_grid(*read_constituent(tmp_path, "m2"))
    assert X[100, 0] == pytest.approx(2.0)      # cell -180..-179.5 (west half)
    # cell 179.5..180: nodes 179.5, 179.75 (0.5 m) and its edge node 180 = -180 (2 m) at half weight
    assert X[100, -1] == pytest.approx((0.5 * 0.5 + 0.5 + 0.5 * 2.0) / 2)


def decode(img, amax, k):
    out = []
    for comp in (0, 1):
        tile, sub = divmod(2 * k + comp, 3)
        out.append((img[tile * ATLAS_H:(tile + 1) * ATLAS_H, :, sub].astype(float) - 128) / 127 * amax)
    return out


def test_encode_round_trips_within_one_byte_and_caps_the_top_cells():
    """amax is the 99.99th percentile of cell amplitude; the few cells above it keep their
    phase and are scaled down to amax (EOT20 has estuary artifacts there)."""
    rng = np.random.default_rng(1)
    fields = {}
    for c in CONSTITUENTS:
        A, G = rng.uniform(0, 2, (ATLAS_H, ATLAS_W)), rng.uniform(-math.pi, math.pi, (ATLAS_H, ATLAS_W))
        fields[c] = (A * np.cos(G), A * np.sin(G), np.ones((ATLAS_H, ATLAS_W), bool))
    img, amax = encode_atlas(fields)
    assert img.shape == (ATLAS_H * 6, ATLAS_W, 3) and img.dtype == np.uint8
    for k, c in enumerate(CONSTITUENTS):
        X, Y, _ = fields[c]
        A = np.hypot(X, Y)
        assert amax[c] == pytest.approx(np.percentile(A, 99.99), abs=1e-4)
        dx, dy = decode(img, amax[c], k)
        ok = A <= amax[c]
        assert np.abs(dx - X)[ok].max() <= amax[c] / 127 and np.abs(dy - Y)[ok].max() <= amax[c] / 127
        top = ~ok
        assert top.sum() < 0.001 * A.size
        assert np.allclose(np.hypot(dx, dy)[top], amax[c], atol=2 * amax[c] / 127)
        assert np.allclose(np.arctan2(dy, dx)[top], np.arctan2(Y, X)[top], atol=0.05)
    assert (img[5 * ATLAS_H:, :, 1] == 255).all() and (img[5 * ATLAS_H:, :, 2] == 0).all()


def test_drop_artifacts_removes_isolated_huge_amplitudes():
    a = np.full((100, 100), 0.5)
    a[0, :] = np.nan
    a[50, 50] = 31.0  # the St. Lawrence S2 value
    out = drop_artifacts(a)
    assert np.isnan(out[50, 50]) and np.nanmax(out) == 0.5 and np.isnan(out[0]).all()


def test_build_writes_png_and_json(tmp_path):
    for k, c in enumerate(CONSTITUENTS):
        write_eot(tmp_path / "eot", c, 10.0 * (k + 1), 15.0 * k)
    build_tide_atlas(tmp_path / "eot", tmp_path / "out")
    meta = json.loads((tmp_path / "out" / "tide.json").read_text())
    assert meta["cons"] == CONSTITUENTS and meta["w"] == 720 and meta["h"] == 360 and meta["tiles"] == 6
    assert meta["west"] == -179.75 and meta["north"] == 89.75 and meta["dlon"] == meta["dlat"] == 0.5
    assert meta["start"] == "2026-01-01T00:00:00Z" and len(meta["months"]) == 120 and len(meta["months"][0]) == 16
    assert meta["amax"]["m2"] == pytest.approx(0.1, abs=1e-4) and meta["amax"]["q1"] == pytest.approx(0.8, abs=1e-4)
    assert "EOT20" in meta["source"] and "CC BY 4.0" in meta["source"]
    # The image is named after its content, so a cached tide.json never pairs with another build's image.
    assert meta["png"].startswith("tide-") and meta["png"].endswith(".png") and len(meta["png"]) == len("tide-0123456789ab.png")
    with Image.open(tmp_path / "out" / meta["png"]) as img:
        assert img.size == (720, 2160) and img.mode == "RGB"
    assert not (tmp_path / "out" / "tide.png").exists()
    build_tide_atlas(tmp_path / "eot", tmp_path / "out")  # same input, same name
    assert json.loads((tmp_path / "out" / "tide.json").read_text())["png"] == meta["png"]


ROOT = Path(__file__).resolve().parent.parent
EOT20_ZIP = ROOT / "eot20" / "eot20.zip"
REF_TIDE = ROOT / "reference" / "thetidechart-capture" / "site" / "assets__globe__tide.json"


@pytest.mark.reference
@pytest.mark.skipif(not EOT20_ZIP.exists() or not REF_TIDE.exists(), reason="EOT20 download or reference capture missing")
def test_amax_against_the_reference_atlas(tmp_path):
    """Spec §9 tide atlas test. Ours is EOT20, theirs FES2022 (both 0.5 deg): measured ratios are
    1.03-1.13 for the semidiurnals and 1.26-1.56 for the diurnals, whose maxima sit in the Sea of
    Okhotsk where the two models differ most."""
    build_tide_atlas(EOT20_ZIP, tmp_path)
    ours = json.loads((tmp_path / "tide.json").read_text())["amax"]
    ref = json.loads(REF_TIDE.read_text())["amax"]
    for c in ("m2", "s2", "n2", "k2"):
        assert 0.9 <= ours[c] / ref[c] <= 1.2, (c, ours[c], ref[c])
    for c in ("k1", "o1", "p1", "q1"):
        assert 0.9 <= ours[c] / ref[c] <= 1.65, (c, ours[c], ref[c])
