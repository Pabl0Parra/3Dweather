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


def meta_json(completed=True, times=("2026-11-13T06:00Z",), variables=("wave_height",),
              reference_time="2026-11-13T06:00:00Z") -> str:
    return json.dumps({"completed": completed, "reference_time": reference_time,
                       "valid_times": list(times), "variables": list(variables)})


def run_dir(cache: Path) -> Path:
    return cache / "2026111306" / MODEL


def write_meta(cache: Path, **kw):
    run_dir(cache).mkdir(parents=True, exist_ok=True)
    (run_dir(cache) / "meta.json").write_text(meta_json(**kw))


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
    d = run_dir(tmp_path) / "wave_height"
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
    remote.write_text(meta_json(times=(), variables=()))
    fetch = FakeFetch(remote)
    assert OpenMeteoRun(MODEL, RUN, tmp_path / "cache", fetch=fetch).meta()["completed"] is True
    assert fetch.calls == [
        "https://openmeteo.s3.amazonaws.com/data_spatial/ncep_gfswave025/2026/11/13/0600Z/meta.json"]


def test_http_fetch_leaves_no_file_on_failure(tmp_path, monkeypatch):
    class Broken:
        headers = {}
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


class Scripted:
    """fetch that serves a queue of payloads (or exceptions) per file name; records URLs."""
    def __init__(self, files: dict):
        self.files = {k: list(v) for k, v in files.items()}
        self.calls: list[str] = []

    def __call__(self, url: str, dest: Path) -> None:
        self.calls.append(url)
        item = self.files[url.rsplit("/", 1)[1]].pop(0)
        if isinstance(item, Exception):
            raise item
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(item if isinstance(item, bytes) else item.encode())


def test_cache_is_keyed_by_run(tmp_path):
    """A second run sharing the cache must fetch its own files, never reuse the first run's."""
    write_om(tmp_path / "a.om", "wave_height", np.full((2, 2), 1.0))
    write_om(tmp_path / "b.om", "wave_height", np.full((2, 2), 2.0))
    later = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
    times = ("2026-11-13T12:00Z",)
    fetch = Scripted({
        "meta.json": [meta_json(times=times), meta_json(times=times, reference_time="2026-11-13T12:00:00Z")],
        "2026-11-13T1200.om": [(tmp_path / "a.om").read_bytes(), (tmp_path / "b.om").read_bytes()]})
    first = OpenMeteoRun(MODEL, RUN, tmp_path / "cache", fetch=fetch).field("wave_height", later)
    second = OpenMeteoRun(MODEL, later, tmp_path / "cache", fetch=fetch).field("wave_height", later)
    assert first[0, 0] == 1.0 and second[0, 0] == 2.0
    assert sum("/1200Z/" in u for u in fetch.calls) == 2


def test_meta_for_another_run_is_rejected(tmp_path):
    write_meta(tmp_path, reference_time="2026-11-13T00:00:00Z")
    with pytest.raises(RuntimeError, match="2026-11-13T00:00:00Z"):
        OpenMeteoRun(MODEL, RUN, tmp_path, fetch=FakeFetch()).meta()


def test_incomplete_meta_is_not_cached(tmp_path):
    fetch = Scripted({"meta.json": [meta_json(completed=False), meta_json()]})
    with pytest.raises(RunIncomplete):
        OpenMeteoRun(MODEL, RUN, tmp_path, fetch=fetch).field("wave_height", T0)
    assert OpenMeteoRun(MODEL, RUN, tmp_path, fetch=fetch).meta()["completed"] is True
    assert len(fetch.calls) == 2


def test_run_not_in_bucket_yet_is_run_incomplete(tmp_path):
    import urllib.error
    gone = urllib.error.HTTPError("u", 404, "Not Found", None, None)
    with pytest.raises(RunIncomplete, match="not in the bucket"):
        OpenMeteoRun(MODEL, RUN, tmp_path, fetch=Scripted({"meta.json": [gone]})).meta()


