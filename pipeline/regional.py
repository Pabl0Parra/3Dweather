"""Hourly regional frames (spec §5 steps 2, 4, 5): u, v, rain in {slug}-a.webp,
cloud in {slug}-b.webp, 73 frames in 8 columns, plus {slug}.json."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from PIL import Image

from .atmosphere import cloud_from_layers, rain_rate
from .codecs import encode_cloud, encode_rain, encode_wind
from .regions import REGIONS, Region, RegionGrid, region_peak, sample, smooth151
from .sprites import save_sprite

REGION_HOURS = 72
REGION_COLS = 8
WIND = ("wind_u_component_10m", "wind_v_component_10m")
CLOUD = ("cloud_cover_low", "cloud_cover_mid", "cloud_cover_high")


def region_hours(run: datetime) -> list[datetime]:
    return [run + timedelta(hours=h) for h in range(REGION_HOURS + 1)]


def hours_for_frame(run: datetime, t: datetime) -> list[datetime]:
    """Regional hours made at the globe frame at t: those in (t - 3 h, t], hour 0 at frame 0."""
    h = round((t - run) / timedelta(hours=1))
    return [run + timedelta(hours=k) for k in range(max(0, h - 2), min(h, REGION_HOURS) + 1)]


class _FullGridPrecip:
    """GFS precipitation steps on its own grid up to hour 72, for rain_rate(). The last hour
    reads only the step before it, as the reference's hour-72 rain peak shows."""

    def __init__(self, gfs, run: datetime):
        self.gfs = gfs
        last = run + timedelta(hours=REGION_HOURS)
        self._times = sorted(t for t in (datetime.strptime(v, "%Y-%m-%dT%H:%MZ").replace(tzinfo=gfs.run.tzinfo)
                                         for v in gfs.meta()["valid_times"]) if t <= last)

    def valid_times(self) -> list[datetime]:
        return self._times

    def field(self, t: datetime):
        return self.gfs.field_or_none("precipitation", t)


def pack_frames(frames: list[np.ndarray], cols: int, rows: int) -> Image.Image:
    h, w = frames[0].shape[:2]
    sheet = np.zeros((rows * h, cols * w, 3), np.uint8)
    for j, f in enumerate(frames):
        sheet[(j // cols) * h:(j // cols + 1) * h, (j % cols) * w:(j % cols + 1) * w] = f
    return Image.fromarray(sheet, "RGB")


class RegionalBuilder:
    def __init__(self, gfs, run: datetime, regions: list[Region] = REGIONS):
        self.gfs = gfs
        self.sg = gfs.source_grid
        self.precip = _FullGridPrecip(gfs, run)
        self.regions = [(r, RegionGrid.of(r, self.sg)) for r in regions]
        self.frames = {r.slug: {"a": [], "b": []} for r, _ in self.regions}
        self.peaks = {r.slug: {"wind": [], "rain": []} for r, _ in self.regions}

    def add_hour(self, t: datetime) -> None:
        u, v = (self.gfs.field(name, t) for name in WIND)
        layers = [self.gfs.field_or_none(name, t) for name in CLOUD]
        cloud = None if any(a is None for a in layers) else cloud_from_layers(*layers)
        rain = rain_rate(self.precip, t, smooth=False)
        for r, g in self.regions:
            ru, rv = sample(u, g), sample(v, g)
            rr = smooth151(sample(rain, g)) if rain is not None else np.full((g.h, g.w), np.nan, np.float32)
            rc = sample(cloud, g) if cloud is not None else np.full((g.h, g.w), np.nan, np.float32)
            self.frames[r.slug]["a"].append(np.dstack([encode_wind(ru), encode_wind(rv), encode_rain(rr)]))
            cb = encode_cloud(rc)
            self.frames[r.slug]["b"].append(np.dstack([cb, cb, cb]))
            self.peaks[r.slug]["wind"].append(region_peak(np.hypot(ru, rv), g))
            self.peaks[r.slug]["rain"].append(region_peak(rr, g))

    def write(self, out: Path, run_iso: str) -> None:
        rows = -(-(REGION_HOURS + 1) // REGION_COLS)
        for r, g in self.regions:
            fr = self.frames[r.slug]
            assert len(fr["a"]) == REGION_HOURS + 1, (r.slug, len(fr["a"]))
            for fam in "ab":
                save_sprite(pack_frames(fr[fam], REGION_COLS, rows), out / f"{r.slug}-{fam}.webp")
            manifest = {"region": r.slug, "run": run_iso, "hours": REGION_HOURS + 1, "cols": REGION_COLS,  # hours = frames, as the reference
                        **g.manifest_fields(), "focus": list(r.focus), "tz": r.tz, "place": r.place,
                        "cities": [list(c) for c in r.cities], "peaks": self.peaks[r.slug], "masked": False}
            (out / f"{r.slug}.json").write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                                                encoding="utf-8")
