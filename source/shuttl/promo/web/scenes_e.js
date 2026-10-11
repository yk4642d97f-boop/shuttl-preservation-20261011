// Rally data + replay clock for S4. Contacts are real drag-physics flights between these points.
const R4 = rally([
  { from: [0.35, -2.2, 1.1], to: [-0.4, 2.3, 0.9], T: 0.95, kind: "serve", kmh: 48 },
  { from: [-0.4, 2.3, 0.9], to: [1.0, -5.9, 2.6], T: 1.25, kind: "lift", kmh: 139 },
  { from: [1.0, -5.9, 2.6], to: [-1.3, 3.0, 0.8], T: 0.40, kind: "smash", kmh: 241 },
  { from: [-1.3, 3.0, 0.8], to: [0.9, -1.6, 0.4], T: 0.90, kind: "block", kmh: 57 },
  { from: [0.9, -1.6, 0.4], to: [0.6, 5.3, 2.6], T: 1.30, kind: "lift", kmh: 117 },
  { from: [0.6, 5.3, 2.6], to: [1.9, -4.6, 0.0], T: 0.55, kind: "smash", kmh: 330, win: true },
]);
const RT0 = 26.95, TSM = RT0 + R4.shots[5].t0 + 0.02;
function rate4(t) {
  if (t < TSM) return 1;
  const down = lerp(1, 0.25, E.outSine(prog(t, TSM, TSM + 0.12)));
  return t < 34.0 ? down : lerp(0.25, 1, E.ioSine(prog(t, 34.0, 34.3)));
}
const RTAB = (() => { const a = [0]; let rt = 0; for (let t = RT0; t < 37.2; t += 0.001) { rt += rate4(t) * 0.001; a.push(rt); } return a; })();
const toRT = t => t <= RT0 ? t - RT0 : RTAB[Math.min(RTAB.length - 1, Math.round((t - RT0) * 1000))];
function toT(rt) {
  let lo = 0, hi = RTAB.length - 1;
  while (lo < hi) { const m = (lo + hi) >> 1; RTAB[m] < rt ? lo = m + 1 : hi = m; }
  return RT0 + lo / 1000;
}
const TLAND = toT(R4.T);
// Player feet keyframes [rally time, x, y, lift]
const NEAR = [[-9, 0.2, -2.6, 0], [0, 0.2, -2.6, 0], [0.7, 0.3, -3.6, 0], [1.9, 0.9, -5.3, 0], [2.2, 0.9, -5.4, 0.3], [2.45, 0.8, -5.2, 0],
  [3.0, 0.5, -3.0, 0], [3.5, 0.8, -2.2, 0], [4.3, 0.3, -3.6, 0], [4.8, 0.3, -3.7, 0], [5.35, 1.3, -4.2, 0], [9, 1.3, -4.2, 0]];
const FAR = [[-9, -0.5, 3.3, 0], [0.95, -0.5, 2.8, 0], [1.7, -0.3, 3.6, 0], [2.2, -0.6, 3.5, 0], [2.6, -1.2, 3.4, 0], [3.2, -0.4, 3.8, 0],
  [4.5, 0.4, 4.9, 0], [4.8, 0.5, 4.9, 0.45], [5.05, 0.45, 4.8, 0.05], [9, 0.3, 4.3, 0]];
function feet(K, rt) {
  let i = K.findIndex(k => k[0] > rt); if (i < 0) i = K.length - 1; if (i === 0) i = 1;
  const a = K[i - 1], b = K[i], u = E.ioSine(clamp((rt - a[0]) / (b[0] - a[0])));
  return [lerp(a[1], b[1], u), lerp(a[2], b[2], u), lerp(a[3], b[3], u)];
}
function drawPawn(g, cam, [x, y, lift], col) {
  const s = cam.p(x, y, 0), f = cam.p(x, y, 0.22 + lift), sh = cam.p(x, y, 1.16 + lift), hd = cam.p(x, y, 1.5 + lift), k = s[2];
  g.fillStyle = "rgba(0,0,0,.35)"; g.beginPath(); g.ellipse(s[0], s[1], 0.4 * k, 0.12 * k, 0, 0, 7); g.fill();
  g.lineCap = "round";
  g.strokeStyle = "#15121C"; g.lineWidth = 0.4 * k + 7; g.beginPath(); g.moveTo(f[0], f[1]); g.lineTo(sh[0], sh[1]); g.stroke();
  g.strokeStyle = col; g.lineWidth = 0.4 * k; g.beginPath(); g.moveTo(f[0], f[1]); g.lineTo(sh[0], sh[1]); g.stroke();
  g.fillStyle = col; g.strokeStyle = "#15121C"; g.lineWidth = 3.5;
  g.beginPath(); g.arc(hd[0], hd[1], 0.2 * k, 0, 7); g.fill(); g.stroke();
}
const CAM4 = () => camera([0, -13.8, 9.2], [0, -0.4, 0.6], 1700, 540, 990);
