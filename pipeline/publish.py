"""Publishes built runs to object storage (Cloudflare R2 through its S3 API).

Layout (spec §5, §7): wx/{YYYYMMDDHH}/... per run, wx/latest.json written last,
static globe assets under assets/globe/.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

RUN_CACHE = "public, max-age=2592000, immutable"  # a run's files never change
LATEST_CACHE = "public, max-age=60"
STATIC_CACHE = "public, max-age=604800"
_RUN_DIR = re.compile(r"^wx/(\d{10})/")
_TYPES = {".webp": "image/webp", ".json": "application/json", ".png": "image/png"}


def content_type(path: Path) -> str:
    return _TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class Store(Protocol):
    def put_file(self, key: str, path: Path, content_type: str, cache_control: str) -> None: ...
    def put_bytes(self, key: str, data: bytes, content_type: str, cache_control: str) -> None: ...
    def get_bytes(self, key: str) -> bytes | None: ...
    def list_keys(self, prefix: str) -> list[str]: ...
    def delete_keys(self, keys: list[str]) -> None: ...


class DirStore:
    """A local folder standing in for a bucket (tests, dry runs). Headers go to a sidecar."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.order: list[str] = []  # keys in the order they were written

    def _path(self, key: str) -> Path:
        return self.root / key

    def _meta(self, key: str) -> Path:
        return self.root / ".meta" / (key + ".json")

    def _write_meta(self, key: str, content_type: str, cache_control: str) -> None:
        m = self._meta(key)
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text(json.dumps({"content_type": content_type, "cache_control": cache_control}))
        self.order.append(key)

    def put_file(self, key, path, content_type, cache_control):
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        self._write_meta(key, content_type, cache_control)

    def put_bytes(self, key, data, content_type, cache_control):
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        part.write_bytes(data)
        part.replace(dest)
        self._write_meta(key, content_type, cache_control)

    def get_bytes(self, key):
        p = self._path(key)
        return p.read_bytes() if p.is_file() else None

    def headers(self, key: str) -> dict:
        return json.loads(self._meta(key).read_text())

    def list_keys(self, prefix):
        if not self.root.exists():
            return []
        keys = (p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        return sorted(k for k in keys if not k.startswith(".meta/") and k.startswith(prefix))

    def delete_keys(self, keys):
        for k in keys:
            self._path(k).unlink(missing_ok=True)
            self._meta(k).unlink(missing_ok=True)


class S3Store:
    """A bucket behind the S3 API; `client` is a boto3 S3 client."""

    def __init__(self, client, bucket: str):
        self.client, self.bucket = client, bucket

    def put_file(self, key, path, content_type, cache_control):
        self.client.upload_file(Filename=str(path), Bucket=self.bucket, Key=key,
                                ExtraArgs={"ContentType": content_type, "CacheControl": cache_control})

    def put_bytes(self, key, data, content_type, cache_control):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                               CacheControl=cache_control)

    def get_bytes(self, key):
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.client.exceptions.NoSuchKey:
            return None

    def list_keys(self, prefix):
        keys, token = [], None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                kw["ContinuationToken"] = token
            page = self.client.list_objects_v2(**kw)
            keys += [o["Key"] for o in page.get("Contents", [])]
            if not page.get("IsTruncated"):
                return keys
            token = page["NextContinuationToken"]

    def delete_keys(self, keys):
        for i in range(0, len(keys), 1000):  # S3 caps a batch at 1000 keys
            self.client.delete_objects(Bucket=self.bucket,
                                       Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]], "Quiet": True})


R2_ENV = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")


def s3_store_from_env() -> S3Store:
    """R2 from the four GitHub Actions secrets (see docs/deploy.md)."""
    missing = [k for k in R2_ENV if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"missing environment variables: {', '.join(missing)}")
    import boto3  # optional dependency: pip install -e ".[publish]"
    from botocore.config import Config
    client = boto3.client(
        "s3", endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(retries={"max_attempts": 8, "mode": "standard"},
                      request_checksum_calculation="when_required", response_checksum_validation="when_required"))
    return S3Store(client, os.environ["R2_BUCKET"])


def store_from_arg(arg: str) -> Store:
    """`r2` (from the environment) or `dir:PATH`."""
    if arg == "r2":
        return s3_store_from_env()
    if arg.startswith("dir:"):
        return DirStore(Path(arg[4:]))
    raise ValueError(f"--store must be r2 or dir:PATH, got {arg!r}")


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%MZ")


def publish_run(store: Store, run_dir: Path, run: datetime, built: datetime) -> None:
    """Upload a complete run folder, then point wx/latest.json at it. If any upload
    fails, latest.json still names the previous run."""
    prefix = f"wx/{run:%Y%m%d%H}/"
    files = sorted(p for p in Path(run_dir).iterdir() if p.is_file())
    if not any(p.name == "globe.json" for p in files):
        raise RuntimeError(f"{run_dir} has no globe.json: not a complete run")
    for p in files:
        store.put_file(prefix + p.name, p, content_type(p), RUN_CACHE)
    latest = {"run": _iso(run), "dir": f"{run:%Y%m%d%H}", "built": built.strftime("%Y-%m-%dT%H:%M:%SZ")}
    store.put_bytes("wx/latest.json", json.dumps(latest, separators=(",", ":")).encode(), "application/json",
                    LATEST_CACHE)


def published_run(store: Store) -> datetime | None:
    data = store.get_bytes("wx/latest.json")
    if not data:
        return None
    try:
        return datetime.strptime(json.loads(data)["dir"], "%Y%m%d%H").replace(tzinfo=timezone.utc)
    except (ValueError, KeyError):
        return None


def prune_runs(store: Store, keep_from: datetime) -> list[str]:
    """Delete wx/<run>/ folders older than keep_from, never the published one. Returns the deleted run dirs."""
    current = published_run(store)
    by_run: dict[str, list[str]] = {}
    for key in store.list_keys("wx/"):
        m = _RUN_DIR.match(key)
        if m:
            by_run.setdefault(m.group(1), []).append(key)
    gone = []
    for run_dir, keys in sorted(by_run.items()):
        t = datetime.strptime(run_dir, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        if t < keep_from and t != current:
            store.delete_keys(keys)
            gone.append(run_dir)
    return gone


def upload_dir(store: Store, src: Path, prefix: str, cache_control: str) -> list[str]:
    keys = []
    for p in sorted(Path(src).rglob("*")):
        if p.is_file():
            key = f"{prefix.rstrip('/')}/{p.relative_to(src).as_posix()}"
            store.put_file(key, p, content_type(p), cache_control)
            keys.append(key)
    return keys
