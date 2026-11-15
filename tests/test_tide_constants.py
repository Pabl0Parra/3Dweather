import json
from pathlib import Path

import numpy as np
import pytest

h5py = pytest.importorskip("h5py")

from pipeline.tide_constants import assign, fetch_noaa  # noqa: E402
from pipeline.tide_model import EOT20_NAMES, FES2022_NAMES, ModelReader, sample_model  # noqa: E402


def write_model(d: Path, names, suffix="_ocean_eot20.nc", land_box=None, amp_cm=50.0, step=1.0, lats=(-90, 90)):
    """A grid laid out like EOT20's files (lat south to north, lon 0..360 inclusive, cm, 0 = land)."""
    d.mkdir(parents=True, exist_ok=True)
    lat = np.round(np.arange(lats[0], lats[1] + step / 2, step), 6)
    lon = np.round(np.arange(0, 360 + step / 2, step), 6)
    for k, name in enumerate(names):
        amp = np.full((lat.size, lon.size), amp_cm + k, dtype=np.float32)
        phase = np.full_like(amp, 10.0 * k)
        if land_box:
            la0, la1, lo0, lo1 = land_box
            amp[np.ix_((lat >= la0) & (lat <= la1), (lon >= lo0 % 360) & (lon <= lo1 % 360))] = 0
        with h5py.File(d / f"{name}{suffix}", "w") as f:
            f["lat"], f["lon"], f["amplitude"], f["phase"] = lat, lon, amp, phase
    return d


def rec(id_, lat, lon, type_="place", ref=None):
    return {"id": id_, "name": id_, "latitude": lat, "longitude": lon, "type": type_, "path": f"x/y/{id_}",
            "reference_station": ref}


# --- model sampling --------------------------------------------------------------------------

def test_samples_every_constituent_at_an_ocean_point(tmp_path):
    src = write_model(tmp_path / "eot", ["M2", "S2"])
    reader = ModelReader.eot20(src, names=["M2", "S2"])
    out = sample_model([rec("g1", 10.05, 20.05)], reader)  # 7.8 km from the 10 N, 20 E node
    assert out["g1"] == [["M2", 0.5, 0.0], ["S2", 0.51, 10.0]]


def test_land_point_takes_the_nearest_ocean_cell_within_20_km(tmp_path):
    # 0.05° nodes; land from 10 to 12 N. 10.05 N is a land node 5.6 km from the ocean node at 9.95 N.
    src = write_model(tmp_path / "eot", ["M2"], land_box=(10, 12, 20, 22), step=0.05, lats=(8, 14))
    reader = ModelReader.eot20(src, names=["M2"])
    out = sample_model([rec("near", 10.05, 21.0), rec("in", 10.12, 21.0), rec("out", 10.15, 21.0),
                        rec("deep", 11.0, 21.0)], reader)
    assert out["near"] == [["M2", 0.5, 0.0]]
    assert out["in"] == [["M2", 0.5, 0.0]]  # 18.9 km from the 9.95 N node
    assert out["out"] is None  # 22.2 km
    assert out["deep"] is None  # 111 km inland


def test_fes_names_map_to_noaa_spelling():
    assert FES2022_NAMES["lambda2"] == "LAM2" and FES2022_NAMES["m2"] == "M2" and FES2022_NAMES["mks2"] == "MKS2"
    assert set(EOT20_NAMES) >= {"M2", "S2", "K1", "O1", "SA", "SSA", "MF", "MM", "T2"}


def test_fes_reader_reads_the_same_layout(tmp_path):
    src = write_model(tmp_path / "fes", ["m2", "lambda2"], suffix="_fes2022.nc")
    reader = ModelReader.fes2022(src, names=["m2", "lambda2"])
    out = sample_model([rec("g1", -30.0, 150.0)], reader)
    assert [c[0] for c in out["g1"]] == ["M2", "LAM2"]


# --- NOAA fetching ---------------------------------------------------------------------------

HARCON = {"HarmonicConstituents": [{"name": "M2", "amplitude": 0.671, "phase_GMT": 18.2},
                                   {"name": "S2", "amplitude": 0.128, "phase_GMT": 42.9},
                                   {"name": "M8", "amplitude": 0.0, "phase_GMT": 0.0}]}
