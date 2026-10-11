// ── S4 · 03 回放 (26.0 – 37.0 s): the rally drawn as it happens, then 0.25× on the winning smash.
const HAND = [0.35, -2.2, 1.1];
const PILL_X = [0, 150, 300, 450], PILL_CH = [[0, 2], [TSM - 0.3, 0], [34.0, 2]];
const pillIdx = t => { let v = 2, from = 2, t0 = -9; for (const [tt, i] of PILL_CH) if (t >= tt) { from = v; v = i; t0 = tt; } return [from, v, t0]; };
function ms(cam, p, t) {
  const slow = ease(t, TSM, TSM + 0.35) * (1 - ease(t, TLAND + 0.1, TLAND + 0.6));
  return clamp(cam.p(...p)[2] / 121 * 0.36, 0.18, 0.5) * lerp(1, 2.7, slow);
}
S({
  t0: 26.0, t1: 37.0, z: 28,
  build(root) {
    const c = this;
    root.style.background = "var(--night)";
    c.cv = canvas(root); c.g = c.cv.getContext("2d"); c.cam = CAM4();
    c.chap = el("div", "chap abs", root, "<b>03</b>回放"); c.chap.style.color = "var(--paperDeep)";
    c.h = headline(root, "每一拍，\n都画出来。", "hl paper"); c.h.el.style.fontSize = "104px";
    c.pops = R4.shots.map((s, i) => {
      const e = css(el("div", "sticker abs", root), { background: "var(--card)", fontSize: s.win ? "46px" : "36px", padding: "10px 24px 10px 12px" });
      const ch = chip(e, s.kind, s.win ? 76 : 60); ch.el.style.position = "static"; drawChip(ch, 1);
      el("span", "", e, `${SHOT[s.kind][0]} <b style="font:900 1.15em NY">${s.kmh}</b> <i style="font:italic 900 .8em NY">km/h</i>`);
      const tc = toT(s.t0);
      cue(tc, i === 0 ? "tock" : "thwack", { gain: 0.35 + 0.65 * s.kmh / 330, pitch: s.kmh / 330 });
      cue(tc + 0.05, "pop", { pitch: 0.3 + i * 0.08, gain: .5 });
      return { e, tc, s, p: c.cam.p(...s.from) };
    });
    c.pill = css(el("div", "abs", root), { width: "612px", height: "92px", borderRadius: "46px", background: "var(--card)", border: "4px solid var(--ink)", boxSizing: "border-box" });
    c.blob = css(el("div", "abs", c.pill), { width: "150px", height: "76px", borderRadius: "38px", background: "var(--ink)", top: "4px", left: "4px" });
    c.opts = ["0.25×", "0.5×", "1×", "2×"].map((s, i) => css(el("div", "abs mono", c.pill, s), { width: "150px", left: 4 + PILL_X[i] + "px", top: "0", lineHeight: "84px", textAlign: "center", fontSize: "32px", letterSpacing: "1px" }));
    c.land = css(el("div", "sticker abs", root, "界内 · 远端得分"), { background: "var(--flamingo)", fontSize: "44px" });
    c.scr = css(el("div", "abs", root), { width: W + "px" });
    c.tog = css(el("div", "sticker", c.scr, `<svg width="40" height="34" viewBox="0 0 40 34"><rect x="3" y="3" width="34" height="28" rx="5" fill="none" stroke="#221B2E" stroke-width="4"/><path d="M11 3v28M29 3v28M3 12h8M3 22h8M29 12h8M29 22h8" stroke="#221B2E" stroke-width="3.5"/></svg>只看回合`), { background: "var(--card)", fontSize: "42px", position: "absolute", left: "80px", top: "0" });
    c.cap = css(el("div", "abs body", c.scr, "捡球的时间，自动跳过。"), { color: "var(--paper)", fontSize: "44px", left: "80px", top: "108px", fontWeight: 600 });
    c.track = css(el("div", "abs", c.scr), { left: "80px", top: "196px", height: "60px", display: "flex", alignItems: "stretch" });
    c.segs = [130, 80, 170, 100, 150].map((w, i) => css(el("div", "", c.track), { width: w + "px", borderRadius: "14px", border: "4px solid var(--ink)", background: i === 3 ? "var(--tomato)" : "var(--paper)", boxSizing: "border-box" }));
    c.gaps = [60, 70, 50, 60].map((w, i) => { const gp = css(el("div", "", c.track), { width: w + "px", background: "repeating-linear-gradient(135deg, rgba(244,238,227,.28) 0 6px, transparent 6px 14px)", margin: "10px 0", borderRadius: "6px" }); c.track.insertBefore(gp, c.segs[i + 1]); return { gp, w }; });
    cue(TSM - 0.3, "click", { gain: .6 }); cue(TSM, "slowdown", { gain: .9 }); cue(34.0, "click", { gain: .5 }); cue(34.0, "speedup", { gain: .6 });
    cue(TLAND, "thud", { gain: 1 }); cue(TLAND + 0.28, "stamp", { gain: .8 }); cue(34.8, "click", { gain: .7 }); cue(34.88, "zip", { gain: .7 });
    cue(35.7, "boing", { gain: .5 }); cue(36.45, "whoosh", { gain: .5, dur: .4 });
    BUBBLES.add(TSM + 0.3, TLAND - 0.1, "慢放 0.25×，\n这张脸拍清了吧。", "r", { at: { x: 130, y: 850 } });
  },
  update(lt, t) {
    const c = this, g = c.g, cam = c.cam, rt = toRT(t);
    const iris = E.outCubic(prog(t, 26.0, 26.45)) * 2300;
    this.root.style.clipPath = iris < 2299 ? `circle(${iris}px at ${S3M.x}px ${S3M.y - 60}px)` : "";
    shake(t, TLAND, 16, 0.4);
    g.fillStyle = "#15121C"; g.fillRect(0, 0, W, H);
    const sp = g.createRadialGradient(540, 1000, 80, 540, 1000, 900); sp.addColorStop(0, "rgba(199,182,242,.16)"); sp.addColorStop(1, "rgba(199,182,242,0)");
    g.fillStyle = sp; g.fillRect(0, 0, W, H);
    drawCourt(g, cam, { felt: "#1F4A3A", line: "rgba(244,238,227,.78)", lw: 0.05, apron: "#1B1723" });
    if (rt >= 0 && rt <= R4.T) { const q = rallyAt(R4, rt).p, s = cam.p(q[0], q[1], 0); g.fillStyle = "rgba(0,0,0,.35)"; g.beginPath(); g.ellipse(s[0], s[1], 0.16 * s[2], 0.05 * s[2], 0, 0, 7); g.fill(); }
    drawPawn(g, cam, feet(FAR, rt), "#FF7AB6");
    drawNet(g, cam, { mesh: "rgba(244,238,227,.13)", tape: "#F4EEE3", tapeW: 5 });
    drawPawn(g, cam, feet(NEAR, rt), "#2F4BDE");
    if (t > TLAND) {
      const L = R4.shots[5].to, u = prog(t, TLAND, TLAND + 0.6);
      poly(g, cam, ring(L, 0.28 + 0.9 * E.outCubic(u)), null, `rgba(242,84,45,${1 - u})`, 6);
      poly(g, cam, ring(L, 0.24), "rgba(244,238,227,.9)", "#15121C", 4);
    }
    g.globalAlpha = 1 - prog(t, 35.4, 36.0); drawTrail(g, cam, R4, Math.min(rt, R4.T + 0.05), 1.15, { w: 0.075, min: 2.5, hot: 0.62 }); g.globalAlpha = 1;
    putTL(c.chap, 80, 150, 1, 0, clamp((t - 26.4) * 5) * (1 - prog(t, TSM - 0.2, TSM + 0.1)));
    putTL(c.h.el, 80, 200, 1, 0, 1 - prog(t, TSM - 0.2, TSM + 0.1)); popChars(c.h, t, 26.4, 0.045);
    c.pops.forEach(({ e, tc, s, p }) => {
      const life = s.win ? TLAND + 0.3 : tc + 1.0, k = spring(t - tc, 3, 0.4) * (1 - E.inCubic(prog(t, life, life + 0.2)));
      if (s.win) put(e, 720, 470, k, 4, clamp(k * 4)); else put(e, clamp(p[0], 250, 830), Math.max(540, p[1] - 150), k, -3, clamp(k * 4));
    });
    const [fi, ti, tp] = pillIdx(t), bx = lerp(PILL_X[fi], PILL_X[ti], spring(t - tp, 2.6, 0.45)), po = clamp((t - 27.3) * 4) * (1 - prog(t, 34.3, 34.5));
    put(c.pill, 540, 1790, 1, 0, po); c.blob.style.transform = `translateX(${bx}px)`;
    c.opts.forEach((o, i) => o.style.color = Math.abs(bx - PILL_X[i]) < 75 ? "var(--paper)" : "var(--inkSoft)");
    const lp = cam.p(...R4.shots[5].to), ls = spring(t - TLAND - 0.28, 3, 0.35);
    put(c.land, clamp(lp[0], 260, 820), lp[1] - 130, lerp(1.8, 1, ls), -5, clamp(ls * 4) * (1 - prog(t, 36.3, 36.6)));
    const so = clamp((t - 34.35) * 4), on = t >= 34.8;
    putTL(c.scr, 0, 1560 + (1 - E.outCubic(clamp((t - 34.35) * 3))) * 60, 1, 0, so);
    c.tog.style.background = on ? "var(--pistachio)" : "var(--card)";
    c.tog.style.transform = `scale(${1 + (on ? wob(t - 34.8, 3, 6) * 0.12 : 0)})`;
    const zu = E.ioCubic(prog(t, 34.88, 35.3));
    c.gaps.forEach(({ gp, w }) => gp.style.width = lerp(w, 8, zu) + "px");
    c.cap.style.opacity = clamp((t - 34.95) * 4);
  },
  pose(lt, t) {
    const cam = this.cam, rt = toRT(t), hp = cam.p(...HAND);
    if (t < 26.55) { const h = hop(t, 26.0, 26.55, { x: S3M.x, y: S3M.y }, { x: hp[0], y: hp[1] }, 260); return Object.assign(h, { s: lerp(0.95, ms(cam, HAND, t), E.ioSine(prog(t, 26.0, 26.55))), mood: "happy" }); }
    if (rt < 0) return Object.assign(idle(t, 1), { x: hp[0], y: hp[1] + 3 * Math.sin(t * 9), s: ms(cam, HAND, t), r: 0, mood: "normal", ly: -1 });
    if (rt < R4.T) {
      const { p, v } = rallyAt(R4, rt), a = cam.p(...p), b = cam.p(p[0] + v[0] * 0.01, p[1] + v[1] * 0.01, p[2] + v[2] * 0.01);
      let r = Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI - 90;
      if (rt < 0.08) r = lerp(0, r, rt / 0.08);
      const slow = t > TSM;
      return { x: a[0], y: a[1], s: ms(cam, p, t), r, sq: slow ? -0.12 : -0.2, mood: slow ? "wow" : "squint", wig: -5 };
    }
    const L = cam.p(...R4.shots[5].to), s = ms(cam, R4.shots[5].to, t), base = { x: L[0], y: L[1] - 45 * s };
    if (t < 35.6) { const h = hop(t, TLAND, TLAND + 0.4, base, { x: base.x + 40, y: base.y }, 80); return Object.assign(h, { s, r: lerp(-20, 95, E.outCubic(prog(t, TLAND, TLAND + 0.5))), mood: "dizzy" }); }
    const up = spring(t - 35.6, 2.2, 0.4), I = idle(t, 4);
    if (t < 36.4) return Object.assign(I, { x: base.x + 40, y: base.y - 50 * Math.sin(Math.PI * clamp((t - 35.6) / 0.3)), s, r: lerp(95, 0, up), mood: "happy" });
    return Object.assign(hop(t, 36.4, 36.95, { x: base.x + 40, y: base.y }, { x: 1300, y: base.y - 200 }, 300), { s, mood: "happy" });
  },
});
function ring(p, r) { const a = []; for (let i = 0; i < 28; i++) { const q = i / 28 * 2 * Math.PI; a.push([p[0] + Math.cos(q) * r, p[1] + Math.sin(q) * r, 0]); } return a; }
