// Filter box on browse pages: hides list items whose text does not contain the typed words.
import { fold } from "../search/catalogue";

export function mountFilter(input: HTMLInputElement, items: HTMLElement[]): void {
  const keys = items.map((li) => fold(li.textContent || ""));
  input.addEventListener("input", () => {
    const words = fold(input.value).split(" ").filter(Boolean);
    items.forEach((li, k) => { li.hidden = !words.every((w) => keys[k].includes(w)); });
  });
}
