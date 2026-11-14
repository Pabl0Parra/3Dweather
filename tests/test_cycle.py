from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipeline.__main__ import main
from pipeline.cycle import cycle, due_run
from pipeline.publish import DirStore, published_run
from pipeline.sources.openmeteo import RunIncomplete

UTC = timezone.utc


def at(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


@pytest.mark.parametrize("now, run", [
    ("2026-11-14 05:14", "2026-11-13 18:00"),
    ("2026-11-14 05:15", "2026-11-14 00:00"),
    ("2026-11-14 11:15", "2026-11-14 06:00"),
    ("2026-11-14 23:59", "2026-11-14 18:00"),
    ("2026-11-15 00:30", "2026-11-14 18:00"),
])
def test_due_run(now, run):
    assert due_run(at(now)) == at(run)


class FakeBuild:
    """Writes a minimal run folder; raises RunIncomplete for the first `fail` calls."""
    def __init__(self, fail=0):
        self.fail, self.calls = fail, []

    def __call__(self, run, cache_dir, out_dir, **kw):
        self.calls.append((run, kw))
        if len(self.calls) <= self.fail:
            raise RunIncomplete("ecmwf_ifs run still being published")
        d = Path(out_dir) / run.strftime("%Y%m%d%H")
        d.mkdir(parents=True, exist_ok=True)
        (d / "globe.json").write_text("{}")
        (d / "globe-w0.webp").write_bytes(b"x")
        return d


NOW = at("2026-11-14 11:20")  # 06Z is due


def test_publishes_the_due_run_with_pruned_inputs(tmp_path):
    store, build = DirStore(tmp_path / "bucket"), FakeBuild()
    assert cycle(NOW, tmp_path / "cache", tmp_path / "out", store, build=build, sleep=lambda s: None) == 0
    assert published_run(store) == at("2026-11-14 06:00")
    assert build.calls[0][1] == {"prune": True}


def test_already_current_does_nothing(tmp_path):
    store, build = DirStore(tmp_path / "bucket"), FakeBuild()
    cycle(NOW, tmp_path / "cache", tmp_path / "out", store, build=build, sleep=lambda s: None)
    assert cycle(NOW + timedelta(hours=1), tmp_path / "cache", tmp_path / "out", store, build=build,
                 sleep=lambda s: None) == 0
    assert len(build.calls) == 1


def test_waits_for_late_inputs(tmp_path):
    store, build, slept = DirStore(tmp_path / "bucket"), FakeBuild(fail=2), []
    assert cycle(NOW, tmp_path / "cache", tmp_path / "out", store, build=build, sleep=slept.append) == 0
    assert len(build.calls) == 3 and slept == [600, 600]
    assert published_run(store) == at("2026-11-14 06:00")


def test_gives_up_after_the_wait_and_leaves_latest(tmp_path):
    store = DirStore(tmp_path / "bucket")
    store.put_bytes("wx/latest.json", b'{"dir":"2026111400"}', "application/json", "x")
    build, slept = FakeBuild(fail=99), []
    assert cycle(NOW, tmp_path / "cache", tmp_path / "out", store, build=build, sleep=slept.append) == 2
    assert sum(slept) == 90 * 60 and len(build.calls) == 10
    assert published_run(store) == at("2026-11-14 00:00")


def test_explicit_run_overrides_the_clock(tmp_path):
    store, build = DirStore(tmp_path / "bucket"), FakeBuild()
    cycle(NOW, tmp_path / "cache", tmp_path / "out", store, build=build, sleep=lambda s: None,
          run=at("2026-11-13 18:00"))
    assert published_run(store) == at("2026-11-13 18:00")


def test_old_runs_are_pruned_after_publishing(tmp_path):
    store = DirStore(tmp_path / "bucket")
    for old in ("2026111018", "2026111106", "2026111112"):
        store.put_bytes(f"wx/{old}/globe.json", b"{}", "application/json", "x")
    cycle(NOW, tmp_path / "cache", tmp_path / "out", store, build=FakeBuild(), sleep=lambda s: None)
    runs = sorted({k.split("/")[1] for k in store.list_keys("wx/") if k.count("/") == 2})
    assert runs == ["2026111106", "2026111112", "2026111406"]  # older than 3 days before 06Z on the 14th goes


def test_cli_cycle_with_a_directory_store(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.cycle.build_run", FakeBuild())
    code = main(["cycle", "--run", "2026111306", "--cache", str(tmp_path / "c"), "--out", str(tmp_path / "o"),
                 "--store", f"dir:{tmp_path / 'bucket'}"])
    assert code == 0 and published_run(DirStore(tmp_path / "bucket")) == at("2026-11-13 06:00")


def test_cli_upload(tmp_path):
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "coast.json").write_text("{}")
    main(["upload", "--src", str(tmp_path / "s"), "--prefix", "assets/globe", "--max-age", "604800",
          "--store", f"dir:{tmp_path / 'bucket'}"])
    assert DirStore(tmp_path / "bucket").headers("assets/globe/coast.json")["cache_control"] == "public, max-age=604800"
