"""Command line: python -m pipeline build --run YYYYMMDDHH --cache DIR --out DIR"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .build import build_waves
from .sources.openmeteo import RunIncomplete


def _run_time(text: str) -> datetime:
    try:
        return datetime.strptime(text, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    except ValueError:
        raise argparse.ArgumentTypeError(f"run must look like 2026111306, got {text!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build the wave sprites and manifest for one model run")
    build.add_argument("--run", required=True, type=_run_time, help="model run time, YYYYMMDDHH (UTC)")
    build.add_argument("--cache", required=True, type=Path, help="folder for downloaded inputs")
    build.add_argument("--out", required=True, type=Path, help="folder to write the run into")
    args = parser.parse_args(argv)
    try:
        out = build_waves(args.run, args.cache, args.out)
    except RunIncomplete as exc:
        print(f"not built: {exc}", file=sys.stderr)
        return 2
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
