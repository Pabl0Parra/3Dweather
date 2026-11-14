"""Builds one run folder: wave sprites plus globe.json."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from .grid import GLOBE
from .sources.openmeteo import OpenMeteoRun, RunIncomplete
from .sprites import CHUNKS, COLS, EVERY, FRAMES, HOURS, chunk_frames, pack_chunk, save_sprite
from .waves import frame_time, wave_frame, wave_peak

WAVE_MODEL = "ncep_gfswave025"
WAVE_VARIABLES = ("wave_height", "wave_period", "wave_direction")


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%MZ")


def _check_complete(source, run: datetime) -> None:
    """Refuse to start unless every frame's inputs are published."""
    meta = source.meta()
    if not meta.get("completed"):
        raise RunIncomplete(f"{WAVE_MODEL} run {_iso(run)} is still being published")
    have_times, have_vars = set(meta.get("valid_times", [])), set(meta.get("variables", []))
    missing = [v for v in WAVE_VARIABLES if v not in have_vars]
    missing += [_iso(frame_time(run, j)) for j in range(FRAMES) if _iso(frame_time(run, j)) not in have_times]
    if missing:
        raise RunIncomplete(f"{WAVE_MODEL} run {_iso(run)} is missing: {', '.join(missing[:5])}"
                            + (f" and {len(missing) - 5} more" if len(missing) > 5 else ""))


def build_waves(run: datetime, cache_dir: Path, out_dir: Path, source=None) -> Path:
    """Write out_dir/<YYYYMMDDHH>/ with globe-w0..6.webp and globe.json.
    Nothing is written unless the whole run is available; the folder appears only when complete."""
    source = source or OpenMeteoRun(WAVE_MODEL, run, cache_dir)
    _check_complete(source, run)
    sg = source.source_grid
    final = Path(out_dir) / run.strftime("%Y%m%d%H")
    tmp = final.with_name(final.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        frame_peaks = []
        for chunk in range(len(CHUNKS)):
            frames = []
            for j in chunk_frames(chunk):
                t = frame_time(run, j)
                height, period, direction = (source.field(v, t) for v in WAVE_VARIABLES)
                frames.append(wave_frame(height, period, direction, sg))
                frame_peaks.append(wave_peak(height, sg))
            save_sprite(pack_chunk(frames), tmp / f"globe-w{chunk}.webp")
        manifest = {
            "run": _iso(run), **GLOBE.manifest_fields(),
            "every": EVERY, "hours": HOURS, "frames": FRAMES, "cols": COLS, "chunks": CHUNKS,
            "waves": True,
            "sources": {"wave": _iso(run)},
            "peaks": {"wave": [frame_peaks[h // EVERY] for h in range(HOURS + 1)]},
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
