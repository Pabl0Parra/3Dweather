// WebGL globe: one full-screen triangle, the fragment shader inverse-projects
// every pixel and composes sea, land, the data layer and the limb glow.
import { rampTable, type Layer } from "./layers";
import type { GlobeManifest } from "./manifest";
import type { TideAtlas } from "./tide";
import { radiusPx, type View } from "./view";

const VERT = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAG = `
precision highp float;
uniform vec2 uCentre;       // device px, origin bottom-left
uniform float uRadius;      // device px
uniform float uLat0, uLon0; // radians
uniform vec4 uGrid;         // west, dlon, north, dlat (degrees)
uniform vec2 uGridSize;     // cells
uniform sampler2D uFrameA, uFrameB, uLand, uRamp, uVeilA, uVeilB;
uniform float uMix, uHasData;
uniform float uBody;        // intro: globe body and limb fade in
uniform float uKind;        // 0: one byte indexes the ramp; 1: speed of a two-channel vector
uniform vec4 uMaskA, uMaskB; // channel selectors (scalar / vector x, vector y)
uniform float uVecScale;    // m/s for a full-scale vector byte
uniform float uVecMax;      // speed at the top of the ramp
uniform float uOverLand;    // 1: the layer is drawn over land too
uniform float uHasVeil;     // 1: cloud veil from the second frame pair (R channel)
uniform sampler2D uTide;    // tide atlas: 6 RGB tiles stacked vertically (X, Y per constituent; mask)
uniform vec4 uTideGrid;     // west, dlon, north, dlat
uniform vec2 uTideSize;     // cells per tile
uniform float uTideC[8], uTideS[8]; // amax·f·cos(V+u), amax·f·sin(V+u) now
uniform float uTideMin, uTideMax;   // ramp range (m)

const float PI = 3.141592653589793;
const vec3 SEA = vec3(8.0, 26.0, 46.0) / 255.0;
const vec3 LAND = vec3(27.0, 38.0, 54.0) / 255.0;
const vec3 GLOW = vec3(63.0, 224.0, 255.0) / 255.0;
const vec3 CLOUD = vec3(222.0, 230.0, 240.0) / 255.0;

vec4 cell(sampler2D t, float x, float y) {
  return texture2D(t, vec2((x + 0.5) / uGridSize.x, (y + 0.5) / uGridSize.y));
}

// Bilinear on the raw bytes with the x index wrapped, so +-180 has no seam.
vec4 sample4(sampler2D t, float lat, float lon) {
  float fx = (lon - uGrid.x) / uGrid.y;
  float fy = clamp((uGrid.z - lat) / uGrid.w, 0.0, uGridSize.y - 1.0);
  float x0 = floor(fx), y0 = floor(fy);
  float tx = fx - x0, ty = fy - y0;
  float xa = mod(x0, uGridSize.x), xb = mod(x0 + 1.0, uGridSize.x);
  float yb = min(y0 + 1.0, uGridSize.y - 1.0);
  return mix(mix(cell(t, xa, y0), cell(t, xb, y0), tx), mix(cell(t, xa, yb), cell(t, xb, yb), tx), ty);
}

vec3 tideTexel(float x, float y, float tile) {
  vec3 v = texture2D(uTide, vec2((x + 0.5) / uTideSize.x, (tile * uTideSize.y + y + 0.5) / (6.0 * uTideSize.y))).rgb;
  return (v * 255.0 - 128.0) / 127.0;
}

// Height of one atlas cell (x: sea weight 1 or 0, y: height in m).
vec2 tideCell(float x, float y) {
  vec3 d0 = tideTexel(x, y, 0.0), d1 = tideTexel(x, y, 1.0), d2 = tideTexel(x, y, 2.0);
  vec3 d3 = tideTexel(x, y, 3.0), d4 = tideTexel(x, y, 4.0), d5 = tideTexel(x, y, 5.0);
  float h = d0.r * uTideC[0] + d0.g * uTideS[0] + d0.b * uTideC[1] + d1.r * uTideS[1]
          + d1.g * uTideC[2] + d1.b * uTideS[2] + d2.r * uTideC[3] + d2.g * uTideS[3]
          + d2.b * uTideC[4] + d3.r * uTideS[4] + d3.g * uTideC[5] + d3.b * uTideS[5]
          + d4.r * uTideC[6] + d4.g * uTideS[6] + d4.b * uTideC[7] + d5.r * uTideS[7];
  float sea = step(0.0, d5.g); // mask byte 255 -> +1, 0 -> about -1
  return vec2(sea, h * sea);
}

// Sea-weighted bilinear height, x wrapped; NaN-free: returns (has sea at the nearest cell, height).
vec2 tideAt(float lat, float lon) {
  float fx = (lon - uTideGrid.x) / uTideGrid.y;
  float fy = clamp((uTideGrid.z - lat) / uTideGrid.w, 0.0, uTideSize.y - 1.0);
  float x0 = floor(fx), y0 = floor(fy);
  float tx = fx - x0, ty = fy - y0;
  float xa = mod(x0, uTideSize.x), xb = mod(x0 + 1.0, uTideSize.x);
  float yb = min(y0 + 1.0, uTideSize.y - 1.0);
  vec2 c00 = tideCell(xa, y0), c10 = tideCell(xb, y0), c01 = tideCell(xa, yb), c11 = tideCell(xb, yb);
  vec4 w = vec4((1.0 - tx) * (1.0 - ty), tx * (1.0 - ty), (1.0 - tx) * ty, tx * ty);
  float ws = dot(w, vec4(c00.x, c10.x, c01.x, c11.x));
  float hs = dot(w, vec4(c00.y, c10.y, c01.y, c11.y));
  float nearest = tx < 0.5 ? (ty < 0.5 ? c00.x : c01.x) : (ty < 0.5 ? c10.x : c11.x);
  return vec2(nearest, ws > 0.0 ? hs / ws : 0.0);
}

void main() {
  vec2 p = (gl_FragCoord.xy - uCentre) / uRadius;
  float rho = length(p);
  if (rho > 1.0) {
    float edge = (rho - 1.0) * uRadius;
    float a = exp(-edge / 7.0) * 0.55 * uBody;
    gl_FragColor = vec4(GLOW * a, a);
    return;
  }
  float c = asin(rho);
  float sc = sin(c), cc = cos(c);
  float lat = uLat0, lon = uLon0;
  if (rho > 0.0) {
    lat = asin(cc * sin(uLat0) + p.y * sc * cos(uLat0) / rho);
    lon = uLon0 + atan(p.x * sc, rho * cos(uLat0) * cc - p.y * sin(uLat0) * sc);
  }
  float latD = lat * 180.0 / PI;
  float lonD = mod(lon * 180.0 / PI + 180.0, 360.0) - 180.0;

  float land = step(0.5, texture2D(uLand, vec2((lonD + 180.0) / 360.0, (90.0 - latD) / 180.0)).r);
  vec3 col = mix(SEA, LAND, land);
  if (uHasData > 0.5 && (land < 0.5 || uOverLand > 0.5)) {
    if (uHasVeil > 0.5) {
      float cloud = mix(sample4(uVeilA, latD, lonD).r, sample4(uVeilB, latD, lonD).r, uMix);
      col = mix(col, CLOUD, cloud * 0.55);
    }
    vec4 f = mix(sample4(uFrameA, latD, lonD), sample4(uFrameB, latD, lonD), uMix);
    float idx = dot(f, uMaskA);
    float paint = 1.0;
    if (uKind > 1.5) {
      vec2 t = tideAt(latD, lonD);
      paint = t.x;
      idx = clamp((t.y - uTideMin) / (uTideMax - uTideMin), 0.0, 1.0);
    } else if (uKind > 0.5) {
      vec2 vel = (vec2(dot(f, uMaskA), dot(f, uMaskB)) * 255.0 - 128.0) / 127.0 * uVecScale;
      idx = sqrt(clamp(length(vel) / uVecMax, 0.0, 1.0));
    }
    vec4 w = texture2D(uRamp, vec2((idx * 255.0 + 0.5) / 256.0, 0.5));
    col = mix(col, w.rgb, w.a * paint);
    col = mix(col, LAND, land * 0.25); // keep coasts readable under layers drawn over land
  }
  float shade = 0.72 + 0.28 * cc;            // gentle darkening towards the limb
  float rim = smoothstep(0.86, 1.0, rho) * 0.35;
  gl_FragColor = vec4((col * shade + GLOW * rim) * uBody, uBody);
}
`;

