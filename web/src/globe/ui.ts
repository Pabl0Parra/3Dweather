// Legend for the current layer, built from its colour ramp.
import { legendGradient, legendScale, type Layer } from "./layers";
import type { Units } from "./units";

/** Draws the legend for a layer; call the returned function when the units change. */
export function mountLegend(root: HTMLElement, layer: Layer, units: Units): (units: Units) => void {
  root.classList.add("legend");
  root.innerHTML = `
    <span class="lg-title"></span>
    <div class="lg-bar" style="background: linear-gradient(to right, ${legendGradient(layer)})"></div>
    <div class="lg-ticks"></div>`;
  root.setAttribute("role", "img");
  root.querySelector(".lg-title")!.textContent = layer.legend.title;
  const ticks = root.querySelector<HTMLDivElement>(".lg-ticks")!;
  const update = (u: Units) => {
    const s = legendScale(layer, u);
    ticks.innerHTML = s.ticks.map(([v, label]) => `<span style="left:${s.pos(v).toFixed(1)}%">${label}</span>`).join("")
      + `<span class="lg-unit">${s.unit}</span>`;
    root.setAttribute("aria-label", `${s.title} colour scale, ${s.ticks.map(([, l]) => l).join(", ")} ${s.spoken}`);
  };
  update(units);
  return update;
}
