// The /embed builder: pick a place (catalogue search) and options; the preview iframe and the
// snippet follow. The snippet uses this page's own origin, so it is right on any host.
import { loadCatalogue, search, type Catalogue } from "../search/catalogue";
import { embedUrl, embedHeight, iframeSnippet, parseParams, type EmbedOptions } from "./params";

export function mountBuilder(root: HTMLElement): void {
  const input = root.querySelector<HTMLInputElement>("[data-embed-search]")!;
  const results = root.querySelector<HTMLElement>("[data-embed-results]")!;
  const chosen = root.querySelector<HTMLElement>("[data-embed-chosen]")!;
  const frame = root.querySelector<HTMLIFrameElement>("iframe[data-embed-preview]")!;
  const code = root.querySelector<HTMLTextAreaElement>("textarea[data-embed-code]")!;
  const copy = root.querySelector<HTMLButtonElement>("[data-embed-copy]")!;
  const status = root.querySelector<HTMLElement>("[data-embed-status]")!;
  const opts = (name: string) => root.querySelector<HTMLSelectElement>(`select[data-opt=${name}]`)!;

  const start = parseParams(location.search);
  const state: EmbedOptions & { name: string } = { ...start, name: "" };
  opts("unit").value = state.unit;
  opts("theme").value = state.theme;
  opts("days").value = String(state.days);

  let catalogue: Promise<Catalogue | null> | null = null;
  const cat = () => (catalogue ??= loadCatalogue().catch(() => null));

  const update = () => {
    if (!state.station) {
      chosen.textContent = "No place chosen yet.";
      code.value = "";
      frame.removeAttribute("src");
      return;
    }
    chosen.textContent = state.name || state.station;
    const url = embedUrl(location.origin, state);
    if (frame.getAttribute("src") !== url) frame.src = url;
    frame.height = String(embedHeight(state.days));
    code.value = iframeSnippet(location.origin, state, state.name || state.station);
  };

  const choose = (path: string, name: string) => {
    state.station = path;
    state.name = name;
    results.replaceChildren();
    input.value = "";
    update();
  };

  input.addEventListener("input", async () => {
    const c = await cat();
    if (!c) { status.textContent = "The place list could not be loaded."; return; }
    results.replaceChildren(...search(c, input.value, 8).map((e) => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn";
      b.textContent = `${e.name}, ${e.region}`;
      b.addEventListener("click", () => choose(e.path, e.name));
      li.append(b);
      return li;
    }));
  });

  for (const name of ["unit", "theme", "days"] as const) {
    opts(name).addEventListener("change", () => {
      const v = opts(name).value;
      if (name === "unit") state.unit = v === "ft" ? "ft" : "m";
      else if (name === "theme") state.theme = v === "light" ? "light" : "dark";
      else state.days = (Math.max(1, Math.min(3, Number(v))) || 1) as 1 | 2 | 3;
      update();
    });
  }

  copy.addEventListener("click", async () => {
    if (!code.value) return;
    try {
      await navigator.clipboard.writeText(code.value);
      status.textContent = "Copied.";
    } catch {
      code.select();
      status.textContent = "Select the code and copy it.";
    }
  });

  update();
  if (state.station) {
    cat().then((c) => {
      const e = c?.entries.find((x) => x.path === state.station);
      if (e) { state.name = e.name; update(); }
    });
  }
}
