"""Command line.

python -m pipeline build --run YYYYMMDDHH --cache DIR --out DIR [--latest] [--prune]
python -m pipeline static --cache DIR --out DIR
python -m pipeline cycle --cache DIR --out DIR --store (r2|dir:PATH) [--run YYYYMMDDHH]
python -m pipeline upload --src DIR --prefix KEY --max-age SECONDS --store (r2|dir:PATH)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import cycle as cycle_mod
from .build import build_run, write_latest
from .publish import store_from_arg, upload_dir
from .sources.openmeteo import RunIncomplete
from .static_assets import build_static


def _run_time(text: str) -> datetime:
    try:
        return datetime.strptime(text, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    except ValueError:
        raise argparse.ArgumentTypeError(f"run must look like 2026111306, got {text!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build every globe sprite and the manifest for one model run")
    build.add_argument("--run", required=True, type=_run_time, help="model run time, YYYYMMDDHH (UTC)")
    build.add_argument("--cache", required=True, type=Path, help="folder for downloaded inputs")
    build.add_argument("--out", required=True, type=Path, help="folder to write the run into")
    build.add_argument("--latest", action="store_true", help="also point latest.json at this run")
    build.add_argument("--prune", action="store_true",
                       help="delete each downloaded input once used (CI: a run needs ~16 GB otherwise)")
    static = sub.add_parser("static", help="build the land mask and coastline from Natural Earth")
    static.add_argument("--cache", required=True, type=Path, help="folder for downloaded Natural Earth files")
    static.add_argument("--out", required=True, type=Path, help="folder to write land-mask.png and coast.json")
    cyc = sub.add_parser("cycle", help="scheduled job: build the due run, publish it, prune old runs")
    cyc.add_argument("--cache", required=True, type=Path)
    cyc.add_argument("--out", required=True, type=Path)
    cyc.add_argument("--store", required=True, help="r2 (credentials from the environment) or dir:PATH")
    cyc.add_argument("--run", type=_run_time, help="build this run instead of the one due now")
    up = sub.add_parser("upload", help="upload a folder (static assets) to the store")
    up.add_argument("--src", required=True, type=Path)
    up.add_argument("--prefix", required=True)
    up.add_argument("--max-age", required=True, type=int)
    up.add_argument("--store", required=True)
    args = parser.parse_args(argv)

    if args.command == "cycle":
        return cycle_mod.cycle(datetime.now(timezone.utc), args.cache, args.out, store_from_arg(args.store),
                               run=args.run, build=cycle_mod.build_run)
    if args.command == "upload":
        for key in upload_dir(store_from_arg(args.store), args.src, args.prefix, f"public, max-age={args.max_age}"):
            print(key)
        return 0

    if args.command == "static":
        build_static(args.cache, args.out)
        print(args.out)
        return 0
    try:
        out = build_run(args.run, args.cache, args.out, prune=args.prune)
    except RunIncomplete as exc:
        print(f"not built: {exc}", file=sys.stderr)
        return 2
    if args.latest:
        write_latest(args.out, args.run, datetime.now(timezone.utc))
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
