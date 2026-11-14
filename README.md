# 3Dweather

An open-source, non-commercial weather globe: waves, wind, rain, temperature,
currents and tides on a 3D Earth, built from open forecast data. Scheduled jobs
turn each model run into static image files; the site reads those files and
needs no server.

Status: phase 1, the Python pipeline that builds the wave layer. The design is
in `docs/superpowers/specs/`.

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

Build the wave sprites for one model run:

```
python -m pipeline build --run 2026111306 --cache <cache dir> --out <output dir>
```

Tests marked `reference` compare the output with locally kept reference
material in `reference/` (not in the repository) and are skipped without it.
