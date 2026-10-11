// World frame (metres): x across the court, y along it (near baseline y = -6.7), z up. BWF dimensions.
const CT = { L: 6.7, D: 3.05, SG: 2.59, SS: 1.98, LDL: 5.94, NET: 1.524, POST: 1.55 };

function camera(eye, target, focal, cx = W / 2, cy = H / 2) {
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const nrm = a => { const l = Math.hypot(...a); return [a[0] / l, a[1] / l, a[2] / l]; };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const f = nrm(sub(target, eye)), r = nrm(cross(f, [0, 0, 1])), u = cross(r, f);
  return {
    eye, f, r, u,
    p(x, y, z = 0) {
      const d = sub([x, y, z], eye), zc = Math.max(0.05, dot(d, f));
      return [cx + focal * dot(d, r) / zc, cy - focal * dot(d, u) / zc, focal / zc];
    },
  };
}
function lerpCam(a, b, u) {
  const L3 = (p, q) => p.map((v, i) => lerp(v, q[i], u));
  return [L3(a[0], b[0]), L3(a[1], b[1]), lerp(a[2], b[2], u)];
}
function poly(g, cam, pts, fill, stroke, lw = 3) {
  g.beginPath();
  pts.forEach(([x, y, z], i) => { const [px, py] = cam.p(x, y, z || 0); i ? g.lineTo(px, py) : g.moveTo(px, py); });
  g.closePath();
  if (fill) { g.fillStyle = fill; g.fill(); }
  if (stroke) { g.strokeStyle = stroke; g.lineWidth = lw; g.lineJoin = "round"; g.stroke(); }
}
// Court lines drawn as thin world-space quads so they foreshorten. reveal 0..1 draws them on in order.
function courtLines() {
  const { L, D, SG, SS, LDL } = CT, s = [];
  for (const y of [-L, L]) s.push([-D, y, D, y]);
  for (const y of [-SS, SS]) s.push([-D, y, D, y]);
  for (const y of [-LDL, LDL]) s.push([-D, y, D, y]);
  for (const x of [-D, D, -SG, SG]) s.push([x, -L, x, L]);
  s.push([0, SS, 0, L]); s.push([0, -L, 0, -SS]);
  return s;
}
const COURT_LINES = courtLines();
function drawCourt(g, cam, o = {}) {
  const { L, D } = CT, felt = o.felt || "#1F4A3A", line = o.line || "rgba(244,238,227,.82)", lw = o.lw ?? 0.04;
  if (o.apron) poly(g, cam, [[-D - 1.6, -L - 2.2], [D + 1.6, -L - 2.2], [D + 1.6, L + 2.2], [-D - 1.6, L + 2.2]], o.apron);
  poly(g, cam, [[-D, -L], [D, -L], [D, L], [-D, L]], felt, o.edge, o.edgeW ?? 4);
  const rev = o.reveal ?? 1, n = COURT_LINES.length;
  g.fillStyle = line;
  COURT_LINES.forEach(([x1, y1, x2, y2], i) => {
    const u = clamp(rev * n - i);
    if (u <= 0) return;
    const xe = lerp(x1, x2, u), ye = lerp(y1, y2, u), h = lw / 2;
    const vert = x1 === x2;
    const q = vert ? [[x1 - h, y1], [x1 + h, y1], [xe + h, ye], [xe - h, ye]] : [[x1, y1 - h], [x1, y1 + h], [xe, ye + h], [xe, ye - h]];
    poly(g, cam, q, line);
  });
}
function drawNet(g, cam, o = {}) {
  const { D, NET, POST } = CT, m = D + 0.02;
  poly(g, cam, [[-m, 0, 0.76], [m, 0, 0.76], [m, 0, NET], [-m, 0, NET]], o.mesh || "rgba(244,238,227,.16)");
  const a = cam.p(-m, 0, NET), b = cam.p(m, 0, NET);
  g.strokeStyle = o.tape || "#F4EEE3"; g.lineWidth = o.tapeW ?? 5; g.lineCap = "round";
  g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
  for (const x of [-m, m]) {
    const p0 = cam.p(x, 0, 0), p1 = cam.p(x, 0, POST);
    g.strokeStyle = o.post || "#F4EEE3"; g.lineWidth = o.postW ?? 6;
    g.beginPath(); g.moveTo(p0[0], p0[1]); g.lineTo(p1[0], p1[1]); g.stroke();
  }
}

