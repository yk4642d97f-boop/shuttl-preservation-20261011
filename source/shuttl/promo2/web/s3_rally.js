// ── S3 · 14–30 s · the real rally, re-drawn from the cloud analysis output (no footage).
// It plays in real time, so the thirteen hits are the rhythm. Each "plate" adds one layer of what the
// analysis knows: 1 the ball, frame by frame · 2 the court · 3 the players · 4 the shots.
(() => {
  const H0 = RALLY.hits[0].t, OFF = 15.0 - H0;           // first hit lands at 15.0 s
  const tauOf = t => t - OFF;
  const TEND = RALLY.f1 / RALLY.fps, LAND = TEND + OFF;   // landing ≈ 28.63 s
  const PLATE2 = 18.0, PLATE3 = 20.0, PLATE4 = 20.4;
  const HITS = RALLY.hits.map((h, i) => ({ ...h, i, T: h.t + OFF, pos3: shuttleAt(h.t + 1e-4) || [h.pos[0], h.pos[1], 1] }));
  const FLASH = HITS.filter(h => h.T >= PLATE4 && h.ok);

  const KEYS = [
    [14.0, { az: 90, el: 86, dist: 19, tz: 0.0 }],
    [17.6, { az: 84, el: 66, dist: 19, tz: 0.2 }],
    [20.8, { az: 92, el: 9, dist: 19, tz: 1.3 }],
    [24.8, { az: 32, el: 19, dist: 17.5, tz: 0.9 }],
    [28.4, { az: -4, el: 30, dist: 16.5, tz: 0.6 }],
    [29.95, { az: 90, el: 87, dist: 23, tz: 0.0 }],
  ];
  const camAt = t => {
    let a = KEYS[0][1], b = a, u = 0;
    for (let i = 0; i < KEYS.length - 1; i++) if (t >= KEYS[i][0]) { a = KEYS[i][1]; b = KEYS[i + 1][1]; u = E.ioCubic(prog(t, KEYS[i][0], KEYS[i + 1][0])); }
    const m = k => lerp(a[k], b[k], u);
    return makeCam({ az: m("az"), el: m("el"), dist: m("dist"), target: [0, 0, m("tz")], focal: 1700, cx: W / 2, cy: H / 2 + 30 });
  };
  const hex = h => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const TR = [C.lilac, C.tomato, C.butter].map(hex);
  const trail = u => { const s = u * 2, i = Math.min(1, Math.floor(s)), f = s - i; const a = TR[i], b = TR[i + 1]; return `rgb(${a.map((v, k) => Math.round(lerp(v, b[k], f))).join(",")})`; };

  S({
    t0: 14.0, t1: 30.0,
    build(root) {
      const c = this;
      css(root, { background: C.night });
      c.cv = canvas(root); c.g = c.cv.getContext("2d");
      c.labels = HITS.map(h => {
        if (!h.ok) return null;
        const G = GLYPH[h.glyph];
        const e = el("div", "abs", root,
          `<div style="display:flex;align-items:center;gap:10px;padding:8px 18px 8px 12px;background:${G.ink};border:3px solid ${C.ink};border-radius:99px;` +
          `font:600 30px 'PingFang SC';-webkit-text-stroke:.6px ${onInk(h.glyph)};color:${onInk(h.glyph)};white-space:nowrap">${glyphSVG(h.glyph, onInk(h.glyph), 34, false)}${G.zh}</div>`);
        return e;
      });
      c.hud = el("div", "abs mono", root, ""); css(c.hud, { fontSize: "18px", color: C.paper, textAlign: "right" });
      c.plate = el("div", "abs mono", root, ""); css(c.plate, { fontSize: "18px", color: C.paper });
      c.h1 = headline(root, "找到球。", "zh", { fontSize: "130px", color: C.paper });
      c.h2 = headline(root, "一拍一拍，\n认出来。", "zh", { fontSize: "130px", color: C.paper, lineHeight: "1.12" });
      c.flash = el("div", "fill", root); css(c.flash, { zIndex: 50 });
      c.flashG = el("div", "abs", c.flash);
      c.seal = el("div", "abs", root, sealSVG(120, C.pistachio, `<circle cx="60" cy="60" r="10" fill="${C.ink}"/>`));
      // sound
      [14.35, 14.45, 14.55, 14.65].forEach((t, i) => cue(t, "key", { pitch: 2.2 + i * .3, gain: .7 }));
      HITS.forEach(h => cue(h.T, "thwack", { pitch: h.side === "near" ? 1.0 : 0.6, gain: h.T >= PLATE4 ? 1.0 : 0.8 }));
      FLASH.forEach(h => cue(h.T, "stab", { pitch: GLYPH_KINDS.indexOf(h.glyph) }));
      cue(PLATE2, "plate", { pitch: 0 }); cue(PLATE3, "plate", { pitch: 1 }); cue(PLATE4 - 0.02, "plate", { pitch: 2 });
      cue(LAND, "slam", { gain: 1.2 }); cue(LAND, "boom", { gain: 1.1 });
      [20.6, 20.725, 20.85, 20.975, 21.1].forEach((t, i) => cue(t, "key", { pitch: 1.5 + i * .25, gain: .6 }));
      [21.6, 21.725, 21.85, 21.975].forEach((t, i) => cue(t, "key", { pitch: 2.5 + i * .25, gain: .6 }));
    },
    update(lt, t) {
      const c = this, g = c.g;
      const tau = Math.min(tauOf(t), TEND);
      const frozen = t >= LAND;
      const cam = camAt(t);
      g.clearRect(0, 0, W, H);
      // plate 2 · the court is printed
      if (t >= PLATE2) {
        const d = E.outExpo(prog(t, PLATE2, PLATE2 + 0.9));
        drawCourt(g, cam, { line: "rgba(244,238,227,.75)", width: 2.4, surface: t >= PLATE2 ? C.courtNight : null, draw: d });
      }
      const fNow = tau * RALLY.fps - RALLY.f0;
      const nF = Math.max(0, Math.min(RALLY.shuttle.length - 1, Math.floor(fNow)));
      const pts = [];
      for (let i = 0; i <= nF && fNow >= 0; i++) pts.push(cam.p(...RALLY.shuttle[i]));
      const head = fNow >= 0 ? shuttleAt(tau) : null;
      // ground shadow
      if (head && t >= PLATE2 && !frozen) {
        const s = cam.p(head[0], head[1], 0);
        g.fillStyle = "rgba(0,0,0,.35)"; g.beginPath(); g.ellipse(s.x, s.y, 0.12 * s.k, 0.05 * s.k, 0, 0, Math.PI * 2); g.fill();
      }
      // plate 3 · players
      if (t >= PLATE3) {
        const pin = E.outBack(prog(t, PLATE3, PLATE3 + 0.35));
        for (const side of ["far", "near"]) {
          const [x, y] = playerAt(side, tau), a = cam.p(x, y, 0), b = cam.p(x, y, 1.6 * pin), hd = cam.p(x, y, 1.82 * pin);
          const col = side === "near" ? C.cobalt : C.flamingo;
          g.fillStyle = "rgba(0,0,0,.3)"; g.beginPath(); g.ellipse(a.x, a.y, 0.45 * a.k, 0.16 * a.k, 0, 0, Math.PI * 2); g.fill();
          g.strokeStyle = col; g.lineCap = "round"; g.lineWidth = 0.38 * a.k;
          g.beginPath(); g.moveTo(a.x, a.y - 0.1 * a.k); g.lineTo(b.x, b.y); g.stroke();
          g.fillStyle = col; g.beginPath(); g.arc(hd.x, hd.y, 0.2 * hd.k, 0, Math.PI * 2); g.fill();
        }
      }
      // plate 1 · every frame a dot; from plate 2 the dots join into a flight
      if (pts.length) {
        if (t >= PLATE2) {
          const lu = E.outCubic(prog(t, PLATE2, PLATE2 + 0.6));
          g.strokeStyle = `rgba(244,238,227,${0.42 * lu})`; g.lineWidth = 2; g.lineJoin = "round";
          g.beginPath(); pts.forEach((p, i) => i ? g.lineTo(p.x, p.y) : g.moveTo(p.x, p.y)); g.stroke();
        }
        g.fillStyle = C.paper;
        const dotR = t >= PLATE2 ? 0.035 : 0.075;
        for (const p of pts) { g.beginPath(); g.arc(p.x, p.y, Math.max(2, dotR * p.k), 0, Math.PI * 2); g.fill(); }
        if (t >= PLATE2 && !frozen) {
          const n = Math.min(pts.length - 1, 16);
          g.lineCap = "round";
          for (let k = 0; k < n; k++) {
            const a = pts[pts.length - 1 - n + k], b = pts[pts.length - n + k], u = (k + 1) / n;
            g.strokeStyle = trail(u); g.lineWidth = (2 + 0.11 * b.k * u);
            g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke();
          }
        }
        if (head && !frozen) {
          const q = cam.p(...head);
          g.fillStyle = C.butter; g.beginPath(); g.arc(q.x, q.y, Math.max(6, 0.1 * q.k), 0, Math.PI * 2); g.fill();
        }
      }
      // hit rings + timeline ticks
      const TL0 = 160, TL1 = 1760, TLY = 1010;
      const tlx = tt => lerp(TL0, TL1, (tt - (RALLY.f0 / RALLY.fps)) / (TEND - RALLY.f0 / RALLY.fps));
      g.strokeStyle = "rgba(244,238,227,.3)"; g.lineWidth = 2;
      g.beginPath(); g.moveTo(TL0, TLY); g.lineTo(TL1, TLY); g.stroke();
      for (const h of HITS) {
        if (t < h.T) continue;
        const u = prog(t, h.T, h.T + 0.5);
        if (u < 1) {
          const q = cam.p(...h.pos3);
          g.strokeStyle = `rgba(244,238,227,${1 - u})`; g.lineWidth = 4 * (1 - u) + 1;
          g.beginPath(); g.arc(q.x, q.y, 10 + 90 * E.outExpo(u), 0, Math.PI * 2); g.stroke();
        }
        const x = tlx(h.t), col = h.ok && h.T >= PLATE4 ? GLYPH[h.glyph].ink : C.paper;
        g.fillStyle = col; g.fillRect(x - 3, TLY - 18, 6, 36);
      }
      g.fillStyle = C.tomato; g.fillRect(tlx(Math.max(RALLY.f0 / RALLY.fps, tau)) - 2, TLY - 28, 4, 56);
      // shot labels (plate 4), as the app's replay labels them
      c.labels.forEach((e, i) => {
        if (!e) return;
        const h = HITS[i], dt = t - h.T;
        if (h.T < PLATE4 || dt < 0 || dt > 1.25) { vis(e, false); return; }
        const q = cam.p(...h.pos3), s = spring(dt, 3, 0.45) * (1 - E.inCubic(prog(dt, 1.05, 1.25)));
        put(e, q.x, q.y - 80, s, -3);
      });
      // registration marks
      if (t >= PLATE2) {
        g.strokeStyle = t >= PLATE4 ? C.paper : "rgba(244,238,227,.6)"; g.lineWidth = 2;
        for (const [x, y] of [[64, 64], [W - 64, 64], [64, H - 140], [W - 64, H - 140]]) {
          g.beginPath(); g.arc(x, y, 13, 0, Math.PI * 2); g.moveTo(x - 24, y); g.lineTo(x + 24, y); g.moveTo(x, y - 24); g.lineTo(x, y + 24); g.stroke();
        }
      }
      const plateTxt = t < PLATE2 ? "PLATE 1 · BALL" : t < PLATE3 ? "PLATE 2 · COURT" : t < PLATE4 ? "PLATE 3 · PLAYERS" : "PLATE 4 · SHOTS";
      c.plate.textContent = plateTxt; putTL(c.plate, TL0, TLY + 30);
      const fr = Math.max(0, Math.round(tau * RALLY.fps));
      c.hud.innerHTML = `F ${String(fr).padStart(4, "0")}<br>${HITS.filter(h => t >= h.T).length.toString().padStart(2, "0")} / 13 HITS`;
      putTL(c.hud, W - 300, 80); c.hud.style.width = "236px";
      // landing stamp
      if (frozen) {
        const lq = cam.p(RALLY.landing[0], RALLY.landing[1], 0), s = spring(t - LAND, 2.6, 0.38);
        put(c.seal, lq.x, lq.y, 0.4 + 0.6 * s, 12 - 12 * s, 1);
        shake(t, LAND, 34, 0.5);
      } else vis(c.seal, false);
      // type
      putTL(c.h1.el, 110, 92, 1, 0, t < 17.9 ? 1 : 0);
      typeIn(c.h1, t, 14.35, 0.1, "rise", [17.45, "rise", 0.04]);
      putTL(c.h2.el, 110, 92, 1, 0, t > 20.5 && t < 25.6 ? 1 : 0);
      typeIn(c.h2, t, 20.6, 0.125, "cut", [25.1, "fall", 0.03]);
      c.h2.chars.forEach((ch, i) => { if (i >= 5 && t < 21.6 + (i - 5) * 0.125) ch.style.opacity = 0; });
      // strobe: the shot's ink fills the frame for five frames with its pictogram
      const fh = FLASH.find(h => t >= h.T && t < h.T + 5 / 60);
      if (fh) {
        c.flash.style.background = GLYPH[fh.glyph].ink;
        if (c._fk !== fh.i) { c.flashG.innerHTML = glyphSVG(fh.glyph, onInk(fh.glyph), 560); c._fk = fh.i; }
        put(c.flashG, W / 2, H / 2 - 10, 1, 0, 1);
        c.flash.style.display = "block";
      } else c.flash.style.display = "none";
    },
  });
})();
