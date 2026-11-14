"""Sample FES2022 at every catalogue station, on the owner's machine.

FES2022 (CNES, LEGOS, NOVELTIS, CLS; distributed by AVISO under its own licence) never
enters the repository or a runner, and the constants sampled from it stay in a private
bucket. Download the ocean-tide netCDF files from AVISO+ into one folder
(``m2_fes2022.nc``, ``k1_fes2022.nc``, ...), then:

    python tools/fes2022_constants.py --catalogue stations.json --fes FOLDER --out fes/model-constants.json
    python -m pipeline upload --src fes --prefix fes2022 --max-age 0 --store r2:PRIVATE_BUCKET

The output has the same format as ``python -m pipeline model-constants`` (EOT20). The
Static assets workflow prefers it, station by station, when it finds
``fes2022/model-constants.json`` in the private bucket (see docs/deploy.md).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.tide_constants import write_model_file  # noqa: E402
from pipeline.tide_model import FES2022_NAMES, ModelReader, sample_model  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sample FES2022 at every catalogue station.")
    ap.add_argument("--catalogue", required=True, type=Path, help="stations.json")
    ap.add_argument("--fes", required=True, type=Path, help="folder of <name>_fes2022.nc files")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    names = [n for n in FES2022_NAMES if (args.fes / f"{n}_fes2022.nc").exists()]
    if "m2" not in names:
        ap.error(f"no m2_fes2022.nc in {args.fes}")
    records = json.loads(args.catalogue.read_text(encoding="utf-8"))
    reader = ModelReader.fes2022(args.fes, names)
    samples = sample_model(records, reader)
    write_model_file(args.out, reader.label, samples)
    have = sum(v is not None for v in samples.values())
    print(f"{len(names)} constituents, {have} of {len(samples)} stations -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
