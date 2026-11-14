"""Compare candidate rules against the captured reference run 2026111306.

Dev tool: needs the local reference/ folder (not in the repository).
Usage: python tools/compare_reference_rules.py MODE [MODE ...]
Modes: rain cloud atmos storm ocean
Prints the mean absolute byte difference per frame (0-7) for each candidate.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import codecs as C  # noqa: E402
from pipeline.grid import GLOBE  # noqa: E402
from pipeline.regrid import regrid  # noqa: E402
from pipeline.sources.openmeteo import OpenMeteoRun, RunIncomplete  # noqa: E402
from pipeline.sprites import unpack_frame  # noqa: E402

INPUTS = ROOT / "reference" / "openmeteo-inputs"
CAPTURE = ROOT / "reference" / "thetidechart-capture" / "site"
RUN = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)
FRAMES = range(8)


def src(model: str, run: datetime = RUN) -> OpenMeteoRun:
    return OpenMeteoRun(model, run, INPUTS, cache_run=RUN)


def ref(family: str, j: int, channel: int) -> np.ndarray:
    name = "globe-c.webp" if family == "c" else f"globe-{family}0.webp"
    img = Image.open(CAPTURE / f"wx__2026111306__{name}")
    return unpack_frame(img, j)[..., channel].astype(int)


def on_globe(s: OpenMeteoRun, var: str, t: datetime) -> np.ndarray | None:
    a = s.field_or_none(var, t)
    return None if a is None else regrid(a, s.source_grid, GLOBE)


def report(label: str, diffs: list[float]) -> None:
    print(f"  {label:<34} " + " ".join(f"{d:6.2f}" for d in diffs) + f"   mean {np.mean(diffs):.2f}")


def mad(ours: np.ndarray, theirs: np.ndarray, mask: np.ndarray | None = None) -> float:
    d = np.abs(ours.astype(int) - theirs)
    return float(d[mask].mean() if mask is not None else d.mean())


def frame_time(j: int) -> datetime:
    return RUN + timedelta(hours=3 * j)


def mode_rain() -> None:
    gfs = src("ncep_gfs013")
    print("rain (globe-a channel B)")
    print("  reference frame bytes>0:", [int((ref("a", j, 2) > 0).sum()) for j in FRAMES])

    def series(var: str, t: datetime) -> np.ndarray:
        try:
            g = on_globe(gfs, var, t)
        except RunIncomplete:  # before the run starts
            g = None
        return np.zeros((GLOBE.h, GLOBE.w), np.float32) if g is None else np.nan_to_num(g)

    for showers in (False, True):
        def p(t):
            out = series("precipitation", t)
            return out + series("showers", t) if showers else out
        tag = "+showers" if showers else ""
        cands = {
            f"r1 P(t){tag}": lambda t: p(t),
            f"r2 mean P(t-2..t){tag}": lambda t: (p(t) + p(t - timedelta(hours=1)) + p(t - timedelta(hours=2))) / 3,
            f"r3 P(t+1){tag}": lambda t: p(t + timedelta(hours=1)),
            f"r4 sum P(t-2..t){tag}": lambda t: p(t) + p(t - timedelta(hours=1)) + p(t - timedelta(hours=2)),
        }
        for label, fn in cands.items():
            report(label, [mad(C.encode_rain(fn(frame_time(j))), ref("a", j, 2)) for j in FRAMES])


def mode_cloud() -> None:
    gfs = src("ncep_gfs013")
    print("cloud (globe-b channel R)")
    cands = {
        "c1 linear": lambda x: C.encode_cloud(x),
        "c2 sqrt": lambda x: np.rint(np.sqrt(np.clip(np.nan_to_num(x), 0, 100) / 100) * 255).astype(np.uint8),
    }
    fields = [on_globe(gfs, "cloud_cover", frame_time(j)) for j in FRAMES]
    for label, fn in cands.items():
        report(label, [mad(fn(f) if f is not None else np.zeros((GLOBE.h, GLOBE.w), np.uint8), ref("b", j, 0))
                       for j, f in zip(FRAMES, fields)])


def mode_atmos() -> None:
    gfs, g25 = src("ncep_gfs013"), src("ncep_gfs025")
    ifs = src("ecmwf_ifs", RUN - timedelta(hours=6))
    print("atmosphere sanity")
    rows = {
        "wind u (a.R) gfs013": [], "wind v (a.G) gfs013": [], "temp (t.R) gfs013": [],
        "pressure (b.G) ifs": [], "pressure (b.G) gfs025": [], "gust (b.B) ifs": [], "gust (b.B) gfs025": [],
    }
    for j in FRAMES:
        t = frame_time(j)
        rows["wind u (a.R) gfs013"].append(mad(C.encode_wind(on_globe(gfs, "wind_u_component_10m", t)), ref("a", j, 0)))
        rows["wind v (a.G) gfs013"].append(mad(C.encode_wind(on_globe(gfs, "wind_v_component_10m", t)), ref("a", j, 1)))
        rows["temp (t.R) gfs013"].append(mad(C.encode_air_temp(on_globe(gfs, "temperature_2m", t)), ref("t", j, 0)))
        rows["pressure (b.G) ifs"].append(mad(C.encode_pressure(on_globe(ifs, "pressure_msl", t)), ref("b", j, 1)))
        rows["pressure (b.G) gfs025"].append(mad(C.encode_pressure(on_globe(g25, "pressure_msl", t)), ref("b", j, 1)))
        rows["gust (b.B) ifs"].append(mad(C.encode_gust(on_globe(ifs, "wind_gusts_10m", t)), ref("b", j, 2)))
        rows["gust (b.B) gfs025"].append(mad(C.encode_gust(on_globe(g25, "wind_gusts_10m", t)), ref("b", j, 2)))
    for label, d in rows.items():
        report(label, d)


def mode_storm() -> None:
    """Grid search for pipeline/storms.py: index = clip(k*cape^p) * clip(rain/g, 0, 1) * [LI < 0]."""
    import itertools
    g25 = src("ncep_gfs025")
    data = []
    for j in range(1, 8):  # frame 0 has no GFS rain
        t = frame_time(j)
        data.append((np.nan_to_num(on_globe(g25, "cape", t)), np.nan_to_num(on_globe(g25, "lifted_index", t)),
                     C.decode_rain(ref("a", j, 2)), ref("s", j, 0)))
    rows = []
    for k, p, g, li in itertools.product((0.05, 0.1, 0.2, 0.4), (0.75, 1.0), (0.1, 0.5, 1.0, 3.0), (False, True)):
        ious, mads = [], []
        for cape, lifted, rain, s in data:
            idx = np.clip(k * cape ** p, 0, 255) * np.clip(rain / g, 0, 1) * ((lifted < 0) if li else 1)
            b = np.rint(idx).astype(int)
            ious.append(((b > 0) & (s > 0)).sum() / max(((b > 0) | (s > 0)).sum(), 1))
            mads.append(np.abs(b - s).mean())
        rows.append((np.mean(ious), np.mean(mads), k, p, g, li))
    print("storm: IoU of storm cells, mean byte difference, k, p, g, lifted-index gate")
    for r in sorted(rows, reverse=True)[:5]:
        print("  ", " ".join(str(round(x, 3)) if isinstance(x, float) else str(x) for x in r))


if __name__ == "__main__":
    modes = {"rain": mode_rain, "cloud": mode_cloud, "atmos": mode_atmos, "storm": mode_storm}
    for m in sys.argv[1:] or ["rain", "cloud", "atmos"]:
        if m in modes:
            modes[m]()
        else:
            print(f"(mode {m} not added yet)")
