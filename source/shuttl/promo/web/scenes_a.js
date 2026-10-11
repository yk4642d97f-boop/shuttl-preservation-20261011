// ── S0 · Cold open (0 – 6.4 s): a smash lands, "330 km/h", the shuttle complains.
const FLOOR0 = 1650, TI = 0.55;
const S0P = { a: { x: 1240, y: -260 }, c: { x: 920, y: 150 }, b: { x: 560, y: 720 } };
const bez = (u, P = S0P) => ({
  x: (1 - u) ** 2 * P.a.x + 2 * u * (1 - u) * P.c.x + u * u * P.b.x,
  y: (1 - u) ** 2 * P.a.y + 2 * u * (1 - u) * P.c.y + u * u * P.b.y,
});
const flightU = t => lerp(0.36, 1, E.inSine(clamp(t / TI)));
S({
  t0: 0, t1: 6.4, z: 20,
  build(root) {
    const c = this;
    c.disc = el("div", "abs", root);
    css(c.disc, { width: "820px", height: "820px", borderRadius: "50%", background: "var(--tomato)", border: "5px solid var(--ink)", boxSizing: "border-box", overflow: "hidden" });
    css(el("div", "", c.disc), { position: "absolute", inset: 0, backgroundImage: "radial-gradient(rgba(34,27,46,.2) 2.2px, transparent 2.8px)", backgroundSize: "18px 18px", webkitMaskImage: "linear-gradient(150deg, transparent 45%, #000 95%)" });
    c.lab = el("div", "abs body", root, "一记扣杀，球速能到"); css(c.lab, { fontSize: "50px", fontWeight: 600, whiteSpace: "nowrap" });
    c.num = el("div", "num abs", root, "330"); css(c.num, { fontSize: "380px" });
    c.unit = el("div", "unit abs", root, "km/h"); css(c.unit, { fontSize: "96px", whiteSpace: "nowrap" });
    c.cv = canvas(root); c.g = c.cv.getContext("2d");
    c.h = headline(root, "快到，眼睛跟不上。"); c.h.el.style.fontSize = "104px";
    cue(0, "whoosh", { gain: 1, dur: 0.6 }); cue(TI, "thwack", { gain: 1.1 }); cue(TI, "boom", { gain: .8 });
    cue(1.25, "bump", { gain: .55 }); cue(1.6, "bump", { gain: .3 }); cue(1.95, "pop", { pitch: .2 });
    cue(2.8, "boing", { gain: .6 });
    BUBBLES.add(3.35, 4.25, "哎哟……又是我。", "r");
    BUBBLES.add(4.45, 5.5, "等等——这回有人在拍？", "r");
  },
  update(lt, t) {
    const c = this, g = c.g, out = E.inCubic(prog(t, 5.25, 5.85));
    shake(t, TI, 26, 0.5);
    const ds = spring(t - TI, 1.7, 0.42) * (1 - out);
    put(c.disc, 540, 720, ds, 0, ds > 0 ? 1 : 0);
    const ns = spring(t - TI - 0.04, 2.3, 0.36) * (1 - out);
    put(c.num, 540, 730, 0.3 + 0.7 * ns, -4 * ns + 10 * (1 - ns), clamp(ns * 3) * (1 - out));
    const us = spring(t - TI - 0.3, 2.6, 0.4) * (1 - out);
    put(c.unit, 735, 935, us, -6, clamp(us * 3));
    const ls = spring(t - TI - 0.42, 2.6, 0.45) * (1 - out);
    put(c.lab, 540, 470, 1, 0, clamp(ls * 2) * (1 - out)); c.lab.style.transform += ` translateY(${(1 - ls) * 30}px)`;
    put(c.h.el, 540, 1250, 1, 0, 1);
    popChars(c.h, t, 1.85, 0.05, 5.2);
    // canvas: trail, burst, shadow, dizzy stars
    g.clearRect(0, 0, W, H); g.globalAlpha = 1 - out;
    const uh = flightU(t), ut = t < TI ? Math.max(0, uh - 0.5) : lerp(0.5, 1, E.outCubic(prog(t, TI, TI + 0.35)));
    if (ut < uh - 0.001) {
      g.lineCap = "round";
      const n = 40;
      for (let i = 0; i < n; i++) {
        const k0 = i / n, k1 = (i + 1) / n, a = bez(lerp(ut, uh, k0)), b = bez(lerp(ut, uh, k1));
        g.strokeStyle = k0 > 0.5 ? "#F2542D" : "#221B2E"; g.lineWidth = 4 + 40 * Math.pow(k1, 1.3);
        g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke();
      }
    }
    const bu = prog(t, TI, TI + 0.55);
    if (bu > 0 && bu < 1) {
      const cols = ["#221B2E", "#F7D95C", "#2F4BDE", "#221B2E", "#FF7AB6", "#B9D66A"];
      for (let i = 0; i < 16; i++) {
        const a = i / 16 * 2 * Math.PI + hash(i) * 0.3, r0 = 110 + 330 * E.outExpo(bu), len = 90 * (1 - bu) + 8;
        g.strokeStyle = cols[i % cols.length]; g.lineWidth = 16 * (1 - bu) + 2;
        g.beginPath(); g.moveTo(560 + Math.cos(a) * r0, 720 + Math.sin(a) * r0); g.lineTo(560 + Math.cos(a) * (r0 + len), 720 + Math.sin(a) * (r0 + len)); g.stroke();
      }
    }
    const p = this.pose(lt, t);
    if (t > TI + 0.2) {
      const hgt = clamp((FLOOR0 - 60 - p.y) / 500), sw = 150 * (1 - 0.6 * hgt);
      g.fillStyle = `rgba(34,27,46,${0.14 * (1 - hgt)})`; g.beginPath(); g.ellipse(p.x, FLOOR0 + 6, sw, sw * 0.14, 0, 0, 2 * Math.PI); g.fill();
    }
    if (t > 1.5 && t < 3.0) {
      const k = clamp((t - 1.5) * 4) * clamp((3.0 - t) * 5);
      for (let i = 0; i < 3; i++) {
        const a = t * 5 + i * 2.09, sx = p.x - 80 + Math.cos(a) * 95, sy = p.y - 70 + Math.sin(a) * 26;
        star(g, sx, sy, 30 * k, "#F7D95C");
      }
    }
    g.globalAlpha = 1;
  },
  pose(lt, t) {
    const I = idle(t, 0.4), stand = FLOOR0 - 67, lie = FLOOR0 - 104;
    if (t < TI) {
      const u = flightU(t), p = bez(u), p2 = bez(Math.min(1, u + 0.01)), p1 = bez(Math.max(0, u - 0.01));
      const r = Math.atan2(p2.y - p1.y, p2.x - p1.x) * 180 / Math.PI - 90;
      return { x: p.x, y: p.y, s: 1.08, r, sq: -0.28, mood: "squint", wig: -6 };
    }
    if (t < 1.25) { const h = hop(t, TI, 1.25, S0P.b, { x: 360, y: lie }, 300); return Object.assign(h, { r: lerp(28.7, 450, E.outCubic(prog(t, TI, 1.6))), mood: "dizzy", sq: h.sq + wob(t - TI, 4, 7) * 0.3, wig: 10 * wob(t - TI, 5, 4) }); }
    if (t < 2.75) { const h = hop(t, 1.25, 1.6, { x: 360, y: lie }, { x: 335, y: lie }, 70); return Object.assign(h, { r: lerp(28.7, 450, E.outCubic(prog(t, TI, 1.6))), mood: "dizzy", wig: 4 * Math.sin(t * 9) }); }
    const up = spring(t - 2.75, 2.2, 0.4), y = lerp(lie, stand, up) - 70 * Math.sin(Math.PI * clamp((t - 2.75) / 0.3));
    const look = t < 4.2 ? 0 : t < 4.42 ? Math.sin((t - 4.2) / 0.22 * Math.PI * 2) : 0;
    const mood = t < 2.9 ? "dizzy" : t < 3.3 ? "wow" : t < 4.3 ? "normal" : "wow";
    return Object.assign(I, { x: 335, y, r: lerp(450, 360, up), mood, lx: look, ly: t > 4.42 ? -0.2 : 0, s: 1 });
  },
});
function star(g, x, y, r, col) {
  if (r <= 0.5) return;
  g.beginPath();
  for (let i = 0; i < 10; i++) { const a = i * Math.PI / 5 - Math.PI / 2, rr = i % 2 ? r * 0.45 : r; g.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr); }
  g.closePath(); g.fillStyle = col; g.fill(); g.strokeStyle = "#221B2E"; g.lineWidth = 3; g.stroke();
}
