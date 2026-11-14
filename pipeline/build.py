"""Builds one run folder: every globe sprite family plus globe.json, and the 12 regional maps."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from .atmosphere import GUST_HOURS, cloud_from_layers, frame_a, frame_b, frame_t, rain_rate
from .grid import GLOBE
from .ocean import CURRENT_EVERY, CURRENT_FRAMES, ocean_frame, ocean_time, pack_ocean
from .peaks import hourly, peak
from .regions import REGIONS
from .regional import RegionalBuilder, hours_for_frame, region_hours
from .regrid import regrid
from .sources.openmeteo import OpenMeteoRun, RunIncomplete, resolve_daily_run
from .static_assets import ice_mask
from .sprites import CHUNKS, COLS, EVERY, FRAMES, HOURS, chunk_frames, pack_chunk, save_sprite
from .storms import frame_s, storm_index
from .waves import frame_time, wave_frame, wave_peak

WAVE_VARS = ("wave_height", "wave_period", "wave_direction")
GFS_VARS = ("wind_u_component_10m", "wind_v_component_10m", "temperature_2m")
CLOUD_VARS = ("cloud_cover_low", "cloud_cover_mid", "cloud_cover_high")
G25_VARS = ("cape", "lifted_index", "pressure_msl")
IFS_LAG = timedelta(hours=6)
IFS_GAP = timedelta(hours=6)  # long IFS runs step 6-hourly after their hour 144
FAR = timedelta(days=60)      # an eviction cutoff past every input of a run
PA_PER_HPA = 100.0  # IFS pressure is stored in Pa, GFS in hPa


@dataclass
class RunSources:
    """One model run per input, already aligned to the globe run (spec §4)."""
    wave: Any
    gfs: Any
    g25: Any
    ifs: Any
    cur: Any
    sst: Any


def open_sources(run: datetime, cache_dir: Path) -> RunSources:
    def om(model, model_run):
        return OpenMeteoRun(model, model_run, cache_dir, cache_run=run)
    cur_run = resolve_daily_run("meteofrance_currents", run, cache_dir)
    sst_run = resolve_daily_run("meteofrance_sea_surface_temperature", run, cache_dir)
    return RunSources(wave=om("ncep_gfswave025", run), gfs=om("ncep_gfs013", run), g25=om("ncep_gfs025", run),
                      ifs=om("ecmwf_ifs", run - IFS_LAG), cur=om("meteofrance_currents", cur_run),
                      sst=om("meteofrance_sea_surface_temperature", sst_run))


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%MZ")


def _check_complete(s: RunSources, run: datetime) -> None:
    """Refuse to start unless every required input is published (nothing is written otherwise)."""
    missing: list[str] = []
    frame_times = [frame_time(run, j) for j in range(FRAMES)]
    ocean_times = [ocean_time(run, k) for k in range(CURRENT_FRAMES)]
    needs = [
        ("wave", s.wave, WAVE_VARS, frame_times),
        ("gfs", s.gfs, GFS_VARS + CLOUD_VARS + ("precipitation",), frame_times),
        ("gfs", s.gfs, ("wind_u_component_10m", "wind_v_component_10m") + CLOUD_VARS, region_hours(run)),
        ("gfs", s.gfs, ("precipitation",), region_hours(run)[1:]),
        ("gfs025", s.g25, G25_VARS, frame_times),
        ("ifs", s.ifs, ("wind_gusts_10m", "pressure_msl"),
         [t for t in frame_times if t - run <= timedelta(hours=GUST_HOURS)]),
        ("currents", s.cur, ("ocean_u_current", "ocean_v_current"), ocean_times),
        ("sst", s.sst, ("sea_surface_temperature",), ocean_times),
    ]
    for name, src, variables, times in needs:
        meta = src.meta()
        if not meta.get("completed"):
            missing.append(f"{name} run {_iso(src.run)} still being published")
            continue
        have_t, have_v = set(meta.get("valid_times", [])), set(meta.get("variables", []))
        missing += [f"{name} {v}" for v in variables if v not in have_v]
        missing += [f"{name} {_iso(t)}" for t in times if _iso(t) not in have_t]
    if missing:
        raise RunIncomplete(f"run {_iso(run)} is missing: {', '.join(missing[:5])}"
                            + (f" and {len(missing) - 5} more" if len(missing) > 5 else ""))


class _GfsPrecip:
    """Precipitation steps of the GFS run on the globe grid, for rain_rate()."""

    def __init__(self, gfs):
        self.gfs = gfs
        self._times = sorted(datetime.strptime(v, "%Y-%m-%dT%H:%MZ").replace(tzinfo=gfs.run.tzinfo)
                             for v in gfs.meta()["valid_times"])

    def valid_times(self) -> list[datetime]:
        return self._times

    def field(self, t: datetime):
        a = self.gfs.field_or_none("precipitation", t)
        return None if a is None else regrid(a, self.gfs.source_grid, GLOBE)


def _on_globe(src, variable: str, t: datetime) -> np.ndarray:
    return regrid(src.field(variable, t), src.source_grid, GLOBE)


def _pressure(s: RunSources, t: datetime) -> np.ndarray:
    """IFS at t; between two IFS steps up to 6 h apart, their linear mean in time (spec §9);
    past the IFS run's end, GFS 0.25° of run T (spec §4). hPa."""
    if s.ifs.has_time(t):
        return _on_globe(s.ifs, "pressure_msl", t) / PA_PER_HPA
    times = s.ifs.valid_times()
    before = max((u for u in times if u < t), default=None)
    after = min((u for u in times if u > t), default=None)
    if before is not None and after is not None and after - before <= IFS_GAP:
        w = (t - before) / (after - before)
        a, b = (_on_globe(s.ifs, "pressure_msl", u) for u in (before, after))
        return (a * (1 - w) + b * w) / PA_PER_HPA
    return _on_globe(s.g25, "pressure_msl", t)


