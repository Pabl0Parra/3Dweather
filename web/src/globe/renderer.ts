// WebGL globe: one full-screen triangle, the fragment shader inverse-projects
// every pixel and composes sea, land, the wave layer and the limb glow.
import type { GlobeManifest } from "./manifest";
import { rampTable } from "./ramp";
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
uniform sampler2D uFrameA, uFrameB, uLand, uRamp;
uniform float uMix, uHasData;
uniform float uBody;        // intro: globe body and limb fade in

const float PI = 3.141592653589793;
const vec3 SEA = vec3(8.0, 26.0, 46.0) / 255.0;
const vec3 LAND = vec3(27.0, 38.0, 54.0) / 255.0;
const vec3 GLOW = vec3(63.0, 224.0, 255.0) / 255.0;

float cell(sampler2D t, float x, float y) {
  return texture2D(t, vec2((x + 0.5) / uGridSize.x, (y + 0.5) / uGridSize.y)).r;
}

// Bilinear on the height byte with the x index wrapped, so +-180 has no seam.
float height(sampler2D t, float lat, float lon) {
  float fx = (lon - uGrid.x) / uGrid.y;
  float fy = clamp((uGrid.z - lat) / uGrid.w, 0.0, uGridSize.y - 1.0);
  float x0 = floor(fx), y0 = floor(fy);
  float tx = fx - x0, ty = fy - y0;
  float xa = mod(x0, uGridSize.x), xb = mod(x0 + 1.0, uGridSize.x);
  float yb = min(y0 + 1.0, uGridSize.y - 1.0);
  return mix(mix(cell(t, xa, y0), cell(t, xb, y0), tx), mix(cell(t, xa, yb), cell(t, xb, yb), tx), ty);
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

  float land = texture2D(uLand, vec2((lonD + 180.0) / 360.0, (90.0 - latD) / 180.0)).r;
  vec3 col = SEA;
  if (uHasData > 0.5) {
    float h = mix(height(uFrameA, latD, lonD), height(uFrameB, latD, lonD), uMix);
    vec4 w = texture2D(uRamp, vec2((h * 255.0 + 0.5) / 256.0, 0.5));
    col = mix(SEA, w.rgb, w.a);
  }
  col = mix(col, LAND, step(0.5, land));
  float shade = 0.72 + 0.28 * cc;            // gentle darkening towards the limb
  float rim = smoothstep(0.86, 1.0, rho) * 0.35;
  gl_FragColor = vec4((col * shade + GLOW * rim) * uBody, uBody);
}
`;

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
  private tex: Record<"a" | "b" | "land" | "ramp", WebGLTexture>;
  private mix = 0;
  private hasData = false;
  private grid: GlobeManifest | null = null;

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
    for (const n of ["uCentre", "uRadius", "uLat0", "uLon0", "uGrid", "uGridSize", "uFrameA", "uFrameB", "uLand", "uRamp", "uMix", "uHasData", "uBody"])
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
      ramp: this.texture(256, 1, rampTable(), gl.LINEAR, gl.CLAMP_TO_EDGE),
    };
    [this.tex.a, this.tex.b, this.tex.land, this.tex.ramp].forEach((t, i) => {
      gl.activeTexture(gl.TEXTURE0 + i);
      gl.bindTexture(gl.TEXTURE_2D, t);
    });
    gl.uniform1i(this.u.uFrameA, 0);
    gl.uniform1i(this.u.uFrameB, 1);
    gl.uniform1i(this.u.uLand, 2);
    gl.uniform1i(this.u.uRamp, 3);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  }

  private texture(w: number, h: number, data: ArrayBufferView | TexImageSource, filter: number, wrap: number): WebGLTexture {
    const gl = this.gl;
    const t = gl.createTexture()!;
    // Upload on a scratch unit so the samplers bound to units 0-3 stay put.
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

  private replace(unit: number, key: "a" | "b" | "land", t: WebGLTexture): void {
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

  setFrames(a: Uint8ClampedArray, b: Uint8ClampedArray, mix: number): void {
    if (!this.grid) throw new Error("setGrid first");
    const { w, h } = this.grid, gl = this.gl;
    this.replace(0, "a", this.texture(w, h, a, gl.NEAREST, gl.CLAMP_TO_EDGE));
    this.replace(1, "b", this.texture(w, h, b, gl.NEAREST, gl.CLAMP_TO_EDGE));
    this.mix = mix;
    this.hasData = true;
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
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
}
