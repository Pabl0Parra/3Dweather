import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from pipeline.grid import GLOBE
from pipeline.regrid import SourceGrid
from pipeline.station_wx import FIELDS, StationSampler

UTC = timezone.utc
RUN = datetime(2026, 11, 15, 6, tzinfo=UTC)
TIMES = [RUN + timedelta(hours=3 * k) for k in range(3)]
G1 = SourceGrid(lat0=-90.0, lon0=-180.0, dlat=1.0, dlon=1.0)  # 181 x 360, rows south to north


def rec(id_, lat, lon, cc="US", region="new-york"):
    return {"id": id_, "latitude": lat, "longitude": lon, "country_code": cc, "region_slug": region}


def lat_lon_field(grid_lats, grid_lons):
    """A field whose value encodes the cell: lat * 1000 + lon."""
    return (grid_lats[:, None] * 1000 + grid_lons[None, :]).astype(np.float32)


def test_source_grid_and_globe_indices_pick_the_nearest_cell():
    s = StationSampler([rec("a", 40.7, -74.0), rec("b", -33.9, 179.8)], TIMES)
    src = lat_lon_field(np.arange(-90, 91, 1.0), np.arange(-180, 180, 1.0))
    s.add(TIMES[0], "t", src, G1)
    assert s.values("t", TIMES[0]) == pytest.approx([41 * 1000 - 74, -34 * 1000 - 180])  # 179.8 wraps to -180
    glob = lat_lon_field(GLOBE.lats(), GLOBE.lons())
    s.add(TIMES[0], "p", glob, GLOBE)
    y, x = GLOBE.cell_of(40.7, -74.0)
    assert s.values("p", TIMES[0])[0] == pytest.approx(glob[y, x])


def test_sea_fields_take_the_nearest_sea_cell_within_3_cells():
    s = StationSampler([rec("coast", 10.0, 20.0), rec("inland", 30.0, 20.0)], TIMES)
    f = np.full((181, 360), np.nan, np.float32)
    f[100 - 2, 200] = 1.5  # 8 N, 20 E: two cells south of the coast station
    s.add(TIMES[0], "wh", f, G1, sea=True)
    assert s.values("wh", TIMES[0])[0] == pytest.approx(1.5)
    assert np.isnan(s.values("wh", TIMES[0])[1])


def test_wind_speed_and_direction_from_components():
    s = StationSampler([rec("a", 0.0, 0.0)], TIMES)
    u = np.zeros((181, 360), np.float32)
    v = np.full((181, 360), -5.0, np.float32)  # blowing toward the south: a north wind
    s.add_wind(TIMES[0], u, v, G1)
    assert s.values("ws", TIMES[0])[0] == pytest.approx(5.0) and s.values("wd", TIMES[0])[0] == pytest.approx(0.0)


def test_write_groups_by_region_scales_and_carries_sst_forward(tmp_path):
    s = StationSampler([rec("a", 0.0, 0.0), rec("b", 0.0, 1.0, "FR", "brittany"), rec("c", 0.0, 2.0, "XX", None)], TIMES)
    t = np.full((181, 360), 12.34, np.float32)
    for tm in TIMES[:2]:
        s.add(tm, "t", t, G1)
    s.add(RUN - timedelta(hours=6), "sst", np.full((181, 360), 18.27, np.float32), G1, sea=True)
    n = s.write(tmp_path, "2026-11-15T06:00Z")
    assert n == 3
    us = json.loads((tmp_path / "stations" / "us" / "new-york.json").read_text(encoding="utf-8"))
    assert us["v"] == 1 and us["run"] == "2026-11-15T06:00Z" and us["start"] == "2026-11-15T06:00Z"
    assert us["step_h"] == 3 and us["n"] == 3 and us["fields"] == list(FIELDS) and us["scale"] == FIELDS
    a = us["stations"]["a"]
    assert a["t"] == [123, 123, None]  # tenths of a degree; the third time was never added
    assert a["sst"] == [183, 183, 183]  # daily: the last value before each time
    assert a["g"] == [None, None, None]
    assert (tmp_path / "stations" / "fr" / "brittany.json").exists()
    assert (tmp_path / "stations" / "xx" / "_.json").exists()


def test_publish_run_uploads_subfolders(tmp_path):
    from pipeline.publish import DirStore, publish_run
    run_dir = tmp_path / "2026111506"
    (run_dir / "stations" / "us").mkdir(parents=True)
    (run_dir / "globe.json").write_text("{}", encoding="utf-8")
    (run_dir / "stations" / "us" / "new-york.json").write_text("{}", encoding="utf-8")
    store = DirStore(tmp_path / "bucket")
    publish_run(store, run_dir, RUN, RUN)
    assert store.get_bytes("wx/2026111506/stations/us/new-york.json") == b"{}"
    assert store.get_bytes("wx/2026111506/globe.json") == b"{}"


def test_cli_reads_the_catalogue_or_goes_without(tmp_path, capsys):
    from pipeline.__main__ import _stations
    assert _stations(None) is None
    assert _stations(tmp_path / "missing.json") is None
    assert "no station weather" in capsys.readouterr().err
    p = tmp_path / "stations.json"
    p.write_text(json.dumps([rec("a", 1.0, 2.0)]), encoding="utf-8")
    assert _stations(p)[0]["id"] == "a"
