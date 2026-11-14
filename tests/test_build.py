import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from PIL import Image

from pipeline.__main__ import main
from pipeline.build import RunSources, build_run
from pipeline.codecs import encode_pressure
from pipeline.regrid import SourceGrid
from pipeline.sources.openmeteo import RunIncomplete, VariableAbsent
from pipeline.sprites import unpack_frame
from pipeline.waves import wave_peak

RUN = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)
SG = SourceGrid(lat0=-90.0, lon0=-180.0, dlat=2.0, dlon=2.0)  # small grids keep the tests fast
SHAPE = (91, 180)
NO_ICE = np.zeros((384, 768), bool)
H = timedelta(hours=1)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%MZ")


class FakeModel:
    """Constant grids per variable; values may depend on the valid time."""
    source_grid = SG

    def __init__(self, run, variables, times, values=None, absent=()):
        self.run, self.variables, self.times = run, variables, list(times)
        self.values = values or {}
        self.absent = set(absent)  # (variable, time) pairs whose file lacks the variable
        self.evicted: list[datetime] = []

    def meta(self):
        return {"completed": True, "variables": list(self.variables), "valid_times": [iso(t) for t in self.times]}

    def has_time(self, t):
        return t in self.times

    def valid_times(self):
        return sorted(self.times)

    def evict_before(self, t):
        self.evicted.append(t)

    def field(self, variable, t):
        if t not in self.times or variable not in self.variables:
            raise RunIncomplete(f"no {variable} at {iso(t)}")
        if (variable, t) in self.absent:
            raise VariableAbsent(variable)
        v = self.values.get(variable, 1.0)
        return np.full(SHAPE, v(t) if callable(v) else v, np.float32)

    def field_or_none(self, variable, t):
        try:
            return self.field(variable, t)
        except VariableAbsent:
            return None


def frames(n=57):
    return [RUN + timedelta(hours=3 * j) for j in range(n)]


