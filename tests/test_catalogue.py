import gzip
import json
from pathlib import Path

import pytest

from pipeline.catalogue import (
    COAST_KM,
    build_catalogue,
    coast_points,
    fetch_inputs,
    INPUTS,
    CoastIndex,
    slugify,
    write_catalogue,
)

ROOT = Path(__file__).resolve().parents[1]
REAL_INPUTS = ROOT / "catalogue-inputs"
REAL_COAST = ROOT / "reference" / "naturalearth" / "ne_50m_coastline.geojson"

# A straight north-south "coast" along the prime meridian from 40N to 60N, and one
# around a small mid-Pacific island far from any place.
COAST = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {}, "geometry": {"type": "LineString", "coordinates": [[0, 40], [0, 60]]}},
    {"type": "Feature", "properties": {}, "geometry": {"type": "LineString",
     "coordinates": [[-170.0, 10.0], [-169.9, 10.0], [-169.9, 10.1], [-170.0, 10.0]]}},
]}


def _city(gid, name, lat, lon, cc="FR", a1="11", a2="75", pop=1000, tz="Europe/Paris", ascii=None):
    cols = [str(gid), name, ascii if ascii is not None else name, "", f"{lat}", f"{lon}", "P", "PPL", cc, "",
            a1, a2, "", "", str(pop), "", "0", tz, "2024-01-01"]
    return "\t".join(cols)


def _noaa(sid, name, lat, lon, state="", corr=-10, typ="R", ref=""):
    return {"id": sid, "name": name, "lat": lat, "lng": lon, "state": state, "timezonecorr": corr,
            "type": typ, "reference_id": ref}


def write_inputs(d: Path, cities: list[str], noaa: list[dict]) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "cities500.txt").write_text("\n".join(cities) + "\n", encoding="utf-8")
    (d / "admin1CodesASCII.txt").write_text(
        "FR.11\tÎle-de-France\tIle-de-France\t3012874\n"
        "US.HI\tHawaii\tHawaii\t5855797\n"
        "US.NY\tNew York\tNew York\t5128638\n"
        "JP.40\tTokyo\tTokyo\t1850144\n", encoding="utf-8")
    (d / "admin2Codes.txt").write_text("FR.11.75\tParis\tParis\t2968815\n", encoding="utf-8")
    (d / "countryInfo.txt").write_text(
        "# ISO\tISO3\tISO-Numeric\tfips\tCountry\tCapital\tArea\tPopulation\tContinent\n"
        "FR\tFRA\t250\tFR\tFrance\tParis\t547030\t66987244\tEU\n"
        "US\tUSA\t840\tUS\tUnited States\tWashington\t9629091\t327167434\tNA\n"
        "JP\tJPN\t392\tJA\tJapan\tTokyo\t377835\t126529100\tAS\n"
        "KI\tKIR\t296\tKR\tKiribati\tTarawa\t811\t115847\tOC\n", encoding="utf-8")
    (d / "noaa-tidepredictions.json").write_text(json.dumps({"count": len(noaa), "stations": noaa}), encoding="utf-8")
    coast = d / "coast.geojson"
    coast.write_text(json.dumps(COAST), encoding="utf-8")
    return coast


def build(tmp_path, cities, noaa=()):
    coast = write_inputs(tmp_path / "in", cities, list(noaa))
    return build_catalogue(tmp_path / "in", coast, overrides={})  # fixtures, not the packaged table


def by_name(records, name):
    return [r for r in records if r["name"] == name]


def test_every_noaa_station_is_a_gauge(tmp_path):
    recs = build(tmp_path, [_city(1, "Coastville", 45, 0.02)],
                 [_noaa("9414290", "San Francisco", 37.8, -122.47, state="CA"), _noaa("1611347", "Port Allen", 21.9, -159.59, "HI")])
    gauges = [r for r in recs if r["type"] == "gauge"]
    assert sorted(r["id"] for r in gauges) == ["n1611347", "n9414290"]
    assert all(r["has_tides"] and r["reference_station"] is None for r in gauges)


