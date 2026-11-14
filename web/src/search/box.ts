// Header search box: WAI-ARIA combobox over the browser-side catalogue.
import { loadCatalogue, search, type Catalogue, type Entry } from "./catalogue";

const DEBOUNCE_MS = 80;

export function mountSearchBox(root: HTMLElement): void {
  const button = root.querySelector<HTMLButtonElement>(".search-button")!;
  const panel = root.querySelector<HTMLElement>(".search-panel")!;
  const input = root.querySelector<HTMLInputElement>(".search-input")!;
  const list = root.querySelector<HTMLUListElement>(".search-results")!;
  const status = root.querySelector<HTMLElement>(".search-status")!;
  let cat: Catalogue | null = null;
  let results: Entry[] = [];
  let active = -1;
  let timer = 0;

  const ensure = (): void => {
    if (cat) return;
    status.textContent = "Loading stations…";
    loadCatalogue().then((c) => {
      cat = c;
      status.textContent = "";
      if (input.value) render();
    }).catch(() => { status.textContent = "Search is unavailable right now."; });
  };

  const open = (): void => {
    panel.hidden = false;
    button.setAttribute("aria-expanded", "true");
    ensure();
    input.focus();
  };
  const close = (refocus: boolean): void => {
    panel.hidden = true;
    button.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-expanded", "false");
    if (refocus) button.focus();
  };

  const setActive = (i: number): void => {
    active = i;
    list.querySelectorAll<HTMLElement>("[role=option]").forEach((li, k) => li.setAttribute("aria-selected", String(k === i)));
    if (i >= 0) {
      input.setAttribute("aria-activedescendant", `station-opt-${i}`);
      list.children[i]?.scrollIntoView({ block: "nearest" });
    } else input.removeAttribute("aria-activedescendant");
  };

  function render(): void {
    if (!cat) return;
    results = search(cat, input.value);
    list.replaceChildren(...results.map((e, i) => {
      const li = document.createElement("li");
      li.id = `station-opt-${i}`;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", "false");
      const a = document.createElement("a");
      a.href = `/${e.path}`;
      a.tabIndex = -1;
      const name = document.createElement("span");
      name.className = "search-name";
      name.textContent = e.name;
      const where = document.createElement("span");
      where.className = "search-where";
      where.textContent = `${e.type === "gauge" ? "Tide gauge · " : ""}${e.region}, ${e.cc}`;
      a.append(name, where);
      li.append(a);
      return li;
    }));
    const q = input.value.trim();
    input.setAttribute("aria-expanded", String(results.length > 0));
    status.textContent = q.length >= 2 && !results.length ? "No matching stations." : "";
    setActive(-1);
  }

  button.addEventListener("click", () => (panel.hidden ? open() : close(true)));
  input.addEventListener("focus", ensure);
  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(render, DEBOUNCE_MS);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!results.length) return;
      e.preventDefault();
      const n = results.length;
      setActive(e.key === "ArrowDown" ? (active + 1) % n : (active - 1 + n) % n);
    } else if (e.key === "Enter") {
      window.clearTimeout(timer);
      if (cat && !results.length) render();
      const pick = results[Math.max(active, 0)];
      if (pick) {
        e.preventDefault();
        window.location.assign(`/${pick.path}`);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      close(true);
    }
  });
  document.addEventListener("pointerdown", (e) => {
    if (!panel.hidden && !root.contains(e.target as Node)) close(false);
  });
}
