# 3Dweather

An open-source, non-commercial weather globe: waves, wind, rain, temperature,
currents and tides on a 3D Earth, built from open forecast data. Scheduled jobs
turn each model run into static image files; the site reads those files and
needs no server.

Status: the globe has five layers (rain and cloud, wind, temperature, waves,
currents), built every 6 hours by GitHub Actions and published to Cloudflare R2.
The design is in `docs/superpowers/specs/`; publishing setup is in
[`docs/deploy.md`](docs/deploy.md).

## Data credits

Forecast data: NOAA GFS and GFS-Wave, ECMWF IFS (CC BY 4.0) and Mercator
(E.U. Copernicus Marine Service Information), as published by
[Open-Meteo.com](https://open-meteo.com) (CC BY 4.0). Tides: FES2022, funded by
CNES, produced by LEGOS, NOVELTIS and CLS, made freely available by AVISO, and
NOAA CO-OPS harmonic constants (public domain; not NOAA's official
predictions). Base map: Natural Earth and NASA Black Marble (public domain).

## Development

```
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m pytest
```

Build every globe layer for one model run:

```
python -m pipeline build --run 2026111306 --cache <cache dir> --out <output dir>
```

Inputs are downloaded into `<cache dir>/<run>/`, so one cache folder can serve
many runs. Add `--prune` to delete each input once used (a run needs about
16 GB otherwise). Exit code 2 means the run is not fully published yet; try
again later.

The scheduled job runs `python -m pipeline cycle`, which picks the run that is
due, waits for its inputs, builds, uploads and prunes (see `docs/deploy.md`).

The site lives in `web/` (Astro): `npm ci`, `npm run dev`, `npx vitest run`,
`npx playwright test` (the end-to-end tests need a run built into
`web/public/wx` and the static assets in `web/public/assets/globe`).

Tests marked `reference` compare the output with locally kept reference
material in `reference/` (not in the repository) and are skipped without it.