def fake_sources(wave_frames=57, gfs_frames=57, ifs_hours=168, ifs_times=None, ifs_vars=("pressure_msl", "wind_gusts_10m"),
                 ifs_pressure=101500.0):
    hourly = [RUN + h * H for h in range(0, 172)]
    wave = FakeModel(RUN, ["wave_height", "wave_period", "wave_direction"], frames(wave_frames),
                     {"wave_height": lambda t: 2.0 + 0.1 * ((t - RUN) / H) / 3, "wave_period": 10.0,
                      "wave_direction": 270.0})
    gfs_times = sorted(set(hourly) & set(frames(gfs_frames)) | set(hourly[1:gfs_frames * 3 - 2]))
    gfs = FakeModel(RUN, ["wind_u_component_10m", "wind_v_component_10m", "temperature_2m", "precipitation",
                          "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high"], gfs_times,
                    {"wind_u_component_10m": 10.0, "wind_v_component_10m": -5.0, "temperature_2m": 15.0,
                     "precipitation": 2.0, "cloud_cover_low": 50.0, "cloud_cover_mid": 20.0, "cloud_cover_high": 0.0},
                    absent=[(v, RUN) for v in ("precipitation", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high")])
    g25 = FakeModel(RUN, ["cape", "lifted_index", "pressure_msl"], frames(),
                    {"cape": 1000.0, "lifted_index": -2.0, "pressure_msl": 1000.0})
    ifs_run = RUN - 6 * H
    times = ifs_times if ifs_times is not None else [t for t in frames() if t - RUN <= ifs_hours * H]
    ifs = FakeModel(ifs_run, list(ifs_vars), times,
                    {"pressure_msl": ifs_pressure, "wind_gusts_10m": 20.0})  # IFS pressure is in Pa
    day = datetime(2026, 11, 12, tzinfo=timezone.utc)
    ocean_times = [day + h * H for h in range(0, 24 * 10)]
    cur = FakeModel(day, ["ocean_u_current", "ocean_v_current"], ocean_times,
                    {"ocean_u_current": 0.5, "ocean_v_current": -0.5})
    sst = FakeModel(day, ["sea_surface_temperature"], ocean_times, {"sea_surface_temperature": 20.0})
    return RunSources(wave=wave, gfs=gfs, g25=g25, ifs=ifs, cur=cur, sst=sst)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    return build_run(RUN, out / "cache", out / "wx", sources=fake_sources(), ice=NO_ICE)


def test_writes_every_family(built):
    for fam in "abtsw":
        sizes = [Image.open(built / f"globe-{fam}{i}.webp").size for i in range(7)]
        assert sizes == [(3072, 768)] * 6 + [(3072, 1152)], fam
    assert Image.open(built / "globe-c.webp").size == (3072, 768)


def test_manifest_flags_and_sources(built):
    m = json.loads((built / "globe.json").read_text())
    assert m["frames"] == 57 and m["chunks"] == [8, 8, 8, 8, 8, 8, 9] and m["north"] == 89.7364
    assert m["pressure"] and m["gust"] and m["waves"] and m["currents"] and m["storms"]
    assert m["gustHours"] == 84 and m["currentEvery"] == 24 and m["currentFrames"] == 8
    assert m["sources"] == {"ecmwf": "2026-11-13T00:00Z", "wave": "2026-11-13T06:00Z",
                            "cur": "2026-11-12T00:00Z", "sst": "2026-11-12T00:00Z"}
    p = m["peaks"]
    assert set(p) == {"wind", "rain", "hot", "cold", "gust", "low", "wave", "sea_hot", "current"}
    assert len(p["gust"]) == 85 and all(len(p[k]) == 169 for k in p if k != "gust")
    assert p["wind"][0][0] == round(float(np.hypot(10, 5)), 1) and p["low"][0][0] == 1015.0
    assert p["hot"][0][0] == p["cold"][0][0] == 15.0 and p["current"][0][0] == round(float(np.hypot(.5, .5)), 1)
    assert p["wave"][168] == wave_peak(np.full(SHAPE, 2.0 + 0.1 * 56, np.float32), SG)


def test_frame_contents(built):
    a = unpack_frame(Image.open(built / "globe-a0.webp"), 1)
    b0 = unpack_frame(Image.open(built / "globe-b0.webp"), 0)
    assert (a[..., 0] == 153).all() and (a[..., 1] == 115).all() and (a[..., 2] > 0).all()
    assert (b0[..., 0] == 0).all()  # no cloud at the analysis hour
    assert (b0[..., 1] == encode_pressure(np.array([1015.0]))[0]).all() and (b0[..., 2] > 0).all()
    s = unpack_frame(Image.open(built / "globe-s0.webp"), 1)
    assert (s[..., 0] > 0).all()


def test_gust_stops_after_hour_84(built):
    late = unpack_frame(Image.open(built / "globe-b3.webp"), 5)  # frame 29 = hour 87
    early = unpack_frame(Image.open(built / "globe-b3.webp"), 4)  # frame 28 = hour 84
    assert (late[..., 2] == 0).all() and (early[..., 2] > 0).all()


def test_ifs_gap_falls_back_to_gfs_pressure(tmp_path):
    out = build_run(RUN, tmp_path / "c", tmp_path / "wx", sources=fake_sources(ifs_hours=138), ice=NO_ICE)
    last = unpack_frame(Image.open(out / "globe-b6.webp"), 8)  # hour 168, past IFS
    assert (last[..., 1] == encode_pressure(np.array([1000.0]))[0]).all()


def test_missing_gfs_frame_refuses_to_build(tmp_path):
    with pytest.raises(RunIncomplete):
        build_run(RUN, tmp_path / "c", tmp_path / "wx", sources=fake_sources(gfs_frames=50), ice=NO_ICE)
    assert not (tmp_path / "wx").exists() or list((tmp_path / "wx").iterdir()) == []


def test_missing_wave_frame_refuses_to_build(tmp_path):
    with pytest.raises(RunIncomplete):
        build_run(RUN, tmp_path / "c", tmp_path / "wx", sources=fake_sources(wave_frames=56), ice=NO_ICE)


def test_cli_exit_codes(tmp_path, monkeypatch, capsys):
    def boom(run, cache_dir, out_dir, **kw):
        raise RunIncomplete("ncep_gfs013 run 2026-11-13T06:00Z is still being published")

    monkeypatch.setattr("pipeline.__main__.build_run", boom)
    code = main(["build", "--run", "2026111306", "--cache", str(tmp_path), "--out", str(tmp_path)])
    assert code == 2 and "still being published" in capsys.readouterr().err


def test_failure_midway_leaves_no_output(tmp_path):
    src = fake_sources()
    real = src.gfs.field

    def flaky(variable, t):
        if t == RUN + 30 * H:
            raise OSError("disk full")
        return real(variable, t)

    src.gfs.field = flaky
    with pytest.raises(OSError):
        build_run(RUN, tmp_path / "c", tmp_path / "wx", sources=src, ice=NO_ICE)
    assert list((tmp_path / "wx").iterdir()) == []


def test_swap_failure_restores_the_existing_run(tmp_path, monkeypatch):
    out = build_run(RUN, tmp_path / "c", tmp_path / "wx", sources=fake_sources(), ice=NO_ICE)
    (out / "marker").write_text("old")
    import pipeline.build as b
    real = b.Path.rename

    def flaky(self, target):
        if self.name.endswith(".tmp"):
            raise PermissionError("locked")
        return real(self, target)

    monkeypatch.setattr(b.Path, "rename", flaky)
    with pytest.raises(PermissionError):
        build_run(RUN, tmp_path / "c", tmp_path / "wx", sources=fake_sources(), ice=NO_ICE)
    assert (out / "marker").read_text() == "old" and (out / "globe-w0.webp").exists()


def test_write_latest(tmp_path):
    from pipeline.build import write_latest
    write_latest(tmp_path, datetime(2026, 11, 13, 6, tzinfo=timezone.utc),
                 datetime(2026, 11, 14, 9, 30, tzinfo=timezone.utc))
    assert json.loads((tmp_path / "latest.json").read_text()) == {
        "run": "2026-11-13T06:00Z", "dir": "2026111306", "built": "2026-11-14T09:30:00Z"}
    assert not (tmp_path / "latest.json.part").exists()


# --- final review fixes ---

def test_long_ifs_run_is_interpolated_between_6_hourly_steps(tmp_path):
    """IFS 00Z/12Z runs go 6-hourly after their hour 144: frames between steps take the
    linear mean in time, not GFS (the pressure layer flickered otherwise)."""
    steps = [RUN + h * H for h in range(0, 139, 3)] + [RUN + h * H for h in range(144, 169, 6)]
    pa = lambda t: 99000.0 + 10.0 * ((t - RUN) / H)  # 0.1 hPa per hour
    out = build_run(RUN, tmp_path / "c", tmp_path / "wx", ice=NO_ICE,
                    sources=fake_sources(ifs_times=steps, ifs_pressure=pa))
    for slot, hour in ((0, 144), (1, 147), (3, 153)):  # frames 48, 49, 51
        got = unpack_frame(Image.open(out / "globe-b6.webp"), slot)[..., 1]
        assert (got == encode_pressure(np.array([990.0 + 0.1 * hour]))[0]).all(), hour
    low = json.loads((out / "globe.json").read_text())["peaks"]["low"]
    assert low[147][0] == round(990.0 + 0.1 * 147, 1) and low[141][0] == round(990.0 + 0.1 * 141, 1)


def test_ifs_without_pressure_refuses_before_writing(tmp_path):
    with pytest.raises(RunIncomplete, match="ifs pressure_msl"):
        build_run(RUN, tmp_path / "c", tmp_path / "wx", ice=NO_ICE, sources=fake_sources(ifs_vars=("wind_gusts_10m",)))
    assert not (tmp_path / "wx").exists() or list((tmp_path / "wx").iterdir()) == []


def test_prune_evicts_inputs_once_no_later_frame_needs_them(tmp_path):
    src = fake_sources()
    build_run(RUN, tmp_path / "c", tmp_path / "wx", sources=src, ice=NO_ICE, prune=True)
    last = RUN + 168 * H
    for name in ("wave", "gfs", "g25", "ifs", "cur", "sst"):
        ev = getattr(src, name).evicted
        assert ev and ev == sorted(ev) and ev[-1] > last, name  # everything goes at the end
    # while frames remain, nothing a later frame reads is evicted
    gfs_cuts = src.gfs.evicted[:-1]
    assert all(c <= RUN + (3 * j + 2) * H for j, c in enumerate(gfs_cuts))  # rain reads (t-1h, t+1h]
    assert all(c <= RUN + 3 * j * H - 3 * H for j, c in enumerate(src.ifs.evicted[:-1]))



def test_cli_prune_is_opt_in(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr("pipeline.__main__.build_run", lambda run, cache, out, **kw: seen.append(kw) or out)
    main(["build", "--run", "2026111306", "--cache", str(tmp_path), "--out", str(tmp_path)])
    main(["build", "--run", "2026111306", "--cache", str(tmp_path), "--out", str(tmp_path), "--prune"])
    assert seen == [{"prune": False}, {"prune": True}]
