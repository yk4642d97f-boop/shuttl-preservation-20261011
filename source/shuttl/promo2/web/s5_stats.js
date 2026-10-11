// ── S5 · 40–50 s · "看清" / "自己" / "怎么打。"
// Three hard cuts, three spot inks, three of the app's result cards blown up to poster size:
// shot mix (击球构成), landing map (落点地图), court movement (场上移动).
(() => {
  const P1 = 40.0, P2 = 43.0, P3 = 46.0, END = 50.0;
  const sectionHead = (folio, title, color = C.ink) =>
    `<div style="display:flex;align-items:center;gap:18px"><span style="font:700 24px SFMono;color:${C.tomatoText}">${folio}</span>` +
    `<span style="font:600 40px 'PingFang SC';-webkit-text-stroke:1px ${color};color:${color}">${title}</span>` +
    `<span style="flex:1;height:4px;background:${color};margin-left:12px"></span></div>`;
  const MIX = [["clear", .21], ["drop", .19], ["lift", .16], ["net", .13], ["smash", .11], ["push", .08], ["serve", .07], ["drive", .05]];
  // landing stamps (metres; +x far half), alternating winners
  const STAMPS = Array.from({ length: 22 }, (_, i) => {
    const far = hash(i * 4.1) > 0.45, deep = hash(i * 8.3) > 0.35;
    const x = (far ? 1 : -1) * (deep ? 4.6 + hash(i * 1.7) * 1.9 : 1.2 + hash(i * 2.2) * 2.2);
    const y = (hash(i * 6.6) - 0.5) * 5.4;
    return { x, y, near: hash(i * 3.3) > 0.5, n: i + 1 };
  });
  // movement density from the real rally's player paths
  const GRID = (() => {
    const nx = 26, ny = 12, d = { near: [], far: [] };
    for (const s of ["near", "far"]) {
      const g = Array(nx * ny).fill(0);
      for (let tau = RALLY.hits[0].t; tau < RALLY.f1 / RALLY.fps; tau += 1 / 30) {
        const [x, y] = playerAt(s, tau);
        for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
          const cx = -CG.L + (i + .5) * (2 * CG.L / nx), cy = CG.Wd - (j + .5) * (2 * CG.Wd / ny);
          g[j * nx + i] += Math.exp(-((cx - x) ** 2 + (cy - y) ** 2) / (2 * 0.8 ** 2));
        }
      }
      const m = Math.max(...g); d[s] = g.map(v => v / m);
    }
    return { nx, ny, d };
  })();

  // plan view helpers (court horizontal, near baseline on the left)
  const plan = (x0, y0, w) => { const h = w * CG.Wd / CG.L; return { x0, y0, w, h, p: (x, y) => [x0 + (x + CG.L) / (2 * CG.L) * w, y0 + (CG.Wd - y) / (2 * CG.Wd) * h] }; };
  function drawPlan(g, P, line, lw, net = true) {
    g.strokeStyle = line; g.lineWidth = lw; g.lineCap = "round";
    for (const [a, b] of COURT_LINES) { g.beginPath(); g.moveTo(...P.p(a[0], a[1])); g.lineTo(...P.p(b[0], b[1])); g.stroke(); }
    if (net) { g.save(); g.strokeStyle = C.ink; g.lineWidth = lw * 2.2; g.setLineDash([4, 7]); g.beginPath(); g.moveTo(...P.p(0, CG.Wd + .35)); g.lineTo(...P.p(0, -CG.Wd - .35)); g.stroke(); g.restore(); }
  }

  S({
    t0: P1, t1: END,
    build(root) {
      const c = this;
      c.bg = el("div", "fill", root);
      c.cv = canvas(root); c.g = c.cv.getContext("2d");
      // part 1
      c.k1 = el("div", "abs card", root);
      css(c.k1, { width: "1728px", height: "500px", borderWidth: "5px", borderRadius: "44px", boxShadow: `0 10px 0 ${C.ink}`, padding: "44px 56px", boxSizing: "border-box" });
      c.k1.innerHTML = sectionHead("02", "击球构成") +
        `<div class="bar" style="position:relative;margin-top:44px;height:104px;border-radius:52px;border:5px solid ${C.ink};overflow:hidden;display:flex;background:${C.paperDeep}"></div>` +
        `<div class="leg" style="display:flex;gap:26px;margin-top:40px"></div>`;
      c.segs = MIX.map(([k, w]) => { const s = el("div", "", c.k1.querySelector(".bar")); css(s, { width: w * 100 + "%", height: "100%", background: GLYPH[k].ink, borderRight: `5px solid ${C.ink}`, boxSizing: "border-box", transformOrigin: "0 50%" }); return s; });
      c.legs = MIX.map(([k]) => { const e = el("div", "", c.k1.querySelector(".leg"), `${chipHTML(k, 70)}<div style="font:600 24px 'PingFang SC';margin-top:10px;text-align:center">${GLYPH[k].zh}</div>`); return e; });
      c.w1 = headline(root, "看清", "zh", { fontSize: "380px", color: C.card });
      // part 2
      c.k2 = el("div", "abs card", root);
      css(c.k2, { width: "1560px", height: "640px", borderWidth: "5px", borderRadius: "44px", boxShadow: `0 10px 0 ${C.ink}`, padding: "36px 52px", boxSizing: "border-box" });
      c.k2.innerHTML = sectionHead("03", "落点地图");
      c.c2 = el("canvas", "abs", c.k2); c.c2.width = 1456; c.c2.height = 520; css(c.c2, { left: "52px", top: "100px" });
      c.w2 = headline(root, "自己", "zh", { fontSize: "380px", color: C.ink });
      // part 3
      c.k3 = el("div", "abs card", root);
      css(c.k3, { width: "1728px", height: "600px", borderWidth: "5px", borderRadius: "44px", boxShadow: `0 10px 0 ${C.ink}`, padding: "36px 52px", boxSizing: "border-box" });
      c.k3.innerHTML = sectionHead("04", "场上移动");
      c.c3 = el("canvas", "abs", c.k3); c.c3.width = 1624; c.c3.height = 480; css(c.c3, { left: "52px", top: "96px" });
      c.w3 = headline(root, "怎么打。", "zh", { fontSize: "300px", color: C.ink });
      // sound
      cue(P1, "impact", { pitch: 0 }); cue(P1 + 0.25, "key", { pitch: 3, gain: .9 });
      MIX.forEach((_, i) => cue(40.5 + i * 0.125, "blip", { pitch: i / 7 }));
      MIX.forEach((_, i) => cue(41.5 + i * 0.0625, "tick", { pitch: .4 + i * .1 }));
      cue(P2, "impact", { pitch: 1 }); cue(P2 + 0.25, "key", { pitch: 3.3, gain: .9 });
      const MEL = [0, 3, 5, 7, 10, 7, 5, 3, 0, 5, 7, 12, 10, 7, 5, 7, 3, 0, 5, 3, 7, 12];
      STAMPS.forEach((s, i) => cue(43.25 + i * 0.125, "stamp", { pitch: MEL[i % MEL.length] / 12 }));
      cue(P3, "impact", { pitch: 2 });
      [46.25, 46.375, 46.5, 46.625].forEach((t, i) => cue(t, "key", { pitch: 2.5 + i * .3, gain: .9 }));
      cue(46.3, "shimmer", { dur: 3.2 });
    },
    update(lt, tReal) {
      const c = this, g = c.g;
      // the tape-stop: picture freezes and sags while the music winds down
      const t = Math.min(tReal, 49.45);
      const sag = E.inCubic(prog(tReal, 49.45, 50.0));
      c.root.style.transform = sag > 0 ? `translateY(${sag * 90}px) scale(${1 - sag * 0.04})` : "";
      c.root.style.filter = sag > 0 ? `saturate(${1 - sag * 0.8})` : "";
      const part = t < P2 ? 1 : t < P3 ? 2 : 3;
      c.bg.style.background = part === 1 ? C.cobalt : part === 2 ? C.pistachio : C.paper;
      g.clearRect(0, 0, W, H);
      // ── part 1
      const in1 = spring(t - P1, 2.2, 0.5);
      put(c.k1, W / 2, lerp(1500, 745, in1), 1, -1.5, part === 1 ? 1 : 0);
      c.segs.forEach((s, i) => { const u = E.outExpo(prog(t, 40.5 + i * .125, 40.8 + i * .125)); s.style.transform = `scaleX(${u})`; });
      c.legs.forEach((e, i) => { const dt = t - 41.5 - i * .0625; e.style.transform = `scale(${dt < 0 ? 0 : 0.3 + 0.7 * spring(dt, 3.2, .4)}) rotate(${dt < 0 ? 0 : wob(dt, 2.5, 6) * 10}deg)`; });
      putTL(c.w1.el, 90, 30, 1, 0, part === 1 ? 1 : 0);
      typeIn(c.w1, t, P1, 0.25, "cut");
      // ── part 2
      const in2 = spring(t - P2, 2.4, 0.5);
      put(c.k2, 96 + 780, lerp(1400, 700, in2), 1, 1.2, part === 2 ? 1 : 0);
      if (part === 2) {
        const g2 = c.c2.getContext("2d"), PWd = 500 * CG.L / CG.Wd, P = plan((1456 - PWd) / 2, 10, PWd);
        g2.clearRect(0, 0, 1456, 520);
        g2.fillStyle = C.pistachio; g2.fillRect(P.x0, P.y0, P.w, P.h);
        drawPlan(g2, P, C.card, 5);
        STAMPS.forEach((s, i) => {
          const dt = t - 43.25 - i * 0.125; if (dt < 0) return;
          const [x, y] = P.p(s.x, s.y), k = 1 + 0.9 * Math.exp(-dt * 14), r = 30 * k;
          g2.save(); g2.translate(x, y); g2.rotate((hash(i) - .5) * .5 + 0.4 * Math.exp(-dt * 10));
          scallopCanvas(g2, 0, 0, r, .12, 12);
          g2.fillStyle = s.near ? C.cobalt : C.flamingo; g2.fill(); g2.lineWidth = 3.5; g2.strokeStyle = C.ink; g2.stroke();
          g2.fillStyle = s.near ? C.card : C.ink; g2.font = `900 ${Math.round(22 * k)}px NY`; g2.textAlign = "center"; g2.textBaseline = "middle";
          g2.fillText(String(s.n), 0, 1);
          g2.restore();
        });
      }
      putTL(c.w2.el, W - 2 * 0.955 * 380 - 80, 10, 1, 0, part === 2 ? 1 : 0);
      typeIn(c.w2, t, P2, 0.25, "cut");
      // ── part 3
      const in3 = spring(t - P3, 2.4, 0.5);
      put(c.k3, W / 2, lerp(-500, 380, in3), 1, -0.8, part === 3 ? 1 : 0);
      if (part === 3) {
        const g3 = c.c3.getContext("2d");
        const Ph = plan(16 + (1592 - 464 * CG.L / CG.Wd) / 2, 8, 464 * CG.L / CG.Wd);
        g3.clearRect(0, 0, 1624, 480);
        g3.fillStyle = C.paperDeep; g3.fillRect(Ph.x0, Ph.y0, Ph.w, Ph.h);
        const grow = E.outCubic(prog(t, 46.3, 47.8));
        const beat = Math.exp(-((t - P3) % 0.5) * 7) * prog(t, 47.5, 48);
        const { nx, ny, d } = GRID, cw = Ph.w / nx, ch = Ph.h / ny;
        for (const s of ["near", "far"]) {
          g3.fillStyle = s === "near" ? C.cobalt : C.flamingo;
          for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
            const v = d[s][j * nx + i]; if (v < 0.04) continue;
            const r = Math.min(cw, ch) * 0.5 * Math.sqrt(v) * grow * (1 + 0.18 * beat);
            const xx = Ph.x0 + (i + .5) * cw + (j % 2 ? cw * .25 : 0), yy = Ph.y0 + (j + .5) * ch;
            g3.beginPath(); g3.arc(xx, yy, r, 0, Math.PI * 2); g3.fill();
          }
        }
        drawPlan(g3, Ph, C.ink, 3.5);
      }
      putTL(c.w3.el, 90, 690, 1, 0, part === 3 ? 1 : 0);
      typeIn(c.w3, t, 46.25, 0.125, "cut");
      if (part === 3) shake(t, P3, 10, 0.25);
    },
  });
})();