type TexKey = "a" | "b" | "land" | "ramp" | "va" | "vb" | "tide";
type Vec4 = [number, number, number, number];
const mask = (ch: number): Vec4 => [0, 1, 2, 3].map((i) => (i === ch ? 1 : 0)) as Vec4;

/** Full-scale byte speed (m/s) of each vector family: wind (b-128)*50/127, currents (b-128)/127*2.5. */
const VEC_SCALE: Partial<Record<string, number>> = { a: 50, c: 2.5 };

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? "shader error");
  return s;
}

export class GlobeRenderer {
  private gl: WebGLRenderingContext;
  private prog: WebGLProgram;
  private u: Record<string, WebGLUniformLocation | null> = {};
  private tex: Record<TexKey, WebGLTexture>;
  private mix = 0;
  private hasData = false;
  private veil = false;
  private layer: Layer | null = null;
  private grid: GlobeManifest | null = null;
  private tideGrid: TideAtlas | null = null;
  private tidePhases: { c: number[]; s: number[] } | null = null;

  constructor(private canvas: HTMLCanvasElement) {
    const gl = canvas.getContext("webgl", { preserveDrawingBuffer: true, premultipliedAlpha: false, antialias: false });
    if (!gl) throw new Error("WebGL is not available");
    this.gl = gl;
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    const prog = gl.createProgram()!;
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) ?? "link error");
    this.prog = prog;
    gl.useProgram(prog);
    for (const n of ["uCentre", "uRadius", "uLat0", "uLon0", "uGrid", "uGridSize", "uFrameA", "uFrameB", "uLand", "uRamp",
      "uVeilA", "uVeilB", "uMix", "uHasData", "uBody", "uKind", "uMaskA", "uMaskB", "uVecScale", "uVecMax", "uOverLand", "uHasVeil",
      "uTide", "uTideGrid", "uTideSize", "uTideC", "uTideS", "uTideMin", "uTideMax"])
      this.u[n] = gl.getUniformLocation(prog, n);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    const empty = new Uint8Array(4);
    this.tex = {
      a: this.texture(1, 1, empty, gl.NEAREST, gl.CLAMP_TO_EDGE),
      b: this.texture(1, 1, empty, gl.NEAREST, gl.CLAMP_TO_EDGE),
      land: this.texture(1, 1, empty, gl.LINEAR, gl.CLAMP_TO_EDGE),
      ramp: this.texture(256, 1, new Uint8Array(1024), gl.LINEAR, gl.CLAMP_TO_EDGE),
      va: this.texture(1, 1, empty, gl.NEAREST, gl.CLAMP_TO_EDGE),
      vb: this.texture(1, 1, empty, gl.NEAREST, gl.CLAMP_TO_EDGE),
      tide: this.texture(1, 1, empty, gl.NEAREST, gl.CLAMP_TO_EDGE),
    };
    (["a", "b", "land", "ramp", "va", "vb", "tide"] as TexKey[]).forEach((k, i) => {
      gl.activeTexture(gl.TEXTURE0 + i);
      gl.bindTexture(gl.TEXTURE_2D, this.tex[k]);
    });
    gl.uniform1i(this.u.uFrameA, 0);
    gl.uniform1i(this.u.uFrameB, 1);
    gl.uniform1i(this.u.uLand, 2);
    gl.uniform1i(this.u.uRamp, 3);
    gl.uniform1i(this.u.uVeilA, 4);
    gl.uniform1i(this.u.uVeilB, 5);
    gl.uniform1i(this.u.uTide, 6);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  }

  private texture(w: number, h: number, data: ArrayBufferView | TexImageSource, filter: number, wrap: number): WebGLTexture {
    const gl = this.gl;
    const t = gl.createTexture()!;
    // Upload on a scratch unit so the samplers bound to units 0-6 stay put.
    gl.activeTexture(gl.TEXTURE7);
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, wrap);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    if (ArrayBuffer.isView(data)) {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(data.buffer, data.byteOffset, data.byteLength));
    } else {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, data);
    }
    return t;
  }

  private replace(unit: number, key: TexKey, t: WebGLTexture): void {
    const gl = this.gl;
    gl.deleteTexture(this.tex[key]);
    this.tex[key] = t;
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, t);
  }

  setGrid(m: GlobeManifest): void {
    this.grid = m;
  }

  setLandMask(img: ImageBitmap): void {
    // 2048 x 1024 is a power of two, so REPEAT and LINEAR are allowed.
    this.replace(2, "land", this.texture(img.width, img.height, img, this.gl.LINEAR, this.gl.REPEAT));
  }

  /** The layer to draw: its ramp and how its bytes become a colour. Data stays hidden until setFrames. */
  setLayer(l: Layer): void {
    this.layer = l;
    this.hasData = false;
    this.veil = false;
    this.replace(3, "ramp", this.texture(256, 1, rampTable(l), this.gl.LINEAR, this.gl.CLAMP_TO_EDGE));
  }

  setFrames(a: Uint8ClampedArray, b: Uint8ClampedArray, mix: number, veil?: { a: Uint8ClampedArray; b: Uint8ClampedArray }): void {
    if (!this.grid) throw new Error("setGrid first");
    const { w, h } = this.grid, gl = this.gl;
    this.replace(0, "a", this.texture(w, h, a, gl.NEAREST, gl.CLAMP_TO_EDGE));
    this.replace(1, "b", this.texture(w, h, b, gl.NEAREST, gl.CLAMP_TO_EDGE));
    if (veil) {
      this.replace(4, "va", this.texture(w, h, veil.a, gl.NEAREST, gl.CLAMP_TO_EDGE));
      this.replace(5, "vb", this.texture(w, h, veil.b, gl.NEAREST, gl.CLAMP_TO_EDGE));
    }
    this.veil = !!veil;
    this.mix = mix;
    this.hasData = true;
  }

  /** The tide atlas (RGBA pixels of the w × h·tiles image) and its grid; once per page. */
  setTideAtlas(a: TideAtlas): void {
    const gl = this.gl;
    this.tideGrid = a;
    this.replace(6, "tide", this.texture(a.w, a.h * a.tiles, a.pixels, gl.NEAREST, gl.CLAMP_TO_EDGE));
  }

  /** Tide layer: the constituent phases at the moment shown. Shows the layer. */
  setTidePhases(p: { c: number[]; s: number[] }): void {
    this.tidePhases = p;
    this.hasData = true;
    this.veil = false;
  }

  setMix(mix: number): void {
    this.mix = mix;
  }

  /** Intro fade of the globe body and limb, 0..1. */
  body = 1;

  draw(v: View, cssW: number, cssH: number, dpr: number): void {
    const gl = this.gl, c = this.canvas;
    const w = Math.round(cssW * dpr), h = Math.round(cssH * dpr);
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(this.u.uCentre, w / 2, h / 2);
    gl.uniform1f(this.u.uRadius, radiusPx(v.zoom, cssW, cssH) * dpr);
    gl.uniform1f(this.u.uLat0, (v.lat0 * Math.PI) / 180);
    gl.uniform1f(this.u.uLon0, (v.lon0 * Math.PI) / 180);
    const g = this.grid;
    gl.uniform4f(this.u.uGrid, g?.west ?? -180, g?.dlon ?? 1, g?.north ?? 90, g?.dlat ?? 1);
    gl.uniform2f(this.u.uGridSize, g?.w ?? 1, g?.h ?? 1);
    gl.uniform1f(this.u.uMix, this.mix);
    gl.uniform1f(this.u.uHasData, this.hasData ? 1 : 0);
    gl.uniform1f(this.u.uBody, this.body);
    const l = this.layer;
    if (l?.shade.kind === "tide") {
      const t = this.tideGrid, p = this.tidePhases;
      gl.uniform1f(this.u.uKind, 2);
      gl.uniform4f(this.u.uTideGrid, t?.west ?? -180, t?.dlon ?? 1, t?.north ?? 90, t?.dlat ?? 1);
      gl.uniform2f(this.u.uTideSize, t?.w ?? 1, t?.h ?? 1);
      gl.uniform1fv(this.u.uTideC, new Float32Array(p?.c ?? new Array(8).fill(0)));
      gl.uniform1fv(this.u.uTideS, new Float32Array(p?.s ?? new Array(8).fill(0)));
      gl.uniform1f(this.u.uTideMin, l.shade.min);
      gl.uniform1f(this.u.uTideMax, l.shade.max);
      gl.uniform4fv(this.u.uMaskA, mask(0));
      gl.uniform4fv(this.u.uMaskB, mask(1));
    } else if (l?.shade.kind === "vector") {
      gl.uniform1f(this.u.uKind, 1);
      gl.uniform4fv(this.u.uMaskA, mask(l.shade.channels[0]));
      gl.uniform4fv(this.u.uMaskB, mask(l.shade.channels[1]));
      gl.uniform1f(this.u.uVecScale, VEC_SCALE[l.shade.family] ?? 1);
      gl.uniform1f(this.u.uVecMax, l.vecMax ?? 1);
    } else {
      gl.uniform1f(this.u.uKind, 0);
      gl.uniform4fv(this.u.uMaskA, mask(l?.shade.kind === "scalar" ? l.shade.channel : 0));
      gl.uniform4fv(this.u.uMaskB, mask(1));
      gl.uniform1f(this.u.uVecScale, 1);
      gl.uniform1f(this.u.uVecMax, 1);
    }
    gl.uniform1f(this.u.uOverLand, l?.overLand ? 1 : 0);
    gl.uniform1f(this.u.uHasVeil, this.veil ? 1 : 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
}