DATUMS = {"datums": [{"name": "MSL", "value": 1.785}, {"name": "MLLW", "value": 1.002}]}
OFFSETS = {"refStationId": "8518750", "type": "S", "heightOffsetHighTide": 1.03, "heightOffsetLowTide": 0.95,
           "timeOffsetHighTide": -18, "timeOffsetLowTide": -12, "heightAdjustedType": "R"}


def fake_api(calls):
    def fetch(url, dest):
        calls.append(url)
        if "harcon" in url:
            body = HARCON
        elif "datums" in url:
            body = DATUMS
        elif "tidepredoffsets" in url:
            body = OFFSETS
        else:
            raise AssertionError(url)
        dest.write_text(json.dumps(body), encoding="utf-8")
    return fetch


def test_fetch_noaa_gets_what_each_type_needs_and_caches(tmp_path):
    stations = [{"id": "8518750", "type": "R"}, {"id": "8517921", "type": "S"}]
    calls = []
    got = fetch_noaa(stations, tmp_path, fetch=fake_api(calls), pause=0)
    assert got["8518750"]["cons"] == [["M2", 0.671, 18.2], ["S2", 0.128, 42.9]]  # zero amplitudes dropped
    assert got["8518750"]["msl_above_mllw"] == pytest.approx(0.783)
    assert got["8517921"]["offsets"] == {"ref": "8518750", "th": -18, "tl": -12, "hh": 1.03, "hl": 0.95, "kind": "R"}
    n = len(calls)
    assert n == 3
    fetch_noaa(stations, tmp_path, fetch=fake_api(calls), pause=0)
    assert len(calls) == n  # all from the cache


def test_fetch_noaa_stops_on_failures_but_keeps_what_it_got(tmp_path):
    import urllib.error
    from pipeline.tide_constants import NoaaFetchError
    ok = fake_api([])

    def flaky(url, dest):
        if "8517921" in url:
            raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)
        ok(url, dest)
    with pytest.raises(NoaaFetchError, match="1 of 3"):
        fetch_noaa([{"id": "8518750", "type": "R"}, {"id": "8517921", "type": "S"}], tmp_path, fetch=flaky, pause=0)
    assert (tmp_path / "8518750-harcon.json").exists() and not (tmp_path / "8517921-offsets.json").exists()


def test_fetch_noaa_caches_404_as_no_data(tmp_path):
    import urllib.error
    calls = []

    def missing(url, dest):
        calls.append(url)
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
    got = fetch_noaa([{"id": "1", "type": "R"}], tmp_path, fetch=missing, pause=0)
    assert got["1"] == {"type": "R", "cons": [], "msl_above_mllw": None}
    fetch_noaa([{"id": "1", "type": "R"}], tmp_path, fetch=missing, pause=0)
    assert len(calls) == 1


# --- assignment ------------------------------------------------------------------------------

CONS = [["M2", 0.6, 10.0]]


def test_assign_follows_the_spec_rules():
    noaa = {
        "R1": {"type": "R", "cons": CONS, "msl_above_mllw": 0.8},
        "R0": {"type": "R", "cons": [], "msl_above_mllw": None},  # no constants published
        "S1": {"type": "S", "offsets": {"ref": "R1", "th": -18, "tl": -12, "hh": 1.0, "hl": 1.0, "kind": "R"}},
        "S2": {"type": "S", "offsets": {"ref": "RFAR", "th": 0, "tl": 0, "hh": 1.0, "hl": 1.0, "kind": "R"}},
        "S3": {"type": "S", "offsets": {"ref": "S1", "th": 0, "tl": 0, "hh": 1.0, "hl": 1.0, "kind": "R"}},
        "S4": {"type": "S", "offsets": {"ref": "NOPE", "th": 0, "tl": 0, "hh": 1.0, "hl": 1.0, "kind": "R"}},
        "RFAR": {"type": "R", "cons": CONS, "msl_above_mllw": 0.5},
    }
    records = [
        rec("nR1", 40.7, -74.0, "gauge"), rec("nR0", 41.0, -71.0, "gauge"),
        rec("nS1", 40.71, -73.96, "gauge"), rec("nS2", 21.0, -158.0, "gauge"),
        rec("nS3", 40.8, -73.9, "gauge"), rec("nS4", 40.9, -73.8, "gauge"),
        rec("nRFAR", 50.0, -10.0, "gauge"),
        rec("gNear", 40.705, -74.01, ref={"slug": "r1", "name": "R1", "path": "x/y/nR1"}),
        rec("gDonorBad", 41.0, -71.01, ref={"slug": "r0", "name": "R0", "path": "x/y/nR0"}),
        rec("gSea", 30.0, -60.0), rec("gInland", 45.0, 10.0),
    ]
    model = {"nR0": CONS, "nS2": CONS, "nS3": CONS, "nS4": CONS, "gDonorBad": CONS, "gSea": CONS, "gInland": None}
    out = assign(records, noaa, model)
    assert out["nR1"] == {"kind": "harmonic", "cons": CONS, "d": 0.8}
    assert out["nR0"] == {"kind": "model", "cons": CONS}
    assert out["nS1"] == {"kind": "subordinate", "ref": "nR1", "offsets": [-18, -12, 1.0, 1.0, "R"]}
    assert out["nS2"]["kind"] == "model"  # reference over 1,000 km away
    assert out["nS3"]["kind"] == "model"  # reference is itself subordinate
    assert out["nS4"]["kind"] == "model"  # reference unknown
    assert out["gNear"] == {"kind": "donor", "donor": "nR1"}
    assert out["gDonorBad"]["kind"] == "model"  # the nearby gauge has no usable tide
    assert out["gSea"] == {"kind": "model", "cons": CONS}
    assert out["gInland"] == {"kind": "none"}


