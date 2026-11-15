// "Tides near you" on the home page: the browser's position (asked only on a click, never sent
// anywhere) against the catalogue's search file.
import { loadCatalogue, nearest, type Entry } from "../search/catalogue";

export type NearItem = { name: string; href: string; detail: string };

export function nearItems(list: (Entry & { km: number })[]): NearItem[] {
  return list.map((e) => ({
    name: e.name, href: `/${e.path}`, detail: `${e.region} · ${e.km < 10 ? e.km.toFixed(1) : Math.round(e.km)} km`,
  }));
}

export function mountNear(button: HTMLButtonElement, list: HTMLElement, status: HTMLElement): void {
  button.addEventListener("click", () => {
    if (!("geolocation" in navigator)) { status.textContent = "Your browser cannot share its location."; return; }
    status.textContent = "Finding you…";
    navigator.geolocation.getCurrentPosition(async (pos) => {
      try {
        const cat = await loadCatalogue();
        const items = nearItems(nearest(cat, pos.coords.latitude, pos.coords.longitude, 8));
        list.replaceChildren(...items.map((it) => {
          const li = document.createElement("li");
          const a = document.createElement("a");
          a.href = it.href;
          a.textContent = it.name;
          const small = document.createElement("small");
          small.textContent = it.detail;
          a.append(small);
          li.append(a);
          return li;
        }));
        status.textContent = "";
      } catch {
        status.textContent = "The place list could not be loaded. Try the search box instead.";
      }
    }, () => { status.textContent = "Location not shared. Try the search box instead."; }, { timeout: 15000, maximumAge: 600000 });
  });
}
