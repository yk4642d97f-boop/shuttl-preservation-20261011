// Deterministic timeline: every frame is a pure function of t (seconds). No CSS transitions, no rAF state.
const W = 1920, H = 1080, BPM = 120, BEAT = 0.5, BAR = 2.0;

const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, u) => a + (b - a) * u;
const prog = (t, a, b) => clamp((t - a) / (b - a));
const E = {
  lin: u => u,
  inSine: u => 1 - Math.cos(u * Math.PI / 2),
  outSine: u => Math.sin(u * Math.PI / 2),
  ioSine: u => -(Math.cos(Math.PI * u) - 1) / 2,
  inCubic: u => u * u * u,
  outCubic: u => 1 - Math.pow(1 - u, 3),
  ioCubic: u => u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2,
  outQuart: u => 1 - Math.pow(1 - u, 4),
  outQuint: u => 1 - Math.pow(1 - u, 5),
  inQuint: u => u ** 5,
  ioQuint: u => u < .5 ? 16 * u ** 5 : 1 - Math.pow(-2 * u + 2, 5) / 2,
  outExpo: u => u >= 1 ? 1 : 1 - Math.pow(2, -10 * u),
  inExpo: u => u <= 0 ? 0 : Math.pow(2, 10 * u - 10),
  ioExpo: u => u <= 0 ? 0 : u >= 1 ? 1 : u < .5 ? Math.pow(2, 20 * u - 10) / 2 : (2 - Math.pow(2, -20 * u + 10)) / 2,
  outBack: (u, s = 1.7) => 1 + (s + 1) * Math.pow(u - 1, 3) + s * Math.pow(u - 1, 2),
};
const ease = (t, a, b, fn = E.ioCubic) => fn(prog(t, a, b));
const ramp = (t, a, b, v0, v1, fn = E.ioCubic) => lerp(v0, v1, ease(t, a, b, fn));
// Damped spring 0 → 1. dt = seconds since start.
function spring(dt, freq = 2.6, damp = 0.34) {
  if (dt <= 0) return 0;
  const w = 2 * Math.PI * freq, z = damp, wd = w * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * w * dt) * (Math.cos(wd * dt) + (z * w / wd) * Math.sin(wd * dt));
}
const wob = (dt, freq = 3.2, decay = 5.5) => dt <= 0 ? 0 : Math.sin(dt * freq * 2 * Math.PI) * Math.exp(-dt * decay);
const hash = n => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
// Snap a value to a frame grid of `fps` (stop-motion stepping for a deliberately mechanical feel).
const step = (t, fps) => Math.floor(t * fps) / fps;

// DOM helpers
function el(tag, cls, parent, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  if (parent) parent.appendChild(e);
  return e;
}
function css(e, o) { for (const k in o) e.style[k] = o[k]; return e; }
const svgNS = "http://www.w3.org/2000/svg";
function sv(tag, attrs, parent) {
  const e = document.createElementNS(svgNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function vis(e, on) { const v = on ? "visible" : "hidden"; if (e.style.visibility !== v) e.style.visibility = v; }
// Centre-anchored placement: (x, y) centre, scale, rotation (deg), opacity.
function put(e, x, y, s = 1, r = 0, o = 1, sx = 1, sy = 1) {
  e.style.transform = `translate(${x}px,${y}px) translate(-50%,-50%) rotate(${r}deg) scale(${s * sx},${s * sy})`;
  e.style.opacity = o;
  vis(e, o > 0.001 && s * sx * sy !== 0);
}
// Top-left anchored placement (for left-aligned type).
function putTL(e, x, y, s = 1, r = 0, o = 1) {
  e.style.transformOrigin = "0 0";
  e.style.transform = `translate(${x}px,${y}px) rotate(${r}deg) scale(${s})`;
  e.style.opacity = o;
  vis(e, o > 0.001 && s !== 0);
}
function canvas(parent, w = W, h = H) {
  const c = el("canvas", "abs", parent);
  c.width = w; c.height = h;
  return c;
}

// Scenes + sound cues
const SCENES = [];
const CUES = [];
function S(def) { SCENES.push(def); return def; }
function cue(t, name, p = {}) { CUES.push(Object.assign({ t: +t.toFixed(4), name }, p)); }

let STAGE, SHAKE = { x: 0, y: 0, r: 0 };
function seek(t) {
  SHAKE.x = 0; SHAKE.y = 0; SHAKE.r = 0;
  for (const s of SCENES) {
    const on = t >= s.t0 && t < s.t1;
    if (on !== s._on) { s.root.style.display = on ? "block" : "none"; s._on = on; }
    if (on) s.update && s.update(t - s.t0, t);
  }
  STAGE.style.transform = (SHAKE.x || SHAKE.y || SHAKE.r)
    ? `translate(${SHAKE.x}px,${SHAKE.y}px) rotate(${SHAKE.r}deg) scale(1.03)` : "";
}
// Hard, decaying camera jolt (stamp / slam).
function shake(t, t0, amp = 22, dur = 0.4) {
  const u = t - t0;
  if (u < 0 || u > dur) return;
  const k = amp * Math.pow(1 - u / dur, 2), f = Math.floor(u * 60);
  SHAKE.x += (hash(f + t0 * 13) - .5) * 2 * k;
  SHAKE.y += (hash(f * 1.7 + t0 * 7) - .5) * 2 * k;
  SHAKE.r += (hash(f * 2.3 + t0) - .5) * k * 0.02;
}