def test_corrupt_cached_meta_is_refetched(tmp_path):
    run_dir(tmp_path).mkdir(parents=True)
    (run_dir(tmp_path) / "meta.json").write_text('{"completed": tr')
    fetch = Scripted({"meta.json": [meta_json()]})
    assert OpenMeteoRun(MODEL, RUN, tmp_path, fetch=fetch).meta()["completed"] is True


def test_corrupt_cached_om_is_refetched(tmp_path):
    write_meta(tmp_path)
    write_om(tmp_path / "good.om", "wave_height", np.full((2, 2), 3.0))
    (run_dir(tmp_path) / "2026-11-13T0600.om").write_bytes(b"not an om file")
    fetch = Scripted({"2026-11-13T0600.om": [(tmp_path / "good.om").read_bytes()]})
    out = OpenMeteoRun(MODEL, RUN, tmp_path, fetch=fetch).field("wave_height", T0)
    assert out[0, 0] == 3.0 and len(fetch.calls) == 1


def test_short_download_is_rejected(tmp_path, monkeypatch):
    class Short:
        headers = {"Content-Length": "1000"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n):
            data, self.data = getattr(self, "data", b"x" * 100), b""
            return data

    monkeypatch.setattr(openmeteo.urllib.request, "urlopen", lambda url, timeout: Short())
    dest = tmp_path / "file.om"
    with pytest.raises(OSError, match="100 of 1000"):
        http_fetch("https://example.invalid/file.om", dest)
    assert not dest.exists() and not (tmp_path / "file.om.part").exists()


# --- phase 3a: more models, cache keyed by globe run, absent variables, daily runs ---
import urllib.error
from datetime import timedelta

from pipeline.sources.openmeteo import resolve_daily_run


def test_cache_folder_follows_cache_run(tmp_path):
    src = OpenMeteoRun("ecmwf_ifs", RUN - timedelta(hours=6), tmp_path, cache_run=RUN)
    assert src.dir == tmp_path / "2026111306" / "ecmwf_ifs"


def test_every_model_has_a_grid():
    for m in ("ncep_gfswave025", "ncep_gfs013", "ncep_gfs025", "ecmwf_ifs",
              "meteofrance_currents", "meteofrance_sea_surface_temperature"):
        assert m in openmeteo.MODELS


def test_absent_variable_from_cache_list_is_none(tmp_path):
    write_meta(tmp_path, variables=("wave_height", "cloud_cover"))
    (run_dir(tmp_path) / "absent.txt").write_text("2026-11-13T0600: cloud_cover, precipitation\n")
    src = OpenMeteoRun(MODEL, RUN, tmp_path, fetch=FakeFetch())
    assert src.field_or_none("cloud_cover", T0) is None


def test_absent_variable_in_om_file_is_none(tmp_path):
    write_meta(tmp_path, variables=("wave_height", "cloud_cover"))
    write_om(run_dir(tmp_path) / "2026-11-13T0600.om", "wave_height", np.ones((2, 2)))
    src = OpenMeteoRun(MODEL, RUN, tmp_path, fetch=FakeFetch())
    assert src.field_or_none("cloud_cover", T0) is None
    assert src.field_or_none("wave_height", T0)[0, 0] == 1.0


def test_has_time(tmp_path):
    write_meta(tmp_path)
    src = OpenMeteoRun(MODEL, RUN, tmp_path, fetch=FakeFetch())
    assert src.has_time(T0) and not src.has_time(T3)


class MetaFetch:
    """Serves meta.json for the listed run dates (YYYY/MM/DD), 404 otherwise."""
    def __init__(self, completed_days):
        self.days, self.calls = completed_days, []

    def __call__(self, url, dest):
        self.calls.append(url)
        for day in self.days:
            if f"/{day}/0000Z/meta.json" in url:
                dest.parent.mkdir(parents=True, exist_ok=True)
                ref = day.replace("/", "-") + "T00:00:00Z"
                dest.write_text(meta_json(reference_time=ref))
                return
        raise urllib.error.HTTPError(url, 404, "not found", None, None)


