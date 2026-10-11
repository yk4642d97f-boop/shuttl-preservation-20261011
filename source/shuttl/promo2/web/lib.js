// Shuttl graphic primitives, ported from the app's ShuttlDesign package (Riso Court) so the film draws
// with the same geometry, inks and pictograms as the product.

const C = {
  paper: "#F4EEE3", paperDeep: "#EAE1D1", card: "#FFFBF4",
  ink: "#221B2E", inkSoft: "#5B5268", inkFaint: "#8C8397",
  tomato: "#F2542D", cobalt: "#2F4BDE", pistachio: "#B9D66A", lilac: "#C7B6F2", butter: "#F7D95C", flamingo: "#FF7AB6",
  tomatoText: "#BE3417", night: "#15121C", nightRaised: "#221D2B", courtNight: "#1F4A3A",
};

// ── Shot pictograms (ShotGlyph.swift) ────────────────────────────────────────
const GLYPH = {
  smash: { ink: C.tomato, zh: "扣杀", f: [[.12, .14], [.45, .36], [.88, .86]] },
  kill: { ink: C.tomato, zh: "扑球", f: [[.34, .20], [.50, .40], [.70, .86]] },
  clear: { ink: C.cobalt, zh: "高远", f: [[.12, .44], [.50, -.34], [.90, .60]] },
  lift: { ink: C.cobalt, zh: "挑球", f: [[.30, .82], [.60, -.30], [.92, .58]] },
  drop: { ink: C.lilac, zh: "吊球", f: [[.10, .20], [.46, .14], [.66, .86]] },
  net: { ink: C.pistachio, zh: "网前", f: [[.34, .66], [.50, .14], [.66, .66]] },
  block: { ink: C.pistachio, zh: "挡网", f: [[.30, .52], [.46, .30], [.62, .84]] },
  drive: { ink: C.butter, zh: "平抽", f: [[.10, .44], [.50, .36], [.90, .48]] },
  push: { ink: C.butter, zh: "推球", f: [[.30, .48], [.52, .34], [.84, .72]] },
  serve: { ink: C.flamingo, zh: "发球", f: [[.12, .76], [.46, .00], [.74, .70]] },
};
const GLYPH_KINDS = ["smash", "clear", "drop", "net", "drive", "serve", "lift", "push", "kill", "block"];
const onInk = k => (k === "clear" || k === "lift") ? C.card : C.ink;

// Draw a pictogram into a canvas square at (x, y) top-left, side s. `draw` 0…1 strokes the flight progressively.
function drawGlyph(g, kind, x, y, s, color, court = true, draw = 1) {
  const G = GLYPH[kind]; if (!G) return;
  const q = p => [x + p[0] * s, y + p[1] * s];
  g.save(); g.lineCap = "round"; g.strokeStyle = color; g.fillStyle = color;
  if (court) {
    g.globalAlpha *= 0.45; g.lineWidth = Math.max(1, s * .05);
    g.beginPath(); g.moveTo(...q([.04, .92])); g.lineTo(...q([.96, .92])); g.stroke();
    g.globalAlpha /= 0.45; g.lineWidth = Math.max(1, s * .07);
    g.beginPath(); g.moveTo(...q([.5, .92])); g.lineTo(...q([.5, .58])); g.stroke();
  }
  const [a, c, b] = G.f.map(q);
  g.lineWidth = Math.max(1.2, s * .085);
  const n = 40, m = Math.max(1, Math.round(n * clamp(draw)));
  const B = u => [(1 - u) ** 2 * a[0] + 2 * u * (1 - u) * c[0] + u * u * b[0], (1 - u) ** 2 * a[1] + 2 * u * (1 - u) * c[1] + u * u * b[1]];
  g.beginPath(); g.moveTo(...a);
  for (let i = 1; i <= m; i++) g.lineTo(...B(i / n));
  g.stroke();
  const e = B(m / n);
  g.beginPath(); g.arc(e[0], e[1], s * .1, 0, Math.PI * 2); g.fill();
  g.restore();
}
function glyphSVG(kind, color, size, court = true) {
  const G = GLYPH[kind]; const s = size;
  const P = p => `${(p[0] * s).toFixed(2)} ${(p[1] * s).toFixed(2)}`;
  const [a, c, b] = G.f;
  let o = `<svg width="${s}" height="${s}" viewBox="0 0 ${s} ${s}" style="overflow:visible;display:block">`;
  if (court) {
    o += `<path d="M${P([.04, .92])}L${P([.96, .92])}" stroke="${color}" stroke-opacity=".45" stroke-width="${Math.max(1, s * .05)}" stroke-linecap="round"/>`;
    o += `<path d="M${P([.5, .92])}L${P([.5, .58])}" stroke="${color}" stroke-width="${Math.max(1, s * .07)}" stroke-linecap="round"/>`;
  }
  o += `<path d="M${P(a)}Q${P(c)} ${P(b)}" fill="none" stroke="${color}" stroke-width="${Math.max(1.2, s * .085)}" stroke-linecap="round"/>`;
  o += `<circle cx="${(b[0] * s).toFixed(2)}" cy="${(b[1] * s).toFixed(2)}" r="${s * .1}" fill="${color}"/></svg>`;
  return o;
}
// ShotChip: the shot's ink, an ink outline, the pictogram.
function chipHTML(kind, size) {
  const pad = size * .14, inner = size - 2 * pad, bw = Math.max(1, size * .055);
  return `<div style="width:${size}px;height:${size}px;box-sizing:border-box;border-radius:${size * .28}px;background:${GLYPH[kind].ink};` +
    `border:${bw}px solid ${C.ink};padding:${pad - bw}px">${glyphSVG(kind, onInk(kind), inner)}</div>`;
}

