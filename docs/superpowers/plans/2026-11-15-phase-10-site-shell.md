# Phase 10: Site Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Everything around the station pages: a home page, country and region browse pages, a finder map, guides and static pages, and SEO (canonical URLs, JSON-LD, sitemaps, robots.txt).

**Architecture:** All pages are static Astro pages built from the catalogue files (`stations.json`, `countries.json`, `search.json`) at build time, sharing one layout. The finder map is a Leaflet map on OpenStreetMap tiles with our own grid clustering over `search.json`. Sitemaps and robots.txt are Astro endpoints. Written content is fresh (spec header: "written fresh and templated per station").

**Tech Stack:** Astro 7, TypeScript, Vitest, Playwright, Leaflet 1.9.4 (BSD-2), OpenStreetMap tiles (ODbL, attribution).

**Spec:** `docs/superpowers/specs/2026-11-14-same-sources-data-design.md` (§10 item 10; page list in `docs/wave-map-findings-and-plan.md` §10 "Page types").

## Global Constraints

- No server, no API: everything is a static file in R2; search and "near me" run in the browser over `catalogue/search.json`.
- Not scheduled (spec §10): accounts, synced favourites, alert e-mails. No login/register pages.
- Written content is our own; nothing copied from the reference site. Finder tiles: OpenStreetMap, credited "© OpenStreetMap contributors".
- Pages build as `a/b.html` (`build.format: "file"`); the publisher stores them as `a/b`.
- Site URL from `SITE_URL` (no domain yet; default `https://example.invalid` makes canonical links obviously unset in local builds).
- Pages must work at 320 px width with no horizontal scroll.

## Review Focus

1. **A country with one region or a region with one station**: pages still read naturally, no empty sections.
2. **Catalogue missing at build** (forks, CI without secrets): home, guides and the finder still build; country/region pages simply don't exist.
3. **Sitemap size limits**: 50,000 URLs per file; the stations sitemap is split.
4. **Station names with quotes, ampersands or non-Latin letters** in JSON-LD and titles: escaped, valid JSON.
5. **Finder with 24,500 markers**: clustering keeps the map responsive; clicking a cluster zooms in.

---

### Task 1: Browse data and the site layout

**Files:** Create `web/src/stations/browse.ts`, `web/src/stations/browse.test.ts`, `web/src/components/SiteLayout.astro`, `web/src/styles/site.css`.

**Interfaces — Produces:**
- `loadCountries(dir?) -> Country[]` (`countries.json`: `{cc, name, continent, count, regions: [{slug, name, count}]}`), `loadRanks(dir?) -> Map<path, rank>` (from `search.json`), `catalogueDir()` (dirname of `CATALOGUE_FILE`, default `public/catalogue`).
- `browseTree(stations, countries, ranks) -> Country & {regions: (Region & {stations: StationRecord[]})[]}[]` with stations sorted by name and `popular(list, ranks, n)` by rank then gauge first then name.
- `CONTINENTS` (code → name), `continentOf(countries, cc)`.
- `SiteLayout.astro` props `{title, description, path, jsonld?: object[]}`: head (title, description, canonical, OpenGraph, JSON-LD scripts escaped), header (brand, nav: Tides `/stations`, Globe `/wave-map`, Guides `/guides`, search), footer (About, Privacy, Terms, Guides, credits).

- [ ] Step 1: failing tests: tree groups by country and region and sorts; popular order; missing files → `[]`/empty map.
- [ ] Step 2–4: implement; pass.
- [ ] Step 5: commit `feat: browse data and site layout`.

### Task 2: Home, country and region pages

**Files:** Create `web/src/pages/index.astro`, `web/src/pages/[cc].astro`, `web/src/pages/[cc]/[region].astro`, `web/src/home/near.ts` (+ test); modify the station page breadcrumb to link country and region; e2e `web/tests/e2e/browse.spec.ts`.

- Home: hero with a search box, "Tides near you" (button → geolocation → 8 nearest from `search.json`, `nearest()`), popular stations (top 12 by rank), countries by continent (tabs as `<details>`), links to the globe layers and regional maps.
- Country `/{cc}`: region cards (name, count) with a filter box, popular spots (8), link to the country's regional weather map when one exists.
- Region `/{cc}/{region}`: popular spots, all places alphabetically (gauges marked), filter box.
- [ ] Step 1: failing tests: `near.ts` formats nearest results; e2e: home lists continents and popular stations; `/us` lists regions incl. New York; `/us/new-york` lists New York City and links to it; station breadcrumb links back.
- [ ] Step 2–4: implement; pass.
- [ ] Step 5: commit `feat: home, country and region pages`.

### Task 3: Finder map

**Files:** Create `web/src/pages/stations.astro`, `web/src/finder/cluster.ts` (+ test), `web/src/finder/map.ts`; add `leaflet@1.9.4`.

- `clusterPoints(points, zoom, cellPx=60) -> {lat, lon, n, path?, name?}[]` (Web-Mercator pixel grid at the zoom; single points keep path/name).
- Page: countries by continent with counts (static list) + map; markers redrawn on `moveend` from the clusters inside the view; a cluster click zooms in two levels on it; a single station opens a popup linking to its page. OSM attribution.
- [ ] Step 1: failing tests: points in one cell merge with the mean position; far points stay apart; counts sum; e2e: map container and attribution visible, list links to `/us`.
- [ ] Step 2–4: implement; pass.
- [ ] Step 5: commit `feat: station finder map`.

### Task 4: Guides and static pages

**Files:** Create `web/src/pages/guides.astro`, `what-is-a-tide.astro`, `tidal-coefficient.astro`, `solunar-times.astro`, `about.astro`, `privacy.astro`, `terms.astro`; e2e smoke.

- Fresh text. About: sources and licences (the data-credits list), open source repo link, "not NOAA's official predictions". Privacy: no accounts, no cookies; unit choice in local storage; geolocation only on request, never sent. Terms: data licences, no warranty, not for navigation.
- [ ] Step 1: failing e2e: each page has its h1 and appears in the footer or guides index.
- [ ] Step 2–4: implement; pass.
- [ ] Step 5: commit `feat: guides, about, privacy and terms`.

### Task 5: SEO and workflow

**Files:** Create `web/src/seo/jsonld.ts` (+ test), `web/src/pages/sitemap.xml.ts`, `web/src/pages/sitemaps/[name].xml.ts`, `web/src/pages/robots.txt.ts`; modify station/country/region pages (BreadcrumbList; station FAQPage), `astro.config.mjs` (`site` from `SITE_URL`), `.github/workflows/site.yml` (download `countries.json` and `search.json`; `SITE_URL: ${{ vars.SITE_URL }}`), `tests/test_workflows.py`, `docs/deploy.md`, README, spec §9.

- `breadcrumbs(site, items) -> object`, `stationFaq(name, where, source|null) -> object`, `jsonScript(obj) -> string` (escapes `<`, `>`, `&`, U+2028/9).
- Sitemaps: `sitemap.xml` index → `sitemaps/pages.xml` (home, guides, static, finder, globe layers, regional maps), `sitemaps/places.xml` (countries, regions), `sitemaps/stations-{k}.xml` (≤ 40,000 each).
- [ ] Step 1: failing tests: JSON-LD escaping of `</script>` and quotes; sitemap chunking; workflow test (downloads, `SITE_URL`).
- [ ] Step 2–4: implement; pass; full build count.
- [ ] Step 5: commit `feat: sitemaps, JSON-LD and canonical links`.
