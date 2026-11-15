// The finder map: OpenStreetMap tiles under clustered station markers from catalogue/search.json.
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { loadCatalogue } from "../search/catalogue";
import { clusterPoints, type Point } from "./cluster";

export async function mountFinder(el: HTMLElement): Promise<void> {
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
    return;
  }

  const draw = () => {
    layer.clearLayers();
    const view = map.getBounds().pad(0.2);
    const z = map.getZoom();
    for (const c of clusterPoints(points, z)) {
      const ll = L.latLng(c.lat, c.lon);
      if (!view.contains(ll) && !view.contains(L.latLng(c.lat, c.lon + 360)) && !view.contains(L.latLng(c.lat, c.lon - 360))) continue;
      if (c.n === 1) {
        const m = L.circleMarker(ll, { radius: 6, color: "#021018", weight: 1, fillColor: "#3fe0ff", fillOpacity: 0.95 });
        const a = document.createElement("a");
        a.href = `/${c.path}`;
        a.textContent = c.name!;
        m.bindPopup(a);
        m.addTo(layer);
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
}