def test_a_gauge_without_any_tide_is_none():
    out = assign([rec("nX", 0.0, 0.0, "gauge")], {"X": {"type": "R", "cons": [], "msl_above_mllw": None}}, {"nX": None})
    assert out["nX"] == {"kind": "none"}


# --- model files, merging and the CLI ---------------------------------------------------------

from pipeline.tide_constants import build_constants, noaa_stations, read_model, write_model_file  # noqa: E402


def test_model_file_round_trips_with_its_source(tmp_path):
    p = write_model_file(tmp_path / "m.json", "EOT20 x", {"g1": CONS, "g2": None})
    m = read_model(p)
    assert m["model"] == "EOT20 x" and m["stations"] == {"g1": CONS, "g2": None}


def test_first_model_wins_and_each_model_entry_names_its_source():
    fes = {"model": "FES2022", "stations": {"gA": CONS, "gB": None}}  # gC missing: built from an older catalogue
    eot = {"model": "EOT20", "stations": {"gA": [["M2", 0.1, 0.0]], "gB": [["M2", 0.2, 0.0]], "gC": CONS}}
    out = build_constants([rec("gA", 1, 1), rec("gB", 2, 2), rec("gC", 3, 3), rec("gD", 4, 4)], {}, [fes, eot])
    assert out["models"] == ["FES2022", "EOT20"]
    s = out["stations"]
    assert s["gA"] == {"kind": "model", "cons": CONS, "source": "FES2022"}
    assert s["gB"] == {"kind": "model", "cons": [["M2", 0.2, 0.0]], "source": "EOT20"}
    assert s["gC"]["source"] == "EOT20"
    assert s["gD"] == {"kind": "none"}
    assert out["built"].endswith("Z")


def test_noaa_stations_reads_ids_and_types(tmp_path):
    p = tmp_path / "noaa.json"
    p.write_text(json.dumps({"stations": [{"id": "1", "type": "R"}, {"id": "2", "type": "S"}]}), encoding="utf-8")
    assert noaa_stations(p) == [{"id": "1", "type": "R"}, {"id": "2", "type": "S"}]


def test_cli_writes_model_and_constants_files(tmp_path, monkeypatch):
    from pipeline.__main__ import main
    import pipeline.tide_constants as tc

    src = write_model(tmp_path / "eot", list(EOT20_NAMES))
    cat = tmp_path / "stations.json"
    cat.write_text(json.dumps([rec("g1", 10.0, 20.0), rec("n9", 10.0, 21.0, "gauge")]), encoding="utf-8")
    noaa = tmp_path / "noaa.json"
    noaa.write_text(json.dumps({"stations": [{"id": "9", "type": "R"}]}), encoding="utf-8")
    monkeypatch.setattr(tc, "http_fetch", fake_api([]))
    assert main(["model-constants", "--catalogue", str(cat), "--eot20", str(src), "--out", str(tmp_path / "eot.json")]) == 0
    assert main(["tide-constants", "--catalogue", str(cat), "--noaa", str(noaa), "--noaa-cache", str(tmp_path / "c"),
                 "--model", str(tmp_path / "missing.json"), "--model", str(tmp_path / "eot.json"),
                 "--out", str(tmp_path / "out" / "tide-constants.json")]) == 0
    out = json.loads((tmp_path / "out" / "tide-constants.json").read_text(encoding="utf-8"))
    assert out["models"] == [read_model(tmp_path / "eot.json")["model"]]  # a missing model file is skipped
    assert out["stations"]["n9"]["kind"] == "harmonic"
    assert out["stations"]["g1"]["kind"] == "model" and len(out["stations"]["g1"]["cons"]) == len(EOT20_NAMES)


