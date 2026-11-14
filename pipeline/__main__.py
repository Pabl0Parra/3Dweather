"""Command line.

python -m pipeline build --run YYYYMMDDHH --cache DIR --out DIR [--latest] [--prune]
python -m pipeline static --cache DIR --out DIR
python -m pipeline cycle --cache DIR --out DIR --store (r2|dir:PATH) [--run YYYYMMDDHH]
python -m pipeline upload --src DIR --prefix KEY --max-age SECONDS --store (r2|dir:PATH)
python -m pipeline tide-atlas --eot20 ZIP_OR_DIR --out DIR
python -m pipeline catalogue --inputs DIR --out DIR
python -m pipeline publish-site --dist DIR --store (r2|dir:PATH)
python -m pipeline get --key KEY --out FILE --store (r2|dir:PATH)
python -m pipeline model-constants --catalogue STATIONS_JSON --eot20 ZIP_OR_DIR --out FILE
python -m pipeline tide-constants --catalogue STATIONS_JSON --noaa NOAA_LIST --noaa-cache DIR
                                  --model FILE [--model FILE ...] --out FILE

Stores: r2 (bucket R2_BUCKET), r2:BUCKET (another bucket, same account) or dir:PATH.
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
    tide = sub.add_parser("tide-atlas", help="build tide.png and tide.json from EOT20")
    tide.add_argument("--eot20", required=True, type=Path, help="the downloaded EOT20 zip, or a folder of *_ocean_eot20.nc")
    tide.add_argument("--out", required=True, type=Path)
    cat = sub.add_parser("catalogue", help="build stations.json, search.json and countries.json")
    cat.add_argument("--inputs", required=True, type=Path, help="folder for the NOAA, GeoNames and coastline inputs")
    cat.add_argument("--out", required=True, type=Path)
    site = sub.add_parser("publish-site", help="upload the built web site to the bucket root (changed files only)")
    site.add_argument("--dist", required=True, type=Path)
    site.add_argument("--store", required=True)
    site.add_argument("--allow-mass-delete", action="store_true",
                      help="allow deleting more than 10%% of the published site (normally a sign of a broken build)")
    get = sub.add_parser("get", help="download one key from the store (exit 3 when it does not exist)")
    get.add_argument("--key", required=True)
    get.add_argument("--out", required=True, type=Path)
    get.add_argument("--store", required=True)
    mc = sub.add_parser("model-constants", help="sample EOT20 at every catalogue station")
    mc.add_argument("--catalogue", required=True, type=Path, help="stations.json")
    mc.add_argument("--eot20", required=True, type=Path, help="the downloaded EOT20 zip, or a folder of *_ocean_eot20.nc")
    mc.add_argument("--out", required=True, type=Path)
    tc = sub.add_parser("tide-constants", help="one tide-constants entry per station (NOAA, offsets, donors, models)")
    tc.add_argument("--catalogue", required=True, type=Path, help="stations.json")
    tc.add_argument("--noaa", required=True, type=Path, help="NOAA's tide-prediction station list (catalogue input)")
    tc.add_argument("--noaa-cache", required=True, type=Path, help="folder caching NOAA's per-station responses")
    tc.add_argument("--model", action="append", default=[], type=Path,
                    help="model constants file; the first with constants wins per station; missing files are skipped")
    tc.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    if args.command == "model-constants":
        import json
        from .tide_constants import write_model_file
        from .tide_model import ModelReader, sample_model
        records = json.loads(args.catalogue.read_text(encoding="utf-8"))
        reader = ModelReader.eot20(args.eot20)
        samples = sample_model(records, reader)
        write_model_file(args.out, reader.label, samples)
        print(f"{sum(v is not None for v in samples.values())} of {len(samples)} stations sampled -> {args.out}")
        return 0
    if args.command == "tide-constants":
        import json
        from collections import Counter
        from . import tide_constants as tcm
        records = json.loads(args.catalogue.read_text(encoding="utf-8"))
        models = [tcm.read_model(p) for p in args.model if p.exists()]
        noaa = tcm.fetch_noaa(tcm.noaa_stations(args.noaa), args.noaa_cache)
        out = tcm.build_constants(records, noaa, models)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
        kinds = Counter(e["kind"] for e in out["stations"].values())
        print(", ".join(f"{k} {n}" for k, n in sorted(kinds.items())) + f" -> {args.out}")
        return 0

    if args.command == "publish-site":
        from .site import publish_site
        r = publish_site(store_from_arg(args.store), args.dist, allow_mass_delete=args.allow_mass_delete)
        print(f"uploaded {r['uploaded']}, unchanged {r['unchanged']}, deleted {r['deleted']}")
        return 0
    if args.command == "get":
        data = store_from_arg(args.store).get_bytes(args.key)
        if data is None:
            print(f"{args.key}: not in the store", file=sys.stderr)
            return 3
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(data)
        print(args.out)
        return 0

    if args.command == "catalogue":
        from .catalogue import build_catalogue, fetch_inputs, write_catalogue
        records = build_catalogue(args.inputs, fetch_inputs(args.inputs))
        write_catalogue(records, args.inputs, args.out)
        gauges = sum(r["type"] == "gauge" for r in records)
        print(f"{len(records)} stations ({gauges} gauges) in {len({r['country_code'] for r in records})} countries -> {args.out}")
        return 0

    if args.command == "tide-atlas":
        from .tide_atlas import build_tide_atlas
        build_tide_atlas(args.eot20, args.out)
        print(args.out)
        return 0

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
