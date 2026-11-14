"""Reads one model run from Open-Meteo's public bucket, through a local cache.

Whole files are downloaded and read locally: reading single variables by
remote range request measured about 50 times slower.
"""
from __future__ import annotations

import gc
import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
import omfiles

from ..regrid import SourceGrid

BUCKET_URL = "https://openmeteo.s3.amazonaws.com/data_spatial"

MODELS: dict[str, SourceGrid] = {
    "ncep_gfswave025": SourceGrid(lat0=-90.0, lon0=-180.0, dlat=0.25, dlon=0.25),
}


class RunIncomplete(Exception):
    """The bucket does not (yet) hold everything this run needs."""


def http_fetch(url: str, dest: Path) -> None:
    """Download to `<dest>.part`, then rename, so a broken download leaves no file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        written = 0
        with urllib.request.urlopen(url, timeout=120) as response, open(part, "wb") as out:
            expected = response.headers.get("Content-Length")
            while chunk := response.read(1 << 20):
                out.write(chunk)
                written += len(chunk)
        if expected is not None and written != int(expected):
            # a connection closed early ends the read loop without an error
            raise OSError(f"short download: got {written} of {expected} bytes from {url}")
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    part.replace(dest)


def _stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H%M")


class OpenMeteoRun:
    def __init__(self, model: str, run: datetime, cache_dir: Path,
                 fetch: Callable[[str, Path], None] = http_fetch):
        self.model = model
        self.run = run
        # Keyed by run: two runs share valid times, so a per-model folder would
        # silently serve one run's files to another.
        self.dir = Path(cache_dir) / run.strftime("%Y%m%d%H") / model
        self.fetch = fetch
        self._meta: dict | None = None

    @property
    def source_grid(self) -> SourceGrid:
        return MODELS[self.model]

    def _url(self, name: str) -> str:
        return f"{BUCKET_URL}/{self.model}/{self.run:%Y/%m/%d/%H%M}Z/{name}"

    def meta(self) -> dict:
        """The run's meta.json. Kept on disk only once the run is complete, so a
        retry after an early attempt sees the bucket's current state."""
        if self._meta is not None:
            return self._meta
        path = self.dir / "meta.json"
        meta = None
        if path.exists():
            try:
                meta = json.loads(path.read_text())
            except ValueError:
                path.unlink()  # corrupt cache entry: fetch it again
        if meta is None:
            try:
                self.fetch(self._url("meta.json"), path)
            except urllib.error.HTTPError as exc:
                if exc.code in (403, 404):
                    raise RunIncomplete(
                        f"{self.model} run {self.run:%Y-%m-%dT%H:%MZ} is not in the bucket (yet)") from exc
                raise
            meta = json.loads(path.read_text())
        reference = meta.get("reference_time")
        if reference is not None and reference[:16] != self.run.strftime("%Y-%m-%dT%H:%M"):
            raise RuntimeError(f"{path} describes run {reference}, not {self.run:%Y-%m-%dT%H:%MZ}")
        if not meta.get("completed"):
            path.unlink(missing_ok=True)
            return meta
        self._meta = meta
        return meta

    def field(self, variable: str, valid_time: datetime) -> np.ndarray:
        """Native grid for one variable at one valid time, float32, NaN where missing."""
        stamp = _stamp(valid_time)
        packed = self.dir / variable / f"{stamp}.npz"
        if packed.exists():
            return _read_npz(packed)
        om = self.dir / f"{stamp}.om"
        if om.exists():
            try:
                return _read_om(om, variable)
            except Exception:
                om.unlink()  # unreadable cache entry: fetch it again, once
        self._require(variable, valid_time)
        self.fetch(self._url(om.name), om)
        return _read_om(om, variable)

    def _require(self, variable: str, valid_time: datetime) -> None:
        meta = self.meta()
        when = valid_time.strftime("%Y-%m-%dT%H:%MZ")
        if not meta.get("completed"):
            raise RunIncomplete(f"{self.model} run {self.run:%Y-%m-%dT%H:%MZ} is still being published")
        if when not in meta.get("valid_times", []) or variable not in meta.get("variables", []):
            raise RunIncomplete(
                f"{self.model} run {self.run:%Y-%m-%dT%H:%MZ} has no {variable} for {when}")


def _read_npz(path: Path) -> np.ndarray:
    with np.load(path) as z:
        data = z["data"]
        if str(z["kind"]) != "int16":
            return data.astype(np.float32)
        out = data.astype(np.float32) / np.float32(z["scale"])
        out[data == int(z["nan"])] = np.nan
        return out


def _read_om(path: Path, variable: str) -> np.ndarray:
    reader = omfiles.OmFileReader(str(path))
    child = None
    try:
        child = reader.get_child_by_name(variable)
        data = np.asarray(child[:], dtype=np.float32)
    finally:
        child = None
        reader.close()
        del reader
        gc.collect()  # Windows keeps the file locked while reader objects are alive
    return data