def test_fes_tool_writes_the_same_model_format(tmp_path):
    import runpy
    src = write_model(tmp_path / "fes", list(FES2022_NAMES), suffix="_fes2022.nc")
    cat = tmp_path / "stations.json"
    cat.write_text(json.dumps([rec("g1", 10.0, 20.0)]), encoding="utf-8")
    tool = runpy.run_path(str(Path(__file__).parent.parent / "tools" / "fes2022_constants.py"))
    tool["main"](["--catalogue", str(cat), "--fes", str(src), "--out", str(tmp_path / "fes.json")])
    m = read_model(tmp_path / "fes.json")
    assert m["model"].startswith("FES2022") and len(m["stations"]["g1"]) == len(FES2022_NAMES)


def test_store_can_name_another_bucket(monkeypatch):
    import pipeline.publish as pub
    seen = {}
    monkeypatch.setattr(pub, "s3_store_from_env", lambda bucket=None: seen.setdefault("b", bucket))
    pub.store_from_arg("r2:private-tides")
    assert seen["b"] == "private-tides"


def test_fetch_noaa_takes_null_lists_as_empty(tmp_path):
    def nulls(url, dest):
        body = {"HarmonicConstituents": HARCON["HarmonicConstituents"]} if "harcon" in url else {"datums": None}
        if "8000000" in url:
            body = {"HarmonicConstituents": None}
        dest.write_text(json.dumps(body), encoding="utf-8")
    got = fetch_noaa([{"id": "1", "type": "R"}, {"id": "8000000", "type": "R"}], tmp_path, fetch=nulls, pause=0)
    assert got["1"]["msl_above_mllw"] is None and got["1"]["cons"]
    assert got["8000000"]["cons"] == []


def test_fetch_noaa_keeps_only_constituents_the_engine_knows(tmp_path):
    def extra(url, dest):
        cons = HARCON["HarmonicConstituents"] + [{"name": "3MS8", "amplitude": 0.02, "phase_GMT": 5.0}]
        body = {"HarmonicConstituents": cons} if "harcon" in url else DATUMS
        dest.write_text(json.dumps(body), encoding="utf-8")
    got = fetch_noaa([{"id": "9455920", "type": "R"}], tmp_path, fetch=extra, pause=0)
    assert [c[0] for c in got["9455920"]["cons"]] == ["M2", "S2"]


def test_fetch_noaa_asks_for_offsets_in_metres():
    calls = []
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        fetch_noaa([{"id": "9414539", "type": "S"}], Path(d), fetch=fake_api(calls), pause=0)
        assert calls == [f"https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/9414539/tidepredoffsets.json?units=metric"]
        assert (Path(d) / "9414539-offsets-m.json").exists()  # not the old feet cache name


def test_fetch_noaa_treats_an_error_body_as_a_failure(tmp_path):
    from pipeline.tide_constants import NoaaFetchError

    def err(url, dest):
        dest.write_text(json.dumps({"error": {"message": "temporarily unavailable"}}), encoding="utf-8")
    with pytest.raises(NoaaFetchError):
        fetch_noaa([{"id": "1", "type": "R"}], tmp_path, fetch=err, pause=0)
    assert not (tmp_path / "1-harcon.json").exists()  # tried again next run


def test_a_nan_phase_drops_that_constituent(tmp_path):
    src = write_model(tmp_path / "eot", ["M2", "S2"])
    with h5py.File(src / "S2_ocean_eot20.nc", "r+") as f:
        ph = f["phase"][:]
        ph[:] = np.nan
        f["phase"][...] = ph
    out = sample_model([rec("g1", 10.05, 20.05)], ModelReader.eot20(src, names=["M2", "S2"]))
    assert out["g1"] == [["M2", 0.5, 0.0]]
