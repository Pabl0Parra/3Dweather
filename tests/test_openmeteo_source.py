import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import omfiles
import pytest

from pipeline.sources import openmeteo
from pipeline.sources.openmeteo import OpenMeteoRun, RunIncomplete, http_fetch

MODEL = "ncep_gfswave025"
RUN = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)
T0 = RUN
T3 = datetime(2026, 11, 13, 9, tzinfo=timezone.utc)


def write_meta(cache: Path, completed=True, times=("2026-11-13T06:00Z",), variables=("wave_height",)):
    d = cache / MODEL
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(
        {"completed": completed, "valid_times": list(times), "variables": list(variables)}))


def write_om(path: Path, name: str, data: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    w = omfiles.OmFileWriter.at_path(str(path))
    var = w.write_array(data.astype(np.float32), chunks=[2, 2], scale_factor=10.0, name=name)
    w.close(w.write_group("", children=[var]))


class FakeFetch:
    def __init__(self, om_source: Path | None = None):
        self.calls: list[str] = []
        self.om_source = om_source

    def __call__(self, url: str, dest: Path) -> None:
        self.calls.append(url)
        assert self.om_source is not None, f"unexpected fetch of {url}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.om_source.read_bytes())


def test_reads_packed_npz(tmp_path):
    d = tmp_path / MODEL / "wave_height"
    d.mkdir(parents=True)
    np.savez_compressed(d / "2026-11-13T0600.npz", data=np.array([[10, 32767]], np.int16),
                        scale=np.float64(10.0), nan=np.int32(32767), kind="int16")
    out = OpenMeteoRun(MODEL, RUN, tmp_path, fetch=FakeFetch()).field("wave_height", T0)
    assert out.dtype == np.float32 and out[0, 0] == 1.0 and np.isnan(out[0, 1])


def test_missing_valid_time_raises_run_incomplete(tmp_path):
    write_meta(tmp_path)
    fetch = FakeFetch()
    with pytest.raises(RunIncomplete) as err:
        OpenMeteoRun(MODEL, RUN, tmp_path, fetch=fetch).field("wave_height", T3)
    assert MODEL in str(err.value) and "2026-11-13T09:00Z" in str(err.value)
    assert fetch.calls == []


def test_incomplete_run_raises(tmp_path):
    write_meta(tmp_path, completed=False)
    with pytest.raises(RunIncomplete):
        OpenMeteoRun(MODEL, RUN, tmp_path, fetch=FakeFetch()).field("wave_height", T0)


def test_downloads_once_then_uses_cache(tmp_path):
    write_meta(tmp_path / "cache")
    write_om(tmp_path / "remote.om", "wave_height", np.array([[1.5, 2.5], [3.5, 4.5]]))
    fetch = FakeFetch(tmp_path / "remote.om")
    run = OpenMeteoRun(MODEL, RUN, tmp_path / "cache", fetch=fetch)
    a = run.field("wave_height", T0)
    b = run.field("wave_height", T0)
    assert np.allclose(a, [[1.5, 2.5], [3.5, 4.5]]) and np.array_equal(a, b)
    assert fetch.calls == [
        "https://openmeteo.s3.amazonaws.com/data_spatial/ncep_gfswave025/2026/11/13/0600Z/2026-11-13T0600.om"]


def test_meta_is_downloaded_when_absent(tmp_path):
    remote = tmp_path / "meta-remote.json"
    remote.write_text(json.dumps({"completed": True, "valid_times": [], "variables": []}))
    fetch = FakeFetch(remote)
    assert OpenMeteoRun(MODEL, RUN, tmp_path / "cache", fetch=fetch).meta()["completed"] is True
    assert fetch.calls == [
        "https://openmeteo.s3.amazonaws.com/data_spatial/ncep_gfswave025/2026/11/13/0600Z/meta.json"]


def test_http_fetch_leaves_no_file_on_failure(tmp_path, monkeypatch):
    class Broken:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n):
            if not hasattr(self, "sent"):
                self.sent = True
                return b"partial"
            raise OSError("connection reset")

    monkeypatch.setattr(openmeteo.urllib.request, "urlopen", lambda url, timeout: Broken())
    dest = tmp_path / "x" / "file.om"
    with pytest.raises(OSError):
        http_fetch("https://example.invalid/file.om", dest)
    assert not dest.exists()
