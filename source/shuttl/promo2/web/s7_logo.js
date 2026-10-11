// ── S7 · 56–60 s · Shuttl. / 看清，每一拍。
// One last flight across the page; the shuttle lands as the mark and the wordmark prints beside it.
(() => {
  const F0 = 56.0, LAND = 56.5;
  const MARK = 210;
  S({
    t0: 56.0, t1: 60.01,
    build(root) {
      const c = this;
      css(root, { background: C.paper });
      c.cv = canvas(root); c.g = c.cv.getContext("2d");
      c.word = el("div", "abs nyi", root);
      css(c.word, { fontSize: "250px", color: C.ink, lineHeight: "1", letterSpacing: "-0.02em" });
      c.letters = [..."Shuttl."].map((ch, i) => { const s = el("span", "", c.word, ch); s.style.display = "inline-block"; if (ch === ".") s.style.color = C.tomato; return s; });
      c.tag = headline(root, "看清，每一拍。", "zh", { fontSize: "66px", color: C.ink, letterSpacing: "0.02em" });
      c.mark = el("div", "abs", root, shuttleSVG(MARK, C.card, C.tomato, C.ink));
      cue(F0 - 0.08, "whoosh", { dur: 0.55 });
      cue(LAND, "thwack", { pitch: 1.4, gain: 1.1 }); cue(LAND, "boom", { gain: 1 });
      "Shuttl.".split("").forEach((_, i) => cue(LAND + 0.06 + i * 0.0625, "key", { pitch: 2 + i * .25, gain: .7 }));
      cue(57.25, "chime", { pitch: .5 });
    },
    update(lt, t) {
      const c = this, g = c.g;
      // lockup geometry (measured once fonts are in)
      if (!c._w) c._w = c.word.offsetWidth || 820;
      const gap = 70, total = MARK * 0.8 + gap + c._w;
      const x0 = W / 2 - total / 2, wy = 330;
      const end = [x0 + MARK * 0.4, wy + 130];
      const A = [-260, 900], Cc = [480, -320];
      const bez = u => [(1 - u) ** 2 * A[0] + 2 * u * (1 - u) * Cc[0] + u * u * end[0], (1 - u) ** 2 * A[1] + 2 * u * (1 - u) * Cc[1] + u * u * end[1]];
      const uh = E.outSine(prog(t, F0, LAND)), ut = t < LAND ? Math.max(0, uh - 0.6) : lerp(0.4, 1, E.ioCubic(prog(t, LAND, LAND + 0.5)));
      g.clearRect(0, 0, W, H);
      if (ut < uh - 0.003) {
        const n = 48; g.lineCap = "round";
        for (let i = 0; i < n; i++) {
          const k0 = i / n, k1 = (i + 1) / n, a = bez(lerp(ut, uh, k0)), b = bez(lerp(ut, uh, k1));
          g.strokeStyle = k1 < .4 ? C.lilac : k1 < .85 ? C.tomato : C.butter;
          g.lineWidth = 4 + 30 * k1; g.beginPath(); g.moveTo(...a); g.lineTo(...b); g.stroke();
        }
      }
      const hp = bez(uh), dt = t - LAND;
      const ang = t < LAND ? -60 + 40 * uh : -20 + wob(dt, 2.4, 5) * 14;
      const sq = dt > 0 ? 1 - 0.14 * Math.exp(-dt * 12) : 1;
      put(c.mark, hp[0], hp[1], 1.05, ang, t >= F0 ? 1 : 0, 1 / sq, sq);
      putTL(c.word, x0 + MARK * 0.8 + gap, wy, 1, 0, 1);
      c.letters.forEach((s, i) => { const d = t - LAND - 0.06 - i * 0.0625; s.style.opacity = d >= 0 ? 1 : 0; s.style.transform = d >= 0 && d < 0.05 ? "translateY(-6%)" : ""; });
      shake(t, LAND, 14, 0.3);
      const tw = c.tag.el.offsetWidth || 500;
      putTL(c.tag.el, W / 2 - tw / 2, 640, 1, 0, 1);
      typeIn(c.tag, t, 57.25, 0.06, "rise");
    },
  });
})();
