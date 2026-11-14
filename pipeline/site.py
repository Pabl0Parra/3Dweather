"""Publishes the built web site (web/dist) to the bucket root.

Astro builds pages as ``a/b.html`` (``build.format: "file"``); each is stored under ``a/b``
with an HTML content type, so ``/a/b`` is served straight from R2 with no routing rule.
Only files whose MD5 changed since the last publish go up. ``site-manifest.json`` records
what was published (key -> MD5), so pages that left the build are deleted and nothing
else in the bucket (``wx/``, ``assets/``, ``catalogue/``) is ever touched.

Two guards: a publish that would delete more than ``MAX_DELETE_SHARE`` of the site stops
(a build that lost its catalogue must not wipe 24,000 station pages), and retired
``_astro/`` scripts stay for ``KEEP_ASSETS`` so pages cached for an hour still load them.
"""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .publish import Store, content_type

MANIFEST = "site-manifest.json"
PROTECTED = ("wx/", "assets/", "catalogue/")  # data the jobs own, even when web/public copies it into dist
PAGE_CACHE = "public, max-age=3600"
ASSET_CACHE = "public, max-age=31536000, immutable"  # Astro fingerprints everything under _astro/
KEEP_NAMES = {"index.html", "404.html"}
MAX_DELETE_SHARE = 0.10
MAX_DELETE_ANYWAY = 50  # small deletions always pass; the share guards a 24,000-page site
KEEP_ASSETS = timedelta(days=2)


class MassDelete(RuntimeError):
    """The new build would delete most of the published site."""


_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json", ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml", ".ico": "image/x-icon", ".woff2": "font/woff2", ".webp": "image/webp", ".png": "image/png",
}


def site_key(rel: str) -> str:
    name = rel.rsplit("/", 1)[-1]
    if rel.endswith(".html") and name not in KEEP_NAMES:
        return rel[: -len(".html")]
    return rel


def site_content_type(rel: str) -> str:
    suffix = Path(rel).suffix.lower()
    return _TYPES.get(suffix) or content_type(Path(rel))


def site_cache_control(key: str) -> str:
    return ASSET_CACHE if key.startswith("_astro/") else PAGE_CACHE


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _read_manifest(raw: bytes | None) -> tuple[dict[str, str], dict[str, str]]:
    """(published key -> md5, retired asset key -> when it left the build). Reads the first, flat format too."""
    if not raw:
        return {}, {}
    data = json.loads(raw)
    if "files" in data and isinstance(data["files"], dict):
        return data["files"], data.get("retired", {})
    return data, {}


def publish_site(store: Store, dist: Path, workers: int = 16, allow_mass_delete: bool = False,
                 now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    dist = Path(dist)
    files: dict[str, tuple[Path, str]] = {}  # key -> (file, path relative to dist)
    for p in sorted(dist.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(dist).as_posix()
        if rel.startswith(PROTECTED) or rel == MANIFEST:
            continue
        files[site_key(rel)] = (p, rel)

    old, retired = _read_manifest(store.get_bytes(MANIFEST))
    new = {key: _md5(p) for key, (p, _) in files.items()}
    changed = [k for k in new if old.get(k) != new[k]]

    # Pages that left the build go now; retired scripts wait until no cached page can want them.
    retired = {k: when for k, when in retired.items() if k not in new}
    for k in old:
        if k not in new and k.startswith("_astro/"):
            retired.setdefault(k, now.isoformat())
    gone = sorted(k for k in old if k not in new and not k.startswith(("_astro/", *PROTECTED)) and k != MANIFEST)
    gone += sorted(k for k, when in retired.items() if now - datetime.fromisoformat(when) >= KEEP_ASSETS)
    pages_gone = [k for k in gone if not k.startswith("_astro/")]
    if len(pages_gone) > max(MAX_DELETE_ANYWAY, MAX_DELETE_SHARE * len(old)) and not allow_mass_delete:
        raise MassDelete(f"refusing to delete {len(pages_gone)} of {len(old)} published files "
                         f"(more than {MAX_DELETE_SHARE:.0%}); did the build lose its catalogue? "
                         "Pass --allow-mass-delete if this is intended.")

    def put(key: str) -> None:
        p, rel = files[key]
        store.put_file(key, p, site_content_type(rel), site_cache_control(key))

    # Scripts and styles before the pages that load them.
    pages = {k for k in changed if files[k][1].endswith(".html")}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(put, [k for k in changed if k not in pages]))
        list(pool.map(put, sorted(pages)))

    if gone:
        store.delete_keys(gone)
    retired = {k: when for k, when in retired.items() if k not in gone}
    # Retired scripts stay in the manifest's published list until they are deleted.
    published = {**{k: old[k] for k in retired if k in old}, **new}
    if changed or gone or published != old:
        body = {"files": published, "retired": retired}
        store.put_bytes(MANIFEST, json.dumps(body, sort_keys=True).encode("utf-8"), "application/json", "no-store")
    return {"uploaded": len(changed), "unchanged": len(new) - len(changed), "deleted": len(gone)}
