import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from PIL import Image

from pipeline.__main__ import main
from pipeline.build import build_waves
from pipeline.sources.openmeteo import MODELS, RunIncomplete
from pipeline.waves import wave_peak

RUN = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)
SG = MODELS["ncep_gfswave025"]


class FakeSource:
    """Constant grids; height grows 0.1 m per frame so frames are distinguishable."""
    source_grid = SG

    def __init__(self, n_times=57):
        self.times = [RUN + timedelta(hours=3 * j) for j in range(n_times)]

    def meta(self):
        return {"completed": True, "variables": ["wave_height", "wave_period", "wave_direction"],
                "valid_times": [t.strftime("%Y-%m-%dT%H:%MZ") for t in self.times]}

    def height(self, valid_time):
        j = self.times.index(valid_time)
        return np.full((721, 1440), 2.0 + 0.1 * j, np.float32)

    def field(self, variable, valid_time):
        if variable == "wave_height":
            return self.height(valid_time)
        return np.full((721, 1440), 10.0 if variable == "wave_period" else 270.0, np.float32)


def test_build_writes_seven_sprites_and_manifest(tmp_path):
    src = FakeSource()
    out = build_waves(RUN, tmp_path / "cache", tmp_path / "out", source=src)
    assert out == tmp_path / "out" / "2026111306"
    sizes = [Image.open(out / f"globe-w{i}.webp").size for i in range(7)]
    assert sizes == [(3072, 768)] * 6 + [(3072, 1152)]
    m = json.loads((out / "globe.json").read_text())
    assert m["frames"] == 57 and m["chunks"] == [8, 8, 8, 8, 8, 8, 9]
    assert m["w"] == 768 and m["north"] == 89.7364 and m["waves"] is True
    assert m["run"] == "2026-11-13T06:00Z" and m["sources"] == {"wave": "2026-11-13T06:00Z"}
    peaks = m["peaks"]["wave"]
    assert len(peaks) == 169
    assert peaks[0] == peaks[1] == peaks[2] and peaks[3] != peaks[2]
    assert peaks[168] == wave_peak(src.height(src.times[56]), SG)
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["2026111306"]


def test_incomplete_run_writes_nothing(tmp_path):
    with pytest.raises(RunIncomplete):
        build_waves(RUN, tmp_path / "cache", tmp_path / "out", source=FakeSource(n_times=56))
    assert not (tmp_path / "out").exists() or list((tmp_path / "out").iterdir()) == []


def test_rebuild_replaces_existing_run(tmp_path):
    build_waves(RUN, tmp_path / "cache", tmp_path / "out", source=FakeSource())
    out = build_waves(RUN, tmp_path / "cache", tmp_path / "out", source=FakeSource())
    assert (out / "globe.json").exists() and len(list((tmp_path / "out").iterdir())) == 1


def test_cli_exit_codes(tmp_path, monkeypatch, capsys):
    def boom(run, cache_dir, out_dir, source=None):
        raise RunIncomplete("ncep_gfswave025 run 2026-11-13T06:00Z is still being published")

    monkeypatch.setattr("pipeline.__main__.build_waves", boom)
    code = main(["build", "--run", "2026111306", "--cache", str(tmp_path), "--out", str(tmp_path)])
    assert code == 2 and "still being published" in capsys.readouterr().err


class FailingSource(FakeSource):
    def field(self, variable, valid_time):
        if self.times.index(valid_time) == 10:
            raise OSError("disk full")
        return super().field(variable, valid_time)


def test_failure_midway_leaves_no_output(tmp_path):
    with pytest.raises(OSError):
        build_waves(RUN, tmp_path / "cache", tmp_path / "out", source=FailingSource())
    assert list((tmp_path / "out").iterdir()) == []


def test_swap_failure_restores_the_existing_run(tmp_path, monkeypatch):
    """If the new folder cannot be moved into place, the old run must come back intact."""
    out = build_waves(RUN, tmp_path / "cache", tmp_path / "out", source=FakeSource())
    (out / "marker").write_text("old")
    import pipeline.build as b
    real = b.Path.rename

    def flaky(self, target):
        if self.name.endswith(".tmp"):
            raise PermissionError("locked")
        return real(self, target)

    monkeypatch.setattr(b.Path, "rename", flaky)
    with pytest.raises(PermissionError):
        build_waves(RUN, tmp_path / "cache", tmp_path / "out", source=FakeSource())
    assert (out / "marker").read_text() == "old" and (out / "globe-w0.webp").exists()
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["2026111306"]
