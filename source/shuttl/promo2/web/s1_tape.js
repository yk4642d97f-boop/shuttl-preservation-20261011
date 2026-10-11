// ── S1 · 0–6 s · "那一拍，藏在四十分钟里。"
// A forty-minute match as a barcode of rallies. The playhead hunts, the phrase stretches to the length
// of the tape, the playhead locks onto one tomato bar, and we zoom into it until it is the whole frame.
(() => {
  const MATCH = 2400;                        // seconds of tape
  const X0 = 120, X1 = 1800, BY = 560, BH = 170;
  const tx = s => X0 + (s / MATCH) * (X1 - X0);
  // Deterministic rallies: [start, length] in tape seconds.
  const RALLIES = [];
  for (let s = 40, i = 0; s < MATCH - 20; i++) {
    const len = 4 + 26 * Math.pow(hash(i * 3.1), 1.6);
    RALLIES.push([s, len]);
    s += len + 9 + 34 * hash(i * 7.7 + 2);
  }
  const TARGET = RALLIES.reduce((b, r) => Math.abs(r[0] - 1730) < Math.abs(b[0] - 1730) ? r : b);
  const TC = TARGET[0] + TARGET[1] / 2;
  // Playhead search path (tape seconds), keyed in film time.
  const KEYS = [[0, 260], [0.45, 1480], [0.8, 820], [1.1, 1990], [1.45, 1290], [1.8, 2210], [2.15, 1610], [2.5, 1930],
    [2.85, 1580], [3.2, 1840], [3.55, 1690], [3.9, TC + 16], [4.2, TC]];
  const head = t => {
    if (t <= KEYS[0][0]) return KEYS[0][1];
    for (let i = 0; i < KEYS.length - 1; i++)
      if (t <= KEYS[i + 1][0]) return lerp(KEYS[i][1], KEYS[i + 1][1], E.ioQuint((t - KEYS[i][0]) / (KEYS[i + 1][0] - KEYS[i][0])));
    return TC;
  };
  const LOCK = 4.2, ZOOM0 = 4.45, ZOOM1 = 5.8;
  const tcode = s => { s = Math.max(0, Math.round(s)); return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); };

  // Line 1 + line 2 as individually placed characters so "四十分钟" can stretch along the tape.
  const FS1 = 150, FS2 = 108;
  S({
    t0: 0, t1: 6.0,
    build(root) {
      const c = this;
      css(root, { background: C.paper });
      c.cv = canvas(root); c.g = c.cv.getContext("2d");
      c.big = el("div", "abs ny", root, "00:00");
      css(c.big, { fontSize: "430px", color: "transparent", webkitTextStroke: `3px ${C.ink}`, letterSpacing: "-0.02em" });
      c.h1 = headline(root, "那一拍，", "zh", { fontSize: FS1 + "px" });
      c.l2 = [..."藏在四十分钟里。"].map(ch => { const e = el("div", "abs zh", root, ch); css(e, { fontSize: FS2 + "px" }); return e; });
      c.ticks = [0, 600, 1200, 1800, 2400].map(s => { const e = el("div", "abs mono", root, tcode(s)); css(e, { fontSize: "17px", color: C.inkSoft }); return e; });
      c.tag = el("div", "abs mono", root, "REC · 40:00 · 1 TAPE"); css(c.tag, { fontSize: "17px", color: C.inkSoft });
      // sound: the scrub is rendered from the playhead's own speed; ticks on line entrances.
      const v = []; for (let f = 0; f <= LOCK * 60; f++) v.push(+((head((f + 1) / 60) - head(f / 60)) * 60 / MATCH).toFixed(4));
      cue(0, "scrub", { rate: 60, v });
      [0.9, 1.0, 1.1, 1.2].forEach((t, i) => cue(t, "key", { pitch: i }));
      [2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.0, 3.1].forEach((t, i) => cue(t, "key", { pitch: (i % 4) * .7 }));
      cue(2.95, "stretch", { dur: 0.6 });
      cue(LOCK, "lock"); cue(ZOOM0, "rise", { dur: ZOOM1 - ZOOM0 + 0.05 });
    },
    update(lt, t) {
      const c = this, g = c.g;
      const zoom = Math.exp(Math.log(420) * E.inExpo(prog(t, ZOOM0, ZOOM1)));
      const hz = t < LOCK ? head(t) : TC;
      const cxT = tx(TC);
      const anchor = lerp(cxT, W / 2, E.ioCubic(prog(t, ZOOM0, ZOOM0 + 0.7)));
      const X = x => anchor + (x - cxT) * zoom;
      const bandGrow = E.outExpo(prog(t, ZOOM0, ZOOM1));
      const by = lerp(BY, 0, bandGrow), bh = lerp(BH, H, bandGrow);
      g.clearRect(0, 0, W, H);
      // tape
      const intro = E.outExpo(prog(t, 0.0, 0.5));
      for (const r of RALLIES) {
        const a = X(tx(r[0])), b = X(tx(r[0] + r[1]));
        if (b < 0 || a > W) continue;
        const isT = r === TARGET;
        const lit = isT && t >= LOCK;
        const ry = lerp(by + bh / 2, by, intro), rh = bh * intro;
        g.fillStyle = lit ? C.tomato : C.ink;
        g.fillRect(a, ry, Math.max(1.5, b - a), rh);
      }
      // ruler
      if (zoom < 1.5 && t < ZOOM0) {
        g.globalAlpha = intro;
        g.strokeStyle = C.ink; g.lineWidth = 2;
        g.beginPath(); g.moveTo(X0, BY + BH + 22); g.lineTo(X1, BY + BH + 22); g.stroke();
        for (let s = 0; s <= MATCH; s += 60) {
          const x = tx(s), L = s % 600 === 0 ? 18 : 8;
          g.beginPath(); g.moveTo(x, BY + BH + 22); g.lineTo(x, BY + BH + 22 + L); g.stroke();
        }
        g.globalAlpha = 1;
      }
      // playhead
      const px = X(tx(hz));
      if (t > 0.15 && zoom < 30) {
        g.fillStyle = C.tomato;
        g.fillRect(px - 4, BY - 46, 8, BH + 92);
        g.beginPath(); g.moveTo(px - 18, BY - 64); g.lineTo(px + 18, BY - 64); g.lineTo(px, BY - 40); g.closePath(); g.fill();
        if (t >= LOCK && t < LOCK + 0.25) {   // lock brackets
          const k = E.outExpo(prog(t, LOCK, LOCK + 0.2)), w = lerp(80, 30, k);
          g.strokeStyle = C.ink; g.lineWidth = 5;
          g.strokeRect(px - w, BY - 20, w * 2, BH + 40);
        }
      }
      c.ticks.forEach((e, i) => putTL(e, tx(i * 600) - 26, BY + BH + 52, 1, 0, intro * (zoom < 1.2 ? 1 : 0)));
      putTL(c.tag, X0, BY - 64, 1, 0, intro * (t < ZOOM0 ? 1 : 0));
      // giant tape timecode, cropped by the bottom edge
      c.big.textContent = tcode(hz);
      putTL(c.big, 104, 760, 1, 0, t > 0.15 && t < ZOOM0 + 0.1 ? 1 : 0);
      // type
      const out = t >= ZOOM0 + 0.15;
      putTL(c.h1.el, 110, 92, 1, 0, out ? 0 : 1);
      typeIn(c.h1, t, 0.9, 0.1, "cut");
      const s2 = E.outExpo(prog(t, 2.95, 3.6));
      const base = 116, y2 = 300, cw = FS2 * 0.955;
      c.l2.forEach((e, i) => {
        let x = base + i * cw;
        if (i >= 2 && i <= 5) x = lerp(x, lerp(560, 1520, (i - 2) / 3), s2);
        if (i >= 6) x = lerp(x, 1520 + (i - 5) * cw, s2);
        const on = t >= 2.4 + i * 0.1 && !out;
        putTL(e, x, y2, 1, 0, on ? 1 : 0);
        e.style.color = (i >= 2 && i <= 5 && s2 > 0.02) ? C.tomatoText : C.ink;
      });
    },
  });
})();