// ── Scallop / Seal (Shapes.swift, Stickers.swift) ───────────────────────────
function scallopPath(cx, cy, outer, depth = .09, lobes = 16) {
  const inner = outer * (1 - depth), n = lobes * 16;
  let d = "";
  for (let i = 0; i <= n; i++) {
    const a = i / n * 2 * Math.PI - Math.PI / 2, w = (Math.cos(a * lobes) + 1) / 2, r = inner + (outer - inner) * w;
    d += (i ? "L" : "M") + (cx + Math.cos(a) * r).toFixed(2) + " " + (cy + Math.sin(a) * r).toFixed(2);
  }
  return d + "Z";
}
function sealSVG(size, fill, inner = "") {
  const r = size / 2;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="overflow:visible;display:block">` +
    `<path d="${scallopPath(r, r, r - 2, .09, size > 70 ? 16 : 14)}" fill="${fill}" stroke="${C.ink}" stroke-width="${Math.max(2, size * .028)}"/>` +
    `<circle cx="${r}" cy="${r}" r="${r * .72}" fill="none" stroke="${C.ink}" stroke-opacity=".35" stroke-dasharray="${size * .02} ${size * .025}" stroke-width="${Math.max(1, size * .012)}"/>` +
    inner + `</svg>`;
}
function scallopCanvas(g, cx, cy, outer, depth = .09, lobes = 16) {
  const inner = outer * (1 - depth), n = lobes * 12;
  g.beginPath();
  for (let i = 0; i <= n; i++) {
    const a = i / n * 2 * Math.PI - Math.PI / 2, w = (Math.cos(a * lobes) + 1) / 2, r = inner + (outer - inner) * w;
    i ? g.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r) : g.moveTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
  }
  g.closePath();
}

// ── Shuttlecock mark (ShuttlecockMark.swift) ────────────────────────────────
function shuttleSVG(size, skirt = C.card, cork = C.tomato, ink = C.ink, band = null) {
  const s = size, p = (x, y) => `${(x * s).toFixed(2)} ${(y * s).toFixed(2)}`;
  const tips = 6, topL = .12, topR = .88, topY = .12, baseL = .37, baseR = .63, baseY = .66;
  let d = `M${p(baseL, baseY)}L${p(topL, topY)}`;
  const st = (topR - topL) / tips;
  for (let i = 0; i < tips; i++) { const x0 = topL + i * st; d += `Q${p(x0 + st / 2, topY - .09)} ${p(x0 + st, topY)}`; }
  d += `L${p(baseR, baseY)}Z`;
  let ribs = "";
  for (let i = 1; i < tips; i++) { const t = i / tips; ribs += `M${p(baseL + (baseR - baseL) * t, baseY)}L${p(topL + (topR - topL) * t, topY)}`; }
  const bT = .42, bY = baseY + (topY - baseY) * bT;
  const bandD = `M${p(baseL + (topL - baseL) * bT, bY)}L${p(baseR + (topR - baseR) * bT, bY)}`;
  const sw = Math.max(1, s * .035);
  const corkD = `M${p(.33, baseY)}L${p(.67, baseY)}A${.17 * s} ${.17 * s} 0 0 1 ${p(.33, baseY)}Z`;
  return `<svg width="${s}" height="${s}" viewBox="0 0 ${s} ${s}" style="overflow:visible;display:block">` +
    `<path d="${d}" fill="${skirt}"/><path d="${ribs}" stroke="${ink}" stroke-opacity=".55" stroke-width="${Math.max(.8, s * .018)}" stroke-linecap="round"/>` +
    `<path d="${bandD}" stroke="${band || ink}" stroke-width="${Math.max(1, s * .05)}" stroke-linecap="round"/>` +
    `<path d="${d}" fill="none" stroke="${ink}" stroke-width="${sw}" stroke-linejoin="round"/>` +
    `<path d="${corkD}" fill="${cork}" stroke="${ink}" stroke-width="${sw}" stroke-linejoin="round"/></svg>`;
}

// ── Court (CourtPlan.swift): world metres, origin under the net, +x to the far baseline, +y left ──
const CG = { L: 6.70, Wd: 3.05, S: 2.59, SS: 1.98, LS: 5.94 };
const COURT_LINES = (() => {
  const { L, Wd, S, SS, LS } = CG, out = [];
  const ln = (a, b) => out.push([a, b]);
  ln([-L, Wd], [L, Wd]); ln([L, Wd], [L, -Wd]); ln([L, -Wd], [-L, -Wd]); ln([-L, -Wd], [-L, Wd]);
  ln([-L, S], [L, S]); ln([-L, -S], [L, -S]);
  for (const sx of [SS, -SS, LS, -LS]) ln([sx, Wd], [sx, -Wd]);
  ln([SS, 0], [L, 0]); ln([-SS, 0], [-L, 0]);
  return out;
})();

// Orbit camera. az: degrees around +z (0 = looking from the near baseline toward +x), el: degrees above the floor.
function makeCam({ az = 0, el = 30, dist = 18, target = [0, 0, 0.6], focal = 1500, cx = W / 2, cy = H / 2, roll = 0 }) {
  el = clamp(el, -89.5, 89.5);
  const A = az * Math.PI / 180, B = el * Math.PI / 180;
  const eye = [target[0] - Math.cos(B) * Math.cos(A) * dist, target[1] - Math.cos(B) * Math.sin(A) * dist, target[2] + Math.sin(B) * dist];
  const f = norm(sub(target, eye)), r = norm(cross(f, [0, 0, 1])), u = cross(r, f);
  const cr = Math.cos(roll * Math.PI / 180), sr = Math.sin(roll * Math.PI / 180);
  return {
    eye, focal,
    p(x, y, z = 0) {
      const d = [x - eye[0], y - eye[1], z - eye[2]];
      const zc = dot(d, f); const xc = dot(d, r), yc = dot(d, u);
      const k = focal / Math.max(0.05, zc);
      const X = xc * k, Y = -yc * k;
      return { x: cx + X * cr - Y * sr, y: cy + X * sr + Y * cr, k, z: zc };
    },
  };
}
function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
function cross(a, b) { return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
function norm(a) { const l = Math.hypot(...a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; }

function drawCourt(g, cam, { line = C.paper, width = 3, surface = null, net = true, draw = 1, alpha = 1 } = {}) {
  const { L, Wd } = CG;
  g.save(); g.globalAlpha = alpha;
  if (surface) {
    const q = [[-L, Wd], [L, Wd], [L, -Wd], [-L, -Wd]].map(p => cam.p(p[0], p[1], 0));
    g.fillStyle = surface; g.beginPath(); q.forEach((p, i) => i ? g.lineTo(p.x, p.y) : g.moveTo(p.x, p.y)); g.closePath(); g.fill();
  }
  g.strokeStyle = line; g.lineCap = "round";
  COURT_LINES.forEach(([a, b], i) => {
    const u = clamp(draw * COURT_LINES.length - i * 0.6);
    if (u <= 0) return;
    const pa = cam.p(a[0], a[1], 0), pb = cam.p(lerp(a[0], b[0], u), lerp(a[1], b[1], u), 0);
    g.lineWidth = width * Math.sqrt((pa.k + pb.k) / 2 / 100);
    g.beginPath(); g.moveTo(pa.x, pa.y); g.lineTo(pb.x, pb.y); g.stroke();
  });
  if (net && draw > 0.6) {
    const nu = clamp((draw - .6) / .4);
    const top = 1.55, Wn = Wd + 0.05;
    const p0 = cam.p(0, Wn, 0), p1 = cam.p(0, Wn, top * nu), p2 = cam.p(0, -Wn, top * nu), p3 = cam.p(0, -Wn, 0);
    g.lineWidth = width * 1.6 * Math.sqrt(p1.k / 100);
    g.beginPath(); g.moveTo(p0.x, p0.y); g.lineTo(p1.x, p1.y); g.lineTo(p2.x, p2.y); g.lineTo(p3.x, p3.y); g.stroke();
    g.setLineDash([2, 9]); g.lineWidth = width;
    for (let h = 0.3; h < top * nu; h += 0.25) {
      const a = cam.p(0, Wn, h), b = cam.p(0, -Wn, h);
      g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke();
    }
    g.setLineDash([]);
  }
  g.restore();
}

// ── Real rally (data.js) helpers ─────────────────────────────────────────────
// Shuttle world position at video time tau (seconds); null before the serve / after landing.
function shuttleAt(tau) {
  const f = tau * RALLY.fps - RALLY.f0;
  if (f < 0 || f > RALLY.shuttle.length - 1) return null;
  const i = Math.floor(f), u = f - i, a = RALLY.shuttle[i], b = RALLY.shuttle[Math.min(i + 1, RALLY.shuttle.length - 1)];
  return [lerp(a[0], b[0], u), lerp(a[1], b[1], u), lerp(a[2], b[2], u)];
}
// Player feet at tau: keyframes at each of that side's hits, recovering toward a base between them.
const PLAYER_KEYS = (() => {
  const keys = { near: [], far: [] };
  const base = { near: [-3.2, 0], far: [3.4, 0] };
  for (const s of ["near", "far"]) {
    const hs = RALLY.hits.filter(h => h.side === s);
    if (s === "far") keys[s].push([RALLY.hits[0].t - 0.4, base.far[0] + 0.6, -0.4]);
    hs.forEach((h, i) => {
      keys[s].push([h.t, h.pos[0], h.pos[1]]);
      const nx = hs[i + 1];
      if (nx) keys[s].push([(h.t + nx.t) / 2, lerp(h.pos[0], base[s][0], .6), lerp(h.pos[1], base[s][1], .6)]);
    });
    const last = hs[hs.length - 1];
    keys[s].push([last.t + 1.2, lerp(last.pos[0], base[s][0], .5), lerp(last.pos[1], base[s][1], .5)]);
  }
  return keys;
})();
function playerAt(side, tau) {
  const k = PLAYER_KEYS[side];
  if (tau <= k[0][0]) return [k[0][1], k[0][2]];
  for (let i = 0; i < k.length - 1; i++) {
    if (tau <= k[i + 1][0]) {
      const u = E.ioSine((tau - k[i][0]) / (k[i + 1][0] - k[i][0]));
      return [lerp(k[i][1], k[i + 1][1], u), lerp(k[i][2], k[i + 1][2], u)];
    }
  }
  const l = k[k.length - 1]; return [l[1], l[2]];
}

// ── Kinetic type ─────────────────────────────────────────────────────────────
// Each character sits in its own mask so it can be revealed, cut in, or knocked out independently.
function headline(parent, text, cls = "zh", style = {}) {
  const e = el("div", "abs " + cls, parent);
  css(e, style);
  const chars = [];
  for (const ch of text) {
    if (ch === "\n") { el("br", "", e); continue; }
    const m = el("span", "m", e), c = el("span", "ch", m, ch === " " ? "&nbsp;" : ch);
    chars.push(c);
  }
  return { el: e, chars };
}
// mode: "rise" (mask reveal from below), "cut" (appear on its tick with a 3-frame overshoot), "drop" (spring from above)
function typeIn(h, t, t0, stagger = 0.06, mode = "rise", out = null) {
  h.chars.forEach((c, i) => {
    const dt = t - t0 - i * stagger;
    let y = 0, s = 1, o = 1;
    if (mode === "rise") { const u = E.outExpo(clamp(dt / 0.45)); y = (1 - u) * 110; o = dt > 0 ? 1 : 0; }
    else if (mode === "cut") { o = dt >= 0 ? 1 : 0; s = dt < 0.05 ? 1.22 : 1; }
    else if (mode === "drop") { const u = spring(dt, 2.4, 0.45); y = (1 - u) * -140; o = dt > 0 ? 1 : 0; }
    if (out) {
      const du = t - out[0] - i * (out[2] ?? 0.03);
      if (out[1] === "fall") { const u = E.inCubic(clamp(du / 0.35)); y += u * 120; }
      else if (out[1] === "cut" && du >= 0) o = 0;
      else if (out[1] === "rise") { const u = E.inExpo(clamp(du / 0.4)); y -= u * 110; }
    }
    c.style.transform = `translateY(${y}%) scale(${s})`;
    c.style.opacity = o;
  });
}