def test_places_beyond_coast_km_are_dropped(tmp_path):
    # 0.02 deg at 45N is 1.6 km from the coast; 0.1 deg is 7.9 km.
    assert COAST_KM == 4.5
    recs = build(tmp_path, [_city(1, "Near", 45, 0.02), _city(2, "Far", 45, 0.1)])
    assert [r["name"] for r in recs] == ["Near"]
    r = recs[0]
    assert r["id"] == "g1" and r["type"] == "place"
    assert (r["country_code"], r["region_name"], r["region_slug"], r["county"], r["timezone"]) == \
        ("FR", "Île-de-France", "ile-de-france", "Paris", "Europe/Paris")
    assert r["path"] == "fr/ile-de-france/near"


def test_close_smaller_place_is_deduplicated(tmp_path):
    # 0.003 deg of latitude is 0.33 km apart: the smaller one goes.
    recs = build(tmp_path, [_city(1, "Small", 45.003, 0.02, pop=600), _city(2, "Big", 45, 0.02, pop=50000),
                            _city(3, "Apart", 45.05, 0.02, pop=600)])
    assert sorted(r["name"] for r in recs) == ["Apart", "Big"]


def test_gauge_takes_country_region_tz_from_nearest_place(tmp_path):
    recs = build(tmp_path, [_city(1, "Coastville", 45, 0.02), _city(2, "Inland", 45.2, 1.5, a2="")],
                 [_noaa("1", "Pointe", 45.01, 0.0, state="", corr=1)])
    g = by_name(recs, "Pointe")[0]
    assert (g["country_code"], g["region_name"], g["timezone"]) == ("FR", "Île-de-France", "Europe/Paris")
    assert g["path"] == "fr/ile-de-france/pointe"


def test_us_gauge_region_comes_from_its_state(tmp_path):
    recs = build(tmp_path, [_city(1, "Coastville", 45, 0.02)],
                 [_noaa("1611347", "Port Allen, Hanapepe Bay", 21.9, -159.59, state="HI", corr=-10)])
    g = recs[[r["name"] for r in recs].index("Port Allen, Hanapepe Bay")]
    assert (g["country_code"], g["region_name"], g["region_slug"]) == ("US", "Hawaii", "hawaii")
    assert g["path"] == "us/hawaii/port-allen-hanapepe-bay"


def test_far_us_gauge_takes_zone_from_its_state(tmp_path):
    # An Aleutian-style gauge 900 km from the only Hawaii place still gets a real (DST-aware) zone.
    recs = build(tmp_path, [_city(1, "Coastville", 45, 0.02),
                            _city(2, "Hilo", 19.72, -155.08, cc="US", a1="HI", a2="", tz="Pacific/Honolulu")],
                 [_noaa("1619910", "Sand Island", 28.2, -162.0, state="HI", corr=-10)])
    assert by_name(recs, "Sand Island")[0]["timezone"] == "Pacific/Honolulu"


def test_gauge_far_from_places_still_has_tz_and_region(tmp_path):
    recs = build(tmp_path, [_city(1, "Coastville", 45, 0.02)],
                 [_noaa("1890000", "Lonely Atoll", 10.0, -170.0, state="", corr=-11)])
    g = by_name(recs, "Lonely Atoll")[0]
    assert g["timezone"] == "Etc/GMT+11"  # POSIX sign: UTC-11
    assert g["country_code"] and g["region_name"] and g["region_slug"]


def test_place_within_5km_of_gauge_names_it_as_reference_station(tmp_path):
    recs = build(tmp_path, [_city(1, "Harbour Town", 45, 0.02), _city(2, "Other Town", 45.2, 0.02)],
                 [_noaa("8518750", "The Battery", 45.01, 0.0, state="", corr=1)])
    near, far = by_name(recs, "Harbour Town")[0], by_name(recs, "Other Town")[0]
    assert near["reference_station"] == {"slug": "the-battery", "name": "The Battery", "path": "fr/ile-de-france/the-battery"}
    assert far["reference_station"] is None


def test_slugify():
    assert slugify("NEW YORK (The Battery)") == "new-york-the-battery"
    assert slugify("Île-de-France") == "ile-de-france"
    assert slugify("St. John's") == "st-john-s"
    assert slugify("東京") == ""


