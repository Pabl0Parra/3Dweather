import json
from pathlib import Path

from pipeline.__main__ import main
from pipeline.publish import DirStore
from pipeline.site import MANIFEST, publish_site, site_cache_control, site_content_type, site_key


def make_dist(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


SITE = {
    "wave-map.html": "<h1>globe</h1>",
    "weather-map/europe.html": "<h1>europe</h1>",
    "us/new-york/new-york-city.html": "<h1>NYC</h1>",
    "_astro/app.abc123.js": "console.log(1)",
    "_astro/app.abc123.css": "body{}",
    "favicon.svg": "<svg/>",
    # Dev data copied from web/public: never the site's to publish.
    "wx/latest.json": "{}",
    "assets/globe/coast.json": "[]",
    "catalogue/search.json": "{}",
}


def test_site_key_drops_html():
    assert site_key("us/new-york/new-york-city.html") == "us/new-york/new-york-city"
    assert site_key("wave-map.html") == "wave-map"
    assert site_key("index.html") == "index.html"
    assert site_key("404.html") == "404.html"
    assert site_key("_astro/app.abc123.js") == "_astro/app.abc123.js"


def test_pages_served_as_html():
    assert site_content_type("us/new-york/new-york-city.html") == "text/html; charset=utf-8"
    assert site_content_type("_astro/app.abc123.js") == "text/javascript; charset=utf-8"
    assert site_content_type("_astro/app.abc123.css") == "text/css; charset=utf-8"
    assert site_content_type("favicon.svg") == "image/svg+xml"


def test_cache_controls():
    assert site_cache_control("_astro/app.abc123.js") == "public, max-age=31536000, immutable"
    assert site_cache_control("us/new-york/new-york-city") == "public, max-age=3600"
    assert site_cache_control("favicon.svg") == "public, max-age=3600"


def test_first_publish_uploads_pages_without_html_and_skips_data(tmp_path):
    dist = make_dist(tmp_path / "dist", SITE)
    store = DirStore(tmp_path / "bucket")
    assert publish_site(store, dist) == {"uploaded": 6, "unchanged": 0, "deleted": 0}
    keys = store.list_keys("")
    assert "us/new-york/new-york-city" in keys and "weather-map/europe" in keys and "wave-map" in keys
    assert not any(k.startswith(("wx/", "assets/", "catalogue/")) for k in keys)
    assert store.headers("wave-map") == {"content_type": "text/html; charset=utf-8", "cache_control": "public, max-age=3600"}
    assert store.get_bytes("us/new-york/new-york-city") == b"<h1>NYC</h1>"
    # Assets go up before the pages that load them, and the manifest goes last.
    order = store.order
    assert order.index("_astro/app.abc123.js") < order.index("wave-map")
    assert order[-1] == MANIFEST
    manifest = json.loads(store.get_bytes(MANIFEST))
    assert sorted(manifest) == sorted(k for k in keys if k != MANIFEST)


def test_second_publish_uploads_nothing(tmp_path):
    dist = make_dist(tmp_path / "dist", SITE)
    store = DirStore(tmp_path / "bucket")
    publish_site(store, dist)
    n = len(store.order)
    assert publish_site(store, dist) == {"uploaded": 0, "unchanged": 6, "deleted": 0}
    assert len(store.order) == n  # not even the manifest is rewritten


def test_changed_page_uploaded_alone(tmp_path):
    dist = make_dist(tmp_path / "dist", SITE)
    store = DirStore(tmp_path / "bucket")
    publish_site(store, dist)
    (dist / "wave-map.html").write_text("<h1>globe v2</h1>", encoding="utf-8")
    store.order.clear()
    assert publish_site(store, dist) == {"uploaded": 1, "unchanged": 5, "deleted": 0}
    assert store.order == ["wave-map", MANIFEST]


def test_removed_page_deleted_and_data_untouched(tmp_path):
    dist = make_dist(tmp_path / "dist", SITE)
    store = DirStore(tmp_path / "bucket")
    for key in ("wx/latest.json", "assets/globe/coast.json", "catalogue/stations.json"):
        store.put_bytes(key, b"keep", "application/json", "public, max-age=60")
    publish_site(store, dist)
    (dist / "us/new-york/new-york-city.html").unlink()
    assert publish_site(store, dist) == {"uploaded": 0, "unchanged": 5, "deleted": 1}
    keys = store.list_keys("")
    assert "us/new-york/new-york-city" not in keys
    for key in ("wx/latest.json", "assets/globe/coast.json", "catalogue/stations.json"):
        assert store.get_bytes(key) == b"keep"


def test_a_manifest_naming_data_keys_never_deletes_them(tmp_path):
    store = DirStore(tmp_path / "bucket")
    store.put_bytes("wx/latest.json", b"keep", "application/json", "public, max-age=60")
    store.put_bytes(MANIFEST, json.dumps({"wx/latest.json": "x", "old-page": "y"}).encode(), "application/json", "no-store")
    store.put_bytes("old-page", b"<h1>old</h1>", "text/html", "public, max-age=3600")
    publish_site(store, make_dist(tmp_path / "dist", {"wave-map.html": "x"}))
    assert store.get_bytes("wx/latest.json") == b"keep"
    assert store.get_bytes("old-page") is None


def test_cli_publish_site_and_get(tmp_path, capsys):
    dist = make_dist(tmp_path / "dist", {"wave-map.html": "x"})
    bucket = tmp_path / "bucket"
    assert main(["publish-site", "--dist", str(dist), "--store", f"dir:{bucket}"]) == 0
    assert "uploaded 1" in capsys.readouterr().out
    DirStore(bucket).put_bytes("catalogue/stations.json", b"[]", "application/json", "x")
    out = tmp_path / "stations.json"
    assert main(["get", "--key", "catalogue/stations.json", "--out", str(out), "--store", f"dir:{bucket}"]) == 0
    assert out.read_bytes() == b"[]"
    assert main(["get", "--key", "catalogue/missing.json", "--out", str(tmp_path / "m.json"), "--store", f"dir:{bucket}"]) == 3
    assert not (tmp_path / "m.json").exists()
