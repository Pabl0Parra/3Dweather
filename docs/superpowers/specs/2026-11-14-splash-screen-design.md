# Splash screen design: "Ignition"

Date: 2026-11-14. Status: approved by the owner on 2026-11-14.

The owner compared three animated mockups (Ignition, Sonar, Tideline) and chose
Ignition. The mockups are kept for reference in `docs/design/splash-concepts.html`
(open it in a browser; it needs an internet connection for Motion and the
coastline data). The owner also chose the Motion library (motion.dev) to build it.

## Intent

A short, striking opening for the globe that looks futuristic and is honest:
what the visitor sees assembling is the real forecast, and the splash turns
into the live map without a cut. It also covers the time the first map files
take to load.

## Sequence (about 3 seconds)

| Time | What happens |
|---|---|
| 0.0 s | Black screen. One thin cyan horizon line draws outward from the centre |
| 0.3 s | Monospace readouts resolve from scrambled glyphs, top left: the model run time, the models, and a cell count running up to 295,000 |
| 0.55 s | Particles stream in from the screen edges and wrap onto a sphere |
| 0.9 s | The globe body and its glowing edge fade in; the horizon line fades out |
| 1.35 s | Coastlines trace themselves in light |
| 1.85 s | The wordmark "3DWEATHER" resolves letter by letter |
| 2.45 s | The camera pushes in; wordmark and tagline fade; the real map controls slide up |
| 3.0 s | The particles are the live wave layer. The splash is over |

Look: near-black navy background (`#03060d`), electric cyan (`#3fe0ff`) for
lines and readouts, one hot accent (`#ff4fa3`) used sparingly, 1 px lines with
a soft glow, monospace type for readouts, wide-tracked sans for the wordmark.

## Differences between the mockup and the built version

- The mockup's particles follow an invented flow. The built version uses the
  wave vectors of the first forecast frame, with the globe's own particle system.
- The readouts show the actual run from `latest.json`, not fixed text.
- The mockup draws a separate 2D globe. The built version animates the real
  WebGL globe, so the hand-off needs no swap.

## Rules

- It plays on the globe pages only, never on station or browse pages.
- It plays once per browser session; later visits in the session open the map directly.
- Any tap, click, key press or scroll skips to the end state at once.
- Visitors with the reduced-motion setting get a 300 ms fade and no particles-in-flight.
- It never delays the map: if the first frame is ready before the splash ends,
  the splash still finishes on time; if the data is late, the particles hold
  their idle drift and the controls appear when the data arrives. If the data
  fails, the splash ends on the globe with the normal "could not load" message.
- A deep link (`#lat,lon,zoom`) ends with the camera on that place instead of
  the default view.
- The page's text content stays in the HTML underneath, so search engines and
  screen readers are unaffected; the splash is marked decorative.

## How it is built

- Motion (motion.dev) runs one timeline for the DOM parts (readouts, wordmark,
  controls) and drives a single progress value the globe reads each frame.
- The globe module exposes an "intro" mode: particle arrival, coastline reveal
  fraction and camera zoom as inputs. The splash only sets those inputs.
- It belongs to build phase 2 (the globe), after particles and coastline exist.

## Left to the builder

Exact easings and timings within about 0.2 s of the table, the scramble glyph
set, the tagline text, and how the session flag is stored.