def _evict(s: RunSources, t_next: datetime | None, run: datetime) -> None:
    """Drop downloaded inputs no frame from t_next on can read (regional hours back 2 h, IFS
    interpolation up to 6 h); with no next frame, everything atmospheric."""
    if t_next is None:
        for src in (s.wave, s.gfs, s.g25, s.ifs):
            src.evict_before(run + FAR)
        return
    s.wave.evict_before(t_next)
    s.g25.evict_before(t_next)
    s.gfs.evict_before(t_next - timedelta(hours=2))  # regional hours in (t_next - 3 h, t_next] read from t_next - 2 h
    s.ifs.evict_before(t_next - IFS_GAP)


def _atmosphere(s: RunSources, precip: _GfsPrecip, run: datetime, t: datetime) -> dict:
    u, v, temp = (_on_globe(s.gfs, name, t) for name in GFS_VARS)
    layers = [s.gfs.field_or_none(name, t) for name in CLOUD_VARS]
    cloud = None if any(a is None for a in layers) else cloud_from_layers(
        *(regrid(a, s.gfs.source_grid, GLOBE) for a in layers))
    pressure = _pressure(s, t)
    gust = _on_globe(s.ifs, "wind_gusts_10m", t) if t - run <= timedelta(hours=GUST_HOURS) else None
    return {"u": u, "v": v, "temp": temp, "cloud": cloud, "pressure": pressure, "gust": gust,
            "rain": rain_rate(precip, t)}