def test_paths_unique_and_ascii(tmp_path):
    recs = build(tmp_path, [
        _city(1, "Twin", 45, 0.02, pop=900), _city(2, "Twin", 46, 0.02, pop=800), _city(3, "Twin", 47, 0.02, pop=700),
        _city(4, "東京", 48, 0.02, ascii="Tokyo"), _city(5, "東京", 49, 0.02, ascii=""),
    ])
    paths = [r["path"] for r in recs]
    assert len(set(paths)) == len(paths)
    assert {"fr/ile-de-france/twin", "fr/ile-de-france/twin-2", "fr/ile-de-france/twin-3",
            "fr/ile-de-france/tokyo", "fr/ile-de-france/place-5"} == set(paths)  # suffixes are GeoNames ids
    assert all(p.isascii() for p in paths)


def test_coast_distance_km(tmp_path):
    idx = CoastIndex(coast_points(COAST))
    import numpy as np
    d = idx.distance_km(np.array([45.0, 45.0, 0.0]), np.array([0.02, 0.1, 100.0]))
    assert d[0] == pytest.approx(1.57, abs=0.05)
    assert d[1] == pytest.approx(7.86, abs=0.05)
    assert d[2] >= 99


def test_written_files(tmp_path):
    recs = build(tmp_path, [_city(1, "Near", 45, 0.02, pop=20000), _city(2, "Harbour", 46, 0.02)],
                 [_noaa("1611347", "Port Allen", 21.9, -159.59, "HI")])
    out = tmp_path / "out"
    write_catalogue(recs, tmp_path / "in", out)
    stations = json.loads((out / "stations.json").read_text(encoding="utf-8"))
    assert stations == [{k: v for k, v in r.items() if not k.startswith("_")} for r in recs]  # _pop stays private
    assert "_pop" not in stations[0]
    search = json.loads((out / "search.json").read_text(encoding="utf-8"))
    assert search["v"] == 1
    assert search["fields"] == ["id", "name", "cc", "region", "lat", "lon", "type", "path", "rank"]
    rows = {r[0]: r for r in search["rows"]}
    assert rows["g1"] == ["g1", "Near", "FR", "Île-de-France", 45.0, 0.02, 1, "fr/ile-de-france/near", 4]
    assert rows["n1611347"][6] == 0 and rows["n1611347"][8] == 5  # a gauge ranks like a town of ~100,000
    countries = json.loads((out / "countries.json").read_text(encoding="utf-8"))
    assert sum(c["count"] for c in countries) == len(recs)
    fr = next(c for c in countries if c["cc"] == "FR")
    assert (fr["name"], fr["continent"], fr["regions"]) == ("France", "EU", [{"slug": "ile-de-france", "name": "Île-de-France", "count": 2}])


@pytest.mark.reference
@pytest.mark.skipif(not (REAL_INPUTS / "noaa-tidepredictions.json").exists() or not REAL_COAST.exists(),
                    reason="run tools/fetch_catalogue_inputs.py first")
def test_real_catalogue_near_reference_counts(tmp_path):
    recs = build_catalogue(REAL_INPUTS, REAL_COAST)
    n = len(recs)
    us = sum(r["country_code"] == "US" for r in recs)
    countries = len({r["country_code"] for r in recs})
    print(f"total {n}, US {us}, countries {countries}, gauges {sum(r['type'] == 'gauge' for r in recs)}")
    assert abs(n - 24631) <= 0.15 * 24631
    assert abs(us - 4111) <= 0.25 * 4111
    assert abs(countries - 190) <= 0.15 * 190
    write_catalogue(recs, REAL_INPUTS, tmp_path)
    assert len(gzip.compress((tmp_path / "search.json").read_bytes())) < 2_000_000
    paths = [r["path"] for r in recs]
    assert len(set(paths)) == n and all(p.isascii() and r["timezone"] for p, r in zip(paths, recs))


def test_fetch_inputs_downloads_only_what_is_missing(tmp_path):
    (tmp_path / "countryInfo.txt").write_text("", encoding="utf-8")
    got = []
    def fake(url, dest):
        got.append(url)
        dest.write_text("x", encoding="utf-8")
    coast = fetch_inputs(tmp_path, fetch=fake)
    assert coast == tmp_path / "ne_50m_coastline.geojson" and coast.exists()
    assert len(got) == len(INPUTS) - 1
    assert "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=tidepredictions" in got
    assert not any("countryInfo" in u for u in got)
    assert fetch_inputs(tmp_path, fetch=fake) == coast and len(got) == len(INPUTS) - 1


