# 3Dweather

An open-source, non-commercial weather globe: waves, wind, rain, temperature,
currents and tides on a 3D Earth, built from open forecast data. Scheduled jobs
turn each model run into static image files; the site reads those files and
needs no server.

Status: the globe has six layers (rain and cloud, wind, temperature, waves,
currents, tides), and 12 flat regional maps (`/weather-map/{region}` and
`/wind-map/{region}`) show wind, rain and cloud hour by hour for three days.
A catalogue of about 24,500 tide stations and coastal places (NOAA CO-OPS and
GeoNames) has a search box and one page per station. Every station has tide
constants (NOAA, NOAA offsets, a nearby NOAA station, or the EOT20 global model)
and a monthly 25-month table of high and low waters; sun, moon, solunar and
tidal-coefficient data come from JPL DE421. Station pages, rebuilt daily, show
the day's tide chart, the month's table, sun and moon, the weather forecast at
the station, other months and a CSV download.
Everything is built by GitHub Actions and published to Cloudflare R2.
The design is in `docs/superpowers/specs/`; publishing setup is in
[`docs/deploy.md`](docs/deploy.md).

## Data credits

Forecast data: NOAA GFS and GFS-Wave, ECMWF IFS (CC BY 4.0) and Mercator
(E.U. Copernicus Marine Service Information), as published by
[Open-Meteo.com](https://open-meteo.com) (CC BY 4.0). Tides: NOAA CO-OPS harmonic constants and
offsets (public domain; not NOAA's official predictions), EOT20 (Hart-Davis et
al. 2021, DGFI-TUM, CC BY 4.0) and, where the owner supplies it, FES2022 (funded
by CNES, produced by LEGOS, NOVELTIS and CLS, made freely available by AVISO).
Sun and moon: JPL DE421. Places: GeoNames (CC BY 4.0). Base map: Natural Earth and NASA
Black Marble (public domain).

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

Build the station catalogue (downloads the NOAA station list, GeoNames and the
Natural Earth coastline into the inputs folder on first use):

```
python -m pipeline catalogue --inputs catalogue-inputs --out web/public/catalogue
```

Tide constants and tables (`[tides]` extra; EOT20 is the 2.3 GB zip from
SEANOE, see `.github/workflows/static.yml`):

```
python -m pipeline model-constants --catalogue catalogue-out/stations.json --eot20 eot20/eot20.zip --out tide-out/models/eot20.json
python -m pipeline tide-constants --catalogue catalogue-out/stations.json --noaa catalogue-inputs/noaa-tidepredictions.json     --noaa-cache noaa-cache --model tide-out/models/eot20.json --out tide-out/tide-constants.json
python -m pipeline tide-tables --catalogue catalogue-out/stations.json --constants tide-out/tide-constants.json --out tide-out/tides
```

Sun and moon (`[sky]` extra) download JPL DE421 (17 MB) into `sky-cache/` on
first use (`SKY_CACHE` changes the folder). Station page data for today:

```
python -m pipeline station-data --catalogue catalogue-out/stations.json --constants tide-out/tide-constants.json --out web/station-data --sky-cache sky-cache --sky-store sky-months --workers 4
```

`npm run build` reads it from `web/station-data` (or `STATION_DATA_DIR`).

The site lives in `web/` (Astro): `npm ci`, `npm run dev`, `npx vitest run`,
`npx playwright test` (the end-to-end tests need a run built into
`web/public/wx`, the static assets in `web/public/assets/globe` and the
catalogue in `web/public/catalogue`; each spec skips without its data). With
the catalogue present, `npm run build` makes one page per station.

Tests marked `reference` compare the output with locally kept reference
material in `reference/` (not in the repository) and are skipped without it.
