"""Save the Open-Meteo inputs behind reference run 2026111306 before the bucket prunes them.

The public bucket keeps whole-grid files for about 7 days. This copies what the
reference-run test needs into reference/openmeteo-inputs/2026111306/.

Small models are copied as original .om files. Large models are downloaded one
file at a time, the needed variables extracted, and stored as .npz: int16 values plus the scale factor
Open-Meteo itself uses, so nothing is lost. value = data / scale, NaN = 32767.

Safe to re-run: files already saved are skipped.
Usage: python save_reference_inputs.py [output_dir]
"""
from __future__ import annotations

import gc
import json
import shutil
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import omfiles
import s3fs

BUCKET = "openmeteo"
HTTP = "https://openmeteo.s3.amazonaws.com"
RUN = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)
NAN16 = 32767

# Globe frames: every 3 h for 168 h.
FRAME_TIMES = [RUN + timedelta(hours=h) for h in range(0, 169, 3)]
# Rain may be an average over the frame step, so keep every hour GFS has.
HOURLY_TIMES = [RUN + timedelta(hours=h) for h in range(0, 169)]

# model -> (run directory, {variable: times}) for remote subsetting
SUBSET = {
    "ncep_gfs013": ("2026/11/13/0600Z", {
        "wind_u_component_10m": FRAME_TIMES,
        "wind_v_component_10m": FRAME_TIMES,
        "cloud_cover": FRAME_TIMES,
        "temperature_2m": FRAME_TIMES,
        "precipitation": HOURLY_TIMES,
        "showers": HOURLY_TIMES,
    }),
    "ncep_gfs025": ("2026/11/13/0600Z", {
        "cape": FRAME_TIMES,
        "lifted_index": FRAME_TIMES,
        "convective_inhibition": FRAME_TIMES,
        "pressure_msl": FRAME_TIMES,
        "wind_gusts_10m": FRAME_TIMES,
    }),
    "ecmwf_ifs": ("2026/11/13/0000Z", {
        "pressure_msl": FRAME_TIMES,
        "wind_gusts_10m": FRAME_TIMES,
        "cape": FRAME_TIMES,
        "precipitation": FRAME_TIMES,
    }),
}

# model -> (run directory, times or None for every file) copied whole
WHOLE = {
    "ncep_gfswave025": ("2026/11/13/0600Z", FRAME_TIMES),
    "meteofrance_currents": ("2026/11/12/0000Z", None),
    "meteofrance_sea_surface_temperature": ("2026/11/12/0000Z", None),
}


def stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H%M")


def fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)


def meta(model: str, run_dir: str, out: Path) -> dict:
    dest = out / model / "meta.json"
    if not dest.exists():
        fetch(f"{HTTP}/data_spatial/{model}/{run_dir}/meta.json", dest)
    return json.loads(dest.read_text())


def pack(values: np.ndarray, scale: float) -> tuple[np.ndarray, str]:
    """Quantise as Open-Meteo does; fall back to float32 if that would clip."""
    scaled = np.rint(values.astype(np.float64) * scale)
    ok = np.isfinite(scaled)
    if scale > 0 and (np.abs(scaled[ok]) < NAN16).all():
        data = np.where(ok, scaled, NAN16).astype(np.int16)
        return data, "int16"
    return values.astype(np.float32), "float32"


def save_subset(fs, model: str, run_dir: str, t: datetime, names: list[str], out: Path) -> str:
    todo = [n for n in names if not (out / model / n / f"{stamp(t)}.npz").exists()]
    if not todo:
        return f"skip {model} {stamp(t)}"
    # Whole-file download then local read: remote range reads proved ~50x slower.
    local = out / "_tmp" / f"{model}-{stamp(t)}.om"
    fetch(f"{HTTP}/data_spatial/{model}/{run_dir}/{stamp(t)}.om", local)
    reader = omfiles.OmFileReader(str(local))
    try:
        for name in todo:
            var = reader.get_child_by_name(name)
            scale = float(var.scale_factor)
            data, kind = pack(var[:], scale)
            dest = out / model / name / f"{stamp(t)}.npz"
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".part.npz")
            np.savez_compressed(tmp, data=data, scale=np.float64(scale if kind == "int16" else 1.0),
                                nan=np.int32(NAN16 if kind == "int16" else 0), kind=kind)
            tmp.replace(dest)
    finally:
        var = None
        reader.close()
        del reader
        gc.collect()
        try:  # Windows keeps the file locked while any reader object is alive
            local.unlink(missing_ok=True)
        except PermissionError:
            pass  # removed with the rest of _tmp at the end of the run
    return f"ok   {model} {stamp(t)} {','.join(todo)}"


def save_whole(model: str, run_dir: str, name: str, out: Path) -> str:
    dest = out / model / name
    if dest.exists():
        return f"skip {model} {name}"
    fetch(f"{HTTP}/data_spatial/{model}/{run_dir}/{name}", dest)
    return f"ok   {model} {name}"


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path(__file__).resolve().parent.parent / "reference" / "openmeteo-inputs" / "2026111306")
    fs = s3fs.S3FileSystem(anon=True)
    jobs = []
    missing: list[str] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for model, (run_dir, wanted) in SUBSET.items():
            m = meta(model, run_dir, out)
            have_t = set(m["valid_times"])
            have_v = set(m["variables"])
            by_time: dict[datetime, list[str]] = {}
            for name, times in wanted.items():
                if name not in have_v:
                    missing.append(f"{model}: variable {name} not in run")
                    continue
                for t in times:
                    if t.strftime("%Y-%m-%dT%H:%MZ") in have_t:
                        by_time.setdefault(t, []).append(name)
                    elif t in FRAME_TIMES:
                        missing.append(f"{model}: no file for {stamp(t)} ({name})")
            for t, names in sorted(by_time.items()):
                jobs.append(pool.submit(save_subset, fs, model, run_dir, t, names, out))
        for model, (run_dir, times) in WHOLE.items():
            m = meta(model, run_dir, out)
            valid = [datetime.strptime(v, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
                     for v in m["valid_times"]]
            for t in valid:
                if times is None or t in times:
                    jobs.append(pool.submit(save_whole, model, run_dir, f"{stamp(t)}.om", out))
            if times is not None:
                missing += [f"{model}: no file for {stamp(t)}" for t in times if t not in valid]
        failed = 0
        for i, job in enumerate(as_completed(jobs), 1):
            try:
                print(f"[{i}/{len(jobs)}] {job.result()}", flush=True)
            except Exception as exc:  # keep going; a re-run picks up what failed
                failed += 1
                print(f"[{i}/{len(jobs)}] FAILED {exc!r}", flush=True)
    gc.collect()
    shutil.rmtree(out / "_tmp", ignore_errors=True)
    (out / "missing.txt").write_text("\n".join(sorted(set(missing))) + "\n")
    print(f"done: {len(jobs)} jobs, {failed} failed, {len(set(missing))} missing (see missing.txt)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
