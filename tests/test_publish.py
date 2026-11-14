import json
from datetime import datetime, timezone

import pytest

from pipeline.publish import (LATEST_CACHE, RUN_CACHE, DirStore, S3Store, prune_runs, publish_run, published_run,
                              upload_dir)

RUN = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)
BUILT = datetime(2026, 11, 13, 11, 40, tzinfo=timezone.utc)


def run_folder(tmp_path, name="2026111306"):
    d = tmp_path / "out" / name
    d.mkdir(parents=True)
    (d / "globe.json").write_text("{}")
    (d / "globe-w0.webp").write_bytes(b"RIFF")
    (d / "globe-c.webp").write_bytes(b"RIFF")
    return d


def test_publish_uploads_files_with_long_cache_then_latest(tmp_path):
    store = DirStore(tmp_path / "bucket")
    publish_run(store, run_folder(tmp_path), RUN, BUILT)
    assert sorted(store.list_keys("wx/2026111306/")) == [
        "wx/2026111306/globe-c.webp", "wx/2026111306/globe-w0.webp", "wx/2026111306/globe.json"]
    assert store.headers("wx/2026111306/globe-w0.webp") == {"content_type": "image/webp", "cache_control": RUN_CACHE}
    assert store.headers("wx/2026111306/globe.json")["content_type"] == "application/json"
    assert store.headers("wx/latest.json") == {"content_type": "application/json", "cache_control": LATEST_CACHE}
    assert json.loads(store.get_bytes("wx/latest.json")) == {
        "run": "2026-11-13T06:00Z", "dir": "2026111306", "built": "2026-11-13T11:40:00Z"}
    assert store.order[-1] == "wx/latest.json"
    assert RUN_CACHE == "public, max-age=2592000, immutable" and LATEST_CACHE == "public, max-age=60"


def test_failed_upload_leaves_the_old_latest(tmp_path):
    store = DirStore(tmp_path / "bucket")
    store.put_bytes("wx/latest.json", b'{"dir":"2026111300"}', "application/json", LATEST_CACHE)

    class Flaky(DirStore):
        def put_file(self, key, path, content_type, cache_control):
            if len(self.order) >= 2:
                raise OSError("network down")
            super().put_file(key, path, content_type, cache_control)

    flaky = Flaky(tmp_path / "bucket")
    with pytest.raises(OSError):
        publish_run(flaky, run_folder(tmp_path), RUN, BUILT)
    assert store.get_bytes("wx/latest.json") == b'{"dir":"2026111300"}'


def test_published_run(tmp_path):
    store = DirStore(tmp_path / "bucket")
    assert published_run(store) is None
    publish_run(store, run_folder(tmp_path), RUN, BUILT)
    assert published_run(store) == RUN


def test_prune_keeps_recent_published_and_foreign_keys(tmp_path):
    store = DirStore(tmp_path / "bucket")
    for run in ("2026110906", "2026111000", "2026111006", "2026111306"):
        store.put_bytes(f"wx/{run}/globe.json", b"{}", "application/json", RUN_CACHE)
        store.put_bytes(f"wx/{run}/globe-w0.webp", b"x", "image/webp", RUN_CACHE)
    store.put_bytes("wx/latest.json", b'{"run":"2026-11-09T06:00Z","dir":"2026110906"}', "application/json", LATEST_CACHE)
    store.put_bytes("wx/notes.txt", b"x", "text/plain", RUN_CACHE)
    store.put_bytes("assets/globe/coast.json", b"x", "application/json", RUN_CACHE)
    gone = prune_runs(store, keep_from=datetime(2026, 11, 10, 6, tzinfo=timezone.utc))
    assert gone == ["2026111000"]  # 2026110906 is still published, so it stays
    keys = store.list_keys("")
    assert not any(k.startswith("wx/2026111000/") for k in keys)
    for kept in ("wx/2026110906/globe.json", "wx/2026111006/globe.json", "wx/2026111306/globe.json",
                 "wx/latest.json", "wx/notes.txt", "assets/globe/coast.json"):
        assert kept in keys


def test_upload_dir(tmp_path):
    src = tmp_path / "static"
    src.mkdir()
    (src / "land-mask.png").write_bytes(b"png")
    (src / "coast.json").write_text("{}")
    store = DirStore(tmp_path / "bucket")
    upload_dir(store, src, "assets/globe", "public, max-age=604800")
    assert store.headers("assets/globe/land-mask.png") == {"content_type": "image/png",
                                                           "cache_control": "public, max-age=604800"}
    assert sorted(store.list_keys("assets/")) == ["assets/globe/coast.json", "assets/globe/land-mask.png"]


class FakeS3:
    def __init__(self):
        self.calls = []
        self.pages = [{"Contents": [{"Key": "wx/a"}], "IsTruncated": True, "NextContinuationToken": "t"},
                      {"Contents": [{"Key": "wx/b"}], "IsTruncated": False}]

    def upload_file(self, Filename, Bucket, Key, ExtraArgs):
        self.calls.append(("upload_file", Bucket, Key, ExtraArgs))

    def put_object(self, **kw):
        self.calls.append(("put_object", kw["Bucket"], kw["Key"], kw["ContentType"], kw["CacheControl"]))

    def list_objects_v2(self, **kw):
        self.calls.append(("list", kw.get("ContinuationToken")))
        return self.pages.pop(0)

    def delete_objects(self, Bucket, Delete):
        self.calls.append(("delete", Bucket, [o["Key"] for o in Delete["Objects"]]))


def test_s3_store_calls(tmp_path):
    s3 = FakeS3()
    store = S3Store(s3, "wx-bucket")
    f = tmp_path / "f.webp"
    f.write_bytes(b"x")
    store.put_file("wx/r/f.webp", f, "image/webp", RUN_CACHE)
    store.put_bytes("wx/latest.json", b"{}", "application/json", LATEST_CACHE)
    assert store.list_keys("wx/") == ["wx/a", "wx/b"]
    store.delete_keys([f"k{i}" for i in range(1500)])
    assert s3.calls[0] == ("upload_file", "wx-bucket", "wx/r/f.webp",
                           {"ContentType": "image/webp", "CacheControl": RUN_CACHE})
    assert s3.calls[1] == ("put_object", "wx-bucket", "wx/latest.json", "application/json", LATEST_CACHE)
    assert [c[1] for c in s3.calls if c[0] == "list"] == [None, "t"]
    deletes = [c for c in s3.calls if c[0] == "delete"]
    assert [len(d[2]) for d in deletes] == [1000, 500]  # S3 caps a delete batch at 1000 keys