def test_daily_run_prefers_cached_meta(tmp_path):
    d = tmp_path / "2026111306" / "meteofrance_currents"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(meta_json(reference_time="2026-11-12T00:00:00Z"))
    fetch = MetaFetch([])
    got = resolve_daily_run("meteofrance_currents", RUN, tmp_path, fetch)
    assert got == datetime(2026, 11, 12, tzinfo=timezone.utc) and fetch.calls == []


def test_daily_run_walks_back_to_a_completed_run(tmp_path):
    fetch = MetaFetch(["2026/11/12"])
    got = resolve_daily_run("meteofrance_currents", RUN, tmp_path, fetch)
    assert got == datetime(2026, 11, 12, tzinfo=timezone.utc)
    assert any("2026/11/13/0000Z" in c for c in fetch.calls)


def test_daily_run_gives_up_after_four_days(tmp_path):
    with pytest.raises(RunIncomplete):
        resolve_daily_run("meteofrance_currents", RUN, tmp_path, MetaFetch([]))


# --- final review: download retries, cache eviction ---

@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr(openmeteo, "RETRY_DELAYS", (0, 0, 0))


class Body:
    def __init__(self, data=b"ok"):
        self.data, self.headers = data, {"Content-Length": str(len(data))}
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n):
        data, self.data = self.data, b""
        return data


def test_http_fetch_retries_transient_failures(tmp_path, monkeypatch):
    outcomes = [urllib.error.URLError("reset"), urllib.error.HTTPError("u", 503, "Slow Down", None, None), Body(b"done")]
    calls = []

    def urlopen(url, timeout):
        calls.append(url)
        item = outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(openmeteo.urllib.request, "urlopen", urlopen)
    http_fetch("https://example.invalid/f.om", tmp_path / "f.om")
    assert (tmp_path / "f.om").read_bytes() == b"done" and len(calls) == 3


def test_http_fetch_does_not_retry_missing_files(tmp_path, monkeypatch):
    calls = []

    def urlopen(url, timeout):
        calls.append(url)
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(openmeteo.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        http_fetch("https://example.invalid/f.om", tmp_path / "f.om")
    assert len(calls) == 1


def test_http_fetch_gives_up_after_the_last_attempt(tmp_path, monkeypatch):
    calls = []

    def urlopen(url, timeout):
        calls.append(url)
        raise TimeoutError("stalled")

    monkeypatch.setattr(openmeteo.urllib.request, "urlopen", urlopen)
    with pytest.raises(TimeoutError):
        http_fetch("https://example.invalid/f.om", tmp_path / "f.om")
    assert len(calls) == len(openmeteo.RETRY_DELAYS) + 1


def test_evict_before_deletes_only_older_downloaded_files(tmp_path):
    src = OpenMeteoRun(MODEL, RUN, tmp_path, fetch=FakeFetch())
    src.dir.mkdir(parents=True)
    for stamp in ("2026-11-13T0600", "2026-11-13T0900", "2026-11-13T1200"):
        (src.dir / f"{stamp}.om").write_bytes(b"x")
    (src.dir / "wave_height").mkdir()
    (src.dir / "wave_height" / "2026-11-13T0600.npz").write_bytes(b"x")  # saved inputs are kept
    (src.dir / "meta.json").write_text("{}")
    src.evict_before(datetime(2026, 11, 13, 12, tzinfo=timezone.utc))
    assert sorted(p.name for p in src.dir.glob("*.om")) == ["2026-11-13T1200.om"]
    assert (src.dir / "wave_height" / "2026-11-13T0600.npz").exists() and (src.dir / "meta.json").exists()