# --- review fixes ---------------------------------------------------------------------------

def test_override_sets_country_and_fixes_position(tmp_path):
    coast = write_inputs(tmp_path / "in", [_city(1, "Coastville", 45, 0.02)],
                         [_noaa("TPT2893", "Neiafu", -18.65, 6.0167, corr=-11),
                          _noaa("1619910", "Sand Island, Midway", 28.21, -177.36, corr=-11)])
    overrides = {"TPT2893": {"cc": "TO", "lon": -173.9833}, "1619910": {"cc": "UM"}}
    recs = build_catalogue(tmp_path / "in", coast, overrides=overrides)
    neiafu, midway = by_name(recs, "Neiafu")[0], by_name(recs, "Sand Island, Midway")[0]
    assert (neiafu["country_code"], neiafu["longitude"], neiafu["region_name"]) == ("TO", -173.9833, "TO")  # no countryInfo row
    assert midway["path"].startswith("um/") and midway["timezone"] == "Etc/GMT+11"


def test_override_can_route_a_gauge_through_its_us_state(tmp_path):
    coast = write_inputs(tmp_path / "in", [_city(1, "Coastville", 45, 0.02)],
                         [_noaa("TWC2307", "Kiska Harbor", 51.98, 177.55, corr=-10)])
    recs = build_catalogue(tmp_path / "in", coast, overrides={"TWC2307": {"state": "HI"}})  # fixture has HI only
    assert by_name(recs, "Kiska Harbor")[0]["path"] == "us/hawaii/kiska-harbor"


def test_packaged_overrides_load():
    from pipeline.catalogue import load_overrides
    o = load_overrides()
    assert o["TPT2893"]["cc"] == "TO" and o["TWC2307"]["state"] == "AK"


def test_places_claim_slugs_before_gauges(tmp_path):
    recs = build(tmp_path, [_city(10, "Boston", 45, 0.02, pop=600000)],
                 [_noaa("8443970", "Boston", 45.01, 0.0, corr=1)])
    assert by_name(recs, "Boston")[0]["type"] == "place"
    paths = {r["type"]: r["path"] for r in recs}
    assert paths == {"place": "fr/ile-de-france/boston", "gauge": "fr/ile-de-france/boston-8443970"}
    place = [r for r in recs if r["type"] == "place"][0]
    assert place["reference_station"]["path"] == "fr/ile-de-france/boston-8443970"


def test_place_suffixes_are_stable_ids(tmp_path):
    recs = build(tmp_path, [_city(7, "Twin", 45, 0.02, pop=900), _city(3, "Twin", 46, 0.02, pop=800)])
    assert sorted(r["path"] for r in recs) == ["fr/ile-de-france/twin", "fr/ile-de-france/twin-3"]


@pytest.mark.reference
@pytest.mark.skipif(not (REAL_INPUTS / "noaa-tidepredictions.json").exists(), reason="run the catalogue command first")
def test_every_remote_blank_state_gauge_has_an_override():
    """A NOAA station far from every GeoNames place cannot borrow a country: it needs an entry in catalogue_overrides.json."""
    import numpy as np
    from pipeline.catalogue import LOCAL_KM, _nearest, _read_cities, load_overrides
    noaa = json.loads((REAL_INPUTS / "noaa-tidepredictions.json").read_text(encoding="utf-8"))["stations"]
    cities = _read_cities(REAL_INPUTS)
    blank = [s for s in noaa if not (s.get("state") or "").strip()]
    _, km = _nearest([float(s["lat"]) for s in blank], [float(s["lng"]) for s in blank],
                     np.array([float(r[4]) for r in cities]), np.array([float(r[5]) for r in cities]))
    overrides = load_overrides()
    missing = [s["id"] for s, k in zip(blank, km) if k > LOCAL_KM and str(s["id"]) not in overrides]
    assert missing == []
