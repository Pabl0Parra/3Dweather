// The finder map: OpenStreetMap tiles under clustered station markers from catalogue/search.json.
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { loadCatalogue } from "../search/catalogue";
import { clusterPoints, wrapNear, type Point } from "./cluster";

export async function mountFinder(el: HTMLElement, status?: HTMLElement | null): Promise<void> {
  const map = L.map(el, { worldCopyJump: true, preferCanvas: true, minZoom: 2, maxZoom: 15 }).setView([30, 0], 2);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  const layer = L.layerGroup().addTo(map);

  let points: Point[] = [];
  try {
    points = (await loadCatalogue()).entries.map((e) => ({ lat: e.lat, lon: e.lon, name: e.name, path: e.path }));
  } catch {
    el.dataset.error = "1";
    if (status) status.textContent = "The map's place list could not be loaded. The country lists below still work.";
    return;
  }

  // Popups belong to the map, not to the markers: redrawing markers on every move would close them.
  const openStation = (ll: L.LatLng, name: string, path: string) => {
    const a = document.createElement("a");
    a.href = `/${path}`;
    a.textContent = name;
    L.popup({ autoPanPadding: [20, 20] }).setLatLng(ll).setContent(a).openOn(map);
  };

  const singles: { ll: L.LatLng; name: string; path: string }[] = [];
  const draw = () => {
    layer.clearLayers();
    singles.length = 0;
    const view = map.getBounds().pad(0.2);
    const z = map.getZoom();
    const center = map.getCenter().lng;
    for (const c of clusterPoints(points, z)) {
      const ll = L.latLng(c.lat, wrapNear(c.lon, center)); // drawn on the world copy in view
      if (!view.contains(ll)) continue;
      if (c.n === 1) {
        const m = L.circleMarker(ll, { radius: 6, color: "#021018", weight: 1, fillColor: "#3fe0ff", fillOpacity: 0.95 });
        m.on("click", () => openStation(ll, c.name!, c.path!));
        m.addTo(layer);
        singles.push({ ll, name: c.name!, path: c.path! });
      } else {
        const size = c.n < 10 ? 28 : c.n < 100 ? 34 : c.n < 1000 ? 40 : 46;
        const icon = L.divIcon({ className: "", html: `<div class="cluster" style="width:${size}px;height:${size}px">${c.n}</div>`,
          iconSize: [size, size] });
        L.marker(ll, { icon, title: `${c.n} places`, keyboard: true })
          .on("click", () => map.setView(ll, Math.min(map.getMaxZoom(), z + 2)))
          .addTo(layer);
      }
    }
    el.dataset.markers = String(layer.getLayers().length);
  };
  map.on("moveend", draw);
  draw();

  if (import.meta.env.DEV || new URLSearchParams(location.search).has("debug")) {
    (window as any).__finder = {
      map, singles: () => singles.length,
      openFirstSingle: () => { const s = singles[0]; if (s) openStation(s.ll, s.name, s.path); },
    };
  }
}