def build_run(run: datetime, cache_dir: Path, out_dir: Path, sources: RunSources | None = None,
              ice: np.ndarray | None = None, prune: bool = False) -> Path:
    """Write out_dir/<YYYYMMDDHH>/ with globe-{a,b,t,s,w}0..6.webp, globe-c.webp and globe.json.
    Nothing is written unless the whole run is available; the folder appears only when complete.
    prune: delete each downloaded input once no later frame needs it (spec §5; CI disk)."""
    s = sources or open_sources(run, cache_dir)
    _check_complete(s, run)
    if ice is None:  # Natural Earth glaciated areas, cached next to the model inputs
        ice = ice_mask(Path(cache_dir) / "naturalearth")
    final = Path(out_dir) / run.strftime("%Y%m%d%H")
    tmp = final.with_name(final.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        peaks: dict[str, list] = {k: [] for k in ("wind", "rain", "hot", "cold", "gust", "low", "wave")}
        precip = _GfsPrecip(s.gfs)
        regional = RegionalBuilder(s.gfs, run)
        for chunk in range(len(CHUNKS)):
            sheets: dict[str, list] = {f: [] for f in "abtsw"}
            for j in chunk_frames(chunk):
                t = frame_time(run, j)
                for th in hours_for_frame(run, t):
                    regional.add_hour(th)
                height, period, direction = (s.wave.field(v, t) for v in WAVE_VARS)
                sheets["w"].append(wave_frame(height, period, direction, s.wave.source_grid))
                peaks["wave"].append(wave_peak(height, s.wave.source_grid))
                del height, period, direction
                f = _atmosphere(s, precip, run, t)
                sheets["a"].append(frame_a(f))
                sheets["b"].append(frame_b(f))
                sheets["t"].append(frame_t(f))
                cape, lifted = (_on_globe(s.g25, name, t) for name in ("cape", "lifted_index"))
                rain = f["rain"] if f["rain"] is not None else np.zeros((GLOBE.h, GLOBE.w), np.float32)
                sheets["s"].append(frame_s(storm_index(cape, rain, lifted)))
                peaks["wind"].append(peak(np.hypot(f["u"], f["v"])))
                peaks["rain"].append(peak(rain))
                peaks["hot"].append(peak(f["temp"]))
                peaks["cold"].append(peak(f["temp"], mode="min", exclude=ice))
                peaks["low"].append(peak(f["pressure"], mode="min"))
                if f["gust"] is not None:
                    peaks["gust"].append(peak(f["gust"]))
                if prune:
                    _evict(s, frame_time(run, j + 1) if j + 1 < FRAMES else None, run)
            for fam, frames in sheets.items():
                save_sprite(pack_chunk(frames), tmp / f"globe-{fam}{chunk}.webp")

        ocean, sea_hot, current = [], [], []
        for k in range(CURRENT_FRAMES):
            t = ocean_time(run, k)
            u, v = (s.cur.field(name, t) for name in ("ocean_u_current", "ocean_v_current"))
            sst = s.sst.field("sea_surface_temperature", t)
            ocean.append(ocean_frame(u, v, sst, s.cur.source_grid))
            gu, gv = (regrid(a, s.cur.source_grid, GLOBE) for a in (u, v))
            # Ocean peaks only count open sea: cells whose source neighbours are all sea.
            coastal = regrid(np.isfinite(sst).astype(np.float32), s.sst.source_grid, GLOBE) <= 0.999
            current.append(peak(np.hypot(gu, gv), exclude=coastal))
            sea_hot.append(peak(regrid(sst, s.sst.source_grid, GLOBE), exclude=coastal))
            if prune:
                cut = ocean_time(run, k + 1) if k + 1 < CURRENT_FRAMES else run + FAR
                s.cur.evict_before(cut)
                s.sst.evict_before(cut)
        save_sprite(pack_ocean(ocean), tmp / "globe-c.webp")
        regional.write(tmp, _iso(run))

        manifest = {
            "run": _iso(run), **GLOBE.manifest_fields(),
            "every": EVERY, "hours": HOURS, "frames": FRAMES, "cols": COLS, "chunks": CHUNKS,
            "pressure": True, "gust": True, "waves": True, "gustHours": GUST_HOURS,
            "currents": True, "currentEvery": CURRENT_EVERY, "storms": True, "currentFrames": CURRENT_FRAMES,
            "sources": {"ecmwf": _iso(s.ifs.run), "wave": _iso(s.wave.run),
                        "cur": _iso(s.cur.run), "sst": _iso(s.sst.run)},
            "peaks": {
                **{k: hourly(peaks[k], EVERY, HOURS) for k in ("wind", "rain", "hot", "cold")},
                "gust": hourly(peaks["gust"], EVERY, GUST_HOURS),
                "low": hourly(peaks["low"], EVERY, HOURS),
                "wave": hourly(peaks["wave"], EVERY, HOURS),
                "sea_hot": hourly(sea_hot, CURRENT_EVERY, HOURS),
                "current": hourly(current, CURRENT_EVERY, HOURS),
            },
        }
        (tmp / "globe.json").write_text(json.dumps(manifest, separators=(",", ":")))
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    _swap_in(tmp, final)
    return final


def write_latest(out_dir: Path, run: datetime, built: datetime) -> None:
    """Point the site at a run. Written last, after the run folder is complete."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "latest.json"
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps({"run": _iso(run), "dir": run.strftime("%Y%m%d%H"),
                                "regions": [r.slug for r in REGIONS],
                                "built": built.strftime("%Y-%m-%dT%H:%M:%SZ")}, separators=(",", ":")))
    part.replace(path)


def _swap_in(tmp: Path, final: Path) -> None:
    """Replace `final` with `tmp`. The old run is moved aside, not deleted, until
    the new one is in place; if the move fails the old run is put back."""
    old = final.with_name(final.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    had_old = final.exists()
    if had_old:
        final.rename(old)
    try:
        tmp.rename(final)
    except BaseException:
        if had_old:
            old.rename(final)
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(old, ignore_errors=True)
