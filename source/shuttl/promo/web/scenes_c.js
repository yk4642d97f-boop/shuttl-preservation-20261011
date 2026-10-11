// ── S2 · 01 录制 (11.95 – 20.45 s): tripod diagram → phone turns sideways → court lock → record.
const TRI = -11.7, S2A = { x: 885, y: 1256 }, S2B = { x: 880, y: 1640 };
const LOCK_SVG = `<svg width="30" height="36" viewBox="0 0 30 36"><path d="M8 16V11a7 7 0 0 1 14 0v5" fill="none" stroke="#221B2E" stroke-width="4.5"/><rect x="3" y="15" width="24" height="19" rx="5" fill="#221B2E"/></svg>`;
S({
  t0: 11.95, t1: 20.45, z: 24,
  build(root) {
    const c = this;
    c.chap = el("div", "chap abs", root, "<b>01</b>录制");
    c.h = headline(root, "架好，就开拍。");
    c.dia = css(el("div", "abs", root), { width: W + "px", height: H + "px" });
    c.cv = canvas(c.dia); c.g = c.cv.getContext("2d");
    c.labs = ["1.6 米", "5 米", "正中间"].map((s, i) => css(el("div", "pill abs", c.dia, s), { background: i === 2 ? "var(--butter)" : "var(--card)", fontSize: "38px" }));
    c.card = css(el("div", "card abs", root), { width: "920px", padding: "36px 44px 32px", boxSizing: "border-box" });
    el("div", "body", c.card, "横着拍，才装得下整片球场").style.cssText = "font-size:40px;font-weight:600;color:var(--inkSoft);margin-bottom:16px";
    c.rows = ["三脚架约 1.6 米高", "底线后约 5 米", "正中间，对准中线"].map((s, i) => {
      const r = el("div", "", c.card); r.style.cssText = "display:flex;align-items:center;gap:24px;margin:16px 0";
      el("div", "", r, String(i + 1)).style.cssText = "width:60px;height:60px;border-radius:50%;background:var(--ink);color:var(--paper);display:flex;align-items:center;justify-content:center;font:900 36px NY";
      el("div", "", r, s).style.cssText = "font:600 52px 'PingFang SC';-webkit-text-stroke:1.2px var(--ink)";
      return r;
    });
    el("div", "body", c.card, "没那么远？架到 2.5 米高、退 4.5 米也行。").style.cssText = "font-size:32px;color:var(--inkSoft);margin-top:14px";
    c.ph = phone(root, ["rec_upright", "rec_search", "rec_candidate", "rec_locked", "rec_recording"], 440);
    c.lock = css(el("div", "sticker abs", root, `${LOCK_SVG}球场锁定`), { background: "var(--pistachio)", fontSize: "44px" });
    c.chips = css(el("div", "abs", root), { display: "flex", gap: "22px", width: W + "px", justifyContent: "center" });
    c.chipEls = [["单打 · 双打", "var(--lilac)"], ["1080p · 60fps", "var(--butter)"], ["前后摄都能用", "var(--flamingo)"]]
      .map(([s, b]) => css(el("div", "sticker", c.chips, s), { background: b, fontSize: "36px" }));
    cue(12.5, "pop", { pitch: .3 }); cue(12.6, "swish", { gain: .4 }); cue(13.05, "rise", { gain: .35, dur: .4 });
    cue(13.35, "pop", { pitch: .6 }); [13.6, 13.8, 14.0].forEach((x, i) => cue(x, "tick", { pitch: .3 + i * .25 }));
    cue(14.9, "swish", { gain: .5 }); cue(15.0, "pop", { pitch: .4 }); cue(15.55, "whoosh", { gain: .55, dur: .45 });
    cue(16.5, "tick", { pitch: .5 }); cue(17.0, "stamp", { gain: .9 }); cue(17.05, "chime", { gain: .5 });
    [17.5, 17.65, 17.8].forEach((x, i) => cue(x, "pop", { pitch: .5 + i * .2 })); cue(18.75, "shutter", { gain: 1 });
    cue(19.95, "whoosh", { gain: .6, dur: .5 });
    BUBBLES.add(17.25, 18.45, "球场，它自己会找。", "l");
    BUBBLES.add(18.95, 20.0, "开拍！这回别再判我出界。", "l");
  },
  update(lt, t) {
    const c = this, g = c.g;
    const ox = W * (1 - E.ioCubic(prog(t, 11.95, 12.5))), oy = -H * E.ioCubic(prog(t, 19.95, 20.45));
    this.root.style.transform = `translate(${ox}px,${oy}px)`;
    putTL(c.chap, 80, 150, 1, 0, clamp((t - 12.45) * 5));
    putTL(c.h.el, 80, 200); popChars(c.h, t, 12.55, 0.05);
    // diagram (until ~15.2)
    const dx = E.inCubic(prog(t, 14.9, 15.25));
    c.dia.style.opacity = 1 - dx; c.dia.style.transform = `translateY(${-dx * 80}px) scale(${1 - dx * 0.08})`;
    c.dia.style.visibility = dx >= 1 ? "hidden" : "visible";
    if (dx < 1) drawDiagram(c, g, t);
    const cx = E.inCubic(prog(t, 14.85, 15.2));
    putTL(c.card, 80, 1320 + cx * 700, 1, 0, 1 - cx);
    c.rows.forEach((r, i) => { const d = t - 13.6 - i * 0.2, s = spring(d, 2.6, 0.45); r.style.opacity = 0.22 + 0.78 * clamp(d * 6); r.style.transform = `translateX(${d > 0 ? wob(d, 3, 6) * 14 : 0}px) scale(${1 + (d > 0 ? wob(d, 2.5, 5) * 0.05 : 0)})`; r.style.transformOrigin = '0 50%'; });
    // phone phase
    const ps = spring(t - 14.95, 2.1, 0.45), rot = -87 * spring(t - 15.55, 1.7, 0.45);
    c.ph.el.style.transform = `translate(${540 - c.ph.w / 2}px,${900 - c.ph.h / 2}px) rotate(${rot}deg) scale(${ps})`;
    c.ph.el.style.visibility = t < 14.95 ? "hidden" : "visible";
    const f = (a) => prog(t, a, a + 0.18);
    c.ph.show({ rec_upright: 1 - f(15.9), rec_search: f(15.9) * (1 - f(16.45)), rec_candidate: f(16.45) * (1 - f(16.95)), rec_locked: f(16.95) * (1 - f(18.72)), rec_recording: f(18.72) });
    const ls = spring(t - 17.0, 3, 0.35);
    put(c.lock, 790, 650, lerp(1.8, 1, ls), -6, clamp(ls * 4));
    putTL(c.chips, 0, 1250, 1, 0, 1);
    c.chipEls.forEach((e, i) => { const s = spring(t - 17.5 - i * 0.15, 2.8, 0.4); e.style.transform = `scale(${s}) rotate(${[-3, 2, -2][i]}deg)`; e.style.opacity = clamp(s * 3); });
  },
  pose(lt, t) {
    const I = idle(t, 2.1);
    if (t < 14.9) {
      const h = hop(t, 11.97, 12.47, S1M, S2A, 260);
      if (t < 12.47) return Object.assign(h, { mood: "happy", s: 0.95 });
      return Object.assign(I, { x: S2A.x, y: S2A.y, sq: I.sq + h.sq, s: 0.95, lx: -0.7, ly: -0.6 });
    }
    const h = hop(t, 14.9, 15.35, S2A, S2B, 160);
    if (t < 15.35) return Object.assign(h, { s: 0.95, mood: "happy" });
    return Object.assign(I, { x: S2B.x, y: S2B.y, sq: I.sq + h.sq, s: 0.95, lx: -0.8, ly: -0.8, mood: t > 18.9 ? "happy" : "normal" });
  },
});
function drawDiagram(c, g, t) {
  const cam = camera([lerp(9.6, 6.6, ease(t, 12.3, 15, E.ioSine)), -19.5, 8.2], [0, -3.8, 0.4], 1250, 610, 660);
  g.clearRect(0, 0, W, H);
  g.globalAlpha = ease(t, 12.45, 12.8);
  drawCourt(g, cam, { felt: "#B9D66A", line: "rgba(255,251,244,.96)", edge: "#221B2E", edgeW: 4, lw: 0.07, reveal: E.ioSine(prog(t, 12.5, 13.3)) });
  drawNet(g, cam, { mesh: "rgba(34,27,46,.14)", tape: "#221B2E", post: "#221B2E", tapeW: 4, postW: 5 });
  g.globalAlpha = 1;
  const seg = (a, b, col, w, dash) => { const p = cam.p(...a), q = cam.p(...b); g.strokeStyle = col; g.lineWidth = w; g.setLineDash(dash || []); g.beginPath(); g.moveTo(p[0], p[1]); g.lineTo(q[0], q[1]); g.stroke(); g.setLineDash([]); };
  g.lineCap = "round";
  const cu = E.outCubic(prog(t, 13.95, 14.4));
  if (cu > 0) seg([0, -6.7, 0], [0, lerp(-6.7, 6.7, cu), 0], "#F2542D", 6, [18, 14]);
  const fu = ease(t, 13.45, 13.85), P = [0, TRI, 1.6], K = [[-3.05, -6.7], [3.05, -6.7], [3.05, 6.7], [-3.05, 6.7]];
  if (fu > 0) {
    for (const [a, b] of [[0, 1], [2, 3], [1, 2], [3, 0]]) poly(g, cam, [P, [...K[a], 0], [...K[b], 0]], `rgba(47,75,222,${0.07 * fu})`);
    for (const k of K) seg(P, [...k, 0], `rgba(47,75,222,${0.6 * fu})`, 2.5);
  }
  const tu = clamp(E.outBack(prog(t, 13.05, 13.4)), 0, 1.1);
  if (tu > 0) {
    for (const f of [[-0.5, TRI - 0.3], [0.5, TRI - 0.3], [0, TRI + 0.45]]) seg([0, TRI, 1.45 * tu], [...f, 0], "#221B2E", 7);
    seg([0, TRI, 1.45 * tu], [0, TRI, 1.6 * tu], "#221B2E", 9);
  }
  const pu = spring(t - 13.35, 2.6, 0.4);
  if (pu > 0.01) {
    const w = 0.34 * pu, h = 0.19 * pu;
    poly(g, cam, [[-w, TRI, 1.6 - h], [w, TRI, 1.6 - h], [w, TRI, 1.6 + h], [-w, TRI, 1.6 + h]], "#221B2E", "#221B2E", 4);
    const l = cam.p(-w * 0.62, TRI - 0.01, 1.6 + h * 0.5); g.fillStyle = "#F2542D"; g.beginPath(); g.arc(l[0], l[1], 7 * pu, 0, 7); g.fill();
  }
  const hu = E.outCubic(prog(t, 13.6, 13.95)), du = E.outCubic(prog(t, 13.8, 14.15));
  if (hu > 0) { seg([-0.95, TRI, 0], [-0.95, TRI, 1.6 * hu], "#221B2E", 4); seg([-1.15, TRI, 1.6 * hu], [-0.75, TRI, 1.6 * hu], "#221B2E", 4); seg([-1.15, TRI, 0], [-0.75, TRI, 0], "#221B2E", 4); }
  if (du > 0) { const X = 1.5; seg([X, TRI, 0], [X, lerp(TRI, -6.7, du), 0], "#221B2E", 4); seg([X - 0.3, TRI, 0], [X + 0.3, TRI, 0], "#221B2E", 4); if (du > 0.98) seg([X - 0.3, -6.7, 0], [X + 0.3, -6.7, 0], "#221B2E", 4); }
  const L = [[cam.p(-0.95, TRI, 0.8), 13.6, -90, 0], [cam.p(1.5, (TRI - 6.7) / 2, 0), 13.8, 30, 46], [cam.p(0, -1.2, 0), 14.0, 0, -10]];
  L.forEach(([p, t0, ox, oy], i) => { const s = spring(t - t0, 2.8, 0.4); put(c.labs[i], p[0] + ox, p[1] + oy, s, [-4, 3, -3][i], clamp(s * 3)); });
}
