// Deterministic timeline: every frame is a pure function of t (seconds). No CSS transitions.
const W = 1080, H = 1920, FPS = 60, BPM = 120, BAR = 2.0, BEAT = 0.5;

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
  outQuint: u => 1 - Math.pow(1 - u, 5),
  inQuint: u => u ** 5,
  outExpo: u => u >= 1 ? 1 : 1 - Math.pow(2, -10 * u),
  inExpo: u => u <= 0 ? 0 : Math.pow(2, 10 * u - 10),
  ioQuint: u => u < .5 ? 16 * u ** 5 : 1 - Math.pow(-2 * u + 2, 5) / 2,
  outBack: (u, s = 1.9) => 1 + (s + 1) * Math.pow(u - 1, 3) + s * Math.pow(u - 1, 2),
};
const ease = (t, a, b, fn = E.ioCubic) => fn(prog(t, a, b));
const ramp = (t, a, b, v0, v1, fn = E.ioCubic) => lerp(v0, v1, ease(t, a, b, fn));

// Damped spring from 0 → 1 (starts at 0, overshoots, settles). dt = seconds since start.
function spring(dt, freq = 2.6, damp = 0.34) {
  if (dt <= 0) return 0;
  const w = 2 * Math.PI * freq, z = damp, wd = w * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * w * dt) * (Math.cos(wd * dt) + (z * w / wd) * Math.sin(wd * dt));
}
// Impulse wobble: 0 at dt=0, oscillates and dies. Good for squash on landing.
const wob = (dt, freq = 3.2, decay = 5.5) => dt <= 0 ? 0 : Math.sin(dt * freq * 2 * Math.PI) * Math.exp(-dt * decay);

// Seeded hash noise (deterministic shake, jitter).
const hash = n => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

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
// Place an element by its centre: (x, y) centre, scale, rotation (deg), opacity.
function put(e, x, y, s = 1, r = 0, o = 1, sx = 1, sy = 1) {
  e.style.transform = `translate(${x}px,${y}px) translate(-50%,-50%) rotate(${r}deg) scale(${s * sx},${s * sy})`;
  e.style.opacity = o;
  e.style.visibility = o <= 0.001 ? "hidden" : "visible";
}
// Place by top-left corner (for left-aligned type).
function putTL(e, x, y, s = 1, r = 0, o = 1) {
  e.style.transformOrigin = "0 0";
  e.style.transform = `translate(${x}px,${y}px) rotate(${r}deg) scale(${s})`;
  e.style.opacity = o;
  e.style.visibility = o <= 0.001 ? "hidden" : "visible";
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
// Cue at absolute time t: name + optional params (gain, pitch...)
function cue(t, name, p = {}) { CUES.push(Object.assign({ t: +t.toFixed(4), name }, p)); }

let STAGE, SHAKE = { x: 0, y: 0 };
function seek(t) {
  SHAKE.x = 0; SHAKE.y = 0;
  let poseScene = null;
  for (const s of SCENES) {
    const on = t >= s.t0 && t < s.t1;
    if (on !== s._on) { s.root.style.display = on ? "block" : "none"; s._on = on; }
    if (on) {
      s.update && s.update(t - s.t0, t);
      if (s.pose && t >= (s.poseFrom ?? s.t0) && t < (s.poseTo ?? s.t1)) poseScene = s;
    }
  }
  const p = poseScene ? poseScene.pose(t - poseScene.t0, t) : { hidden: true };
  const anchor = MASCOT.set(p);
  BUBBLES.update(t, anchor);
  STAGE.style.transform = (SHAKE.x || SHAKE.y) ? `translate(${SHAKE.x}px,${SHAKE.y}px) scale(1.04)` : "";
}
function shake(t, t0, amp = 22, dur = 0.45) {
  const u = t - t0;
  if (u < 0 || u > dur) return;
  const k = amp * Math.pow(1 - u / dur, 2), f = Math.floor(u * 60);
  SHAKE.x += (hash(f + t0 * 13) - .5) * 2 * k;
  SHAKE.y += (hash(f * 1.7 + t0 * 7) - .5) * 2 * k;
}