// Shuttle flight with quadratic drag (terminal velocity ~6.8 m/s): a = g - k|v|v.
const KDRAG = 9.81 / (6.8 * 6.8), DT = 1 / 240;
function fly(p0, v0, T) {
  const pts = [p0.slice()]; let p = p0.slice(), v = v0.slice();
  for (let i = 0, n = Math.round(T / DT); i < n; i++) {
    const s = Math.hypot(...v);
    v = [v[0] - KDRAG * s * v[0] * DT, v[1] - KDRAG * s * v[1] * DT, v[2] - (9.81 + KDRAG * s * v[2]) * DT];
    p = [p[0] + v[0] * DT, p[1] + v[1] * DT, p[2] + v[2] * DT];
    pts.push(p);
  }
  return pts;
}
// Newton shooting: find v0 so that the flight from a reaches b after T seconds.
function solveShot(a, b, T) {
  let v = [(b[0] - a[0]) / T, (b[1] - a[1]) / T, (b[2] - a[2]) / T + 4.9 * T];
  for (let it = 0; it < 30; it++) {
    const end = fly(a, v, T).at(-1), err = [end[0] - b[0], end[1] - b[1], end[2] - b[2]];
    if (Math.hypot(...err) < 1e-3) break;
    const J = [0, 1, 2].map(k => { const dv = v.slice(); dv[k] += 1e-3; const e2 = fly(a, dv, T).at(-1); return [(e2[0] - end[0]) / 1e-3, (e2[1] - end[1]) / 1e-3, (e2[2] - end[2]) / 1e-3]; });
    // Solve J^T columns: J[k] = d(end)/d(v_k). Build 3x3 and invert (Cramer).
    const M = [[J[0][0], J[1][0], J[2][0]], [J[0][1], J[1][1], J[2][1]], [J[0][2], J[1][2], J[2][2]]];
    const det = m => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
    const D0 = det(M), dx = [0, 1, 2].map(c => det(M.map((row, r) => row.map((x, j) => j === c ? err[r] : x))) / D0);
    v = [v[0] - dx[0], v[1] - dx[1], v[2] - dx[2]];
  }
  return v;
}
// Rally: shots [{from:[x,y,z], to:[x,y,z], T, kind, label}] chained in time.
function rally(shots) {
  let t = 0;
  const out = shots.map(s => {
    const v0 = solveShot(s.from, s.to, s.T), pts = fly(s.from, v0, s.T);
    const r = Object.assign({}, s, { t0: t, t1: t + s.T, pts, v0, kmh: s.kmh ?? Math.round(Math.hypot(...v0) * 3.6) });
    t += s.T; return r;
  });
  return { shots: out, T: t };
}
function rallyAt(R, rt) {
  const s = R.shots.find(s => rt < s.t1) || R.shots.at(-1);
  const i = clamp((rt - s.t0) / DT, 0, s.pts.length - 1), i0 = Math.floor(i), i1 = Math.min(i0 + 1, s.pts.length - 1), f = i - i0;
  const a = s.pts[i0], b = s.pts[i1];
  return { p: [lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)], shot: s, v: [(b[0] - a[0]) / DT, (b[1] - a[1]) / DT, (b[2] - a[2]) / DT] };
}
// Tapered trail: ink/paper tail → tomato head, width by age. win = seconds of history drawn.
function drawTrail(g, cam, R, rt, win = 1.1, o = {}) {
  const pts = [];
  for (const s of R.shots) {
    if (s.t0 > rt) break;
    const step = 3;
    for (let i = 0; i < s.pts.length; i += step) { const tt = s.t0 + i * DT; if (tt > rt) break; if (rt - tt <= win) pts.push([s.pts[i], tt]); }
  }
  const head = rallyAt(R, rt).p; pts.push([head, rt]);
  if (pts.length < 2) return;
  const P = pts.map(([p, tt]) => [cam.p(...p), rt - tt]);
  g.lineCap = "round"; g.lineJoin = "round";
  for (let pass = 0; pass < 2; pass++) for (let i = 1; i < P.length; i++) {
    const [[x0, y0, s0], age] = P[i - 1], [[x1, y1]] = P[i], k = 1 - age / win;
    const w = (o.w ?? 0.09) * s0 * (0.25 + 0.75 * k) + (o.min ?? 2);
    g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1);
    if (pass === 0) { g.strokeStyle = o.outline || "rgba(21,18,28,.85)"; g.lineWidth = w + (o.ow ?? 5); }
    else { g.strokeStyle = k > (o.hot ?? 0.55) ? "#F2542D" : (o.cool || `rgba(244,238,227,${0.25 + 0.6 * k})`); g.lineWidth = w; }
    g.stroke();
  }
}
