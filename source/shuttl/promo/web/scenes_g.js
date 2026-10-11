// ── S5 · Speed (37.0 – 42.35 s): odometer rolls to 330. "吹牛，从此有据可查。"
const S5M = { x: 250, y: 1650 }, S6M = { x: 880, y: 1680 };
const G6 = ["smash", "kill", "clear", "lift", "drop", "net", "block", "drive", "push", "serve"];
const G6X = i => 85 + (i % 5) * 190 + 75, G6Y = i => 520 + Math.floor(i / 5) * 300 + 75;
const LOCK5 = [37.55, 37.8, 38.02];
S({
  t0: 37.0, t1: 42.35, z: 30,
  build(root) {
    const c = this;
    root.style.background = "var(--tomato)";
    root.innerHTML = `<svg class="abs" width="1080" height="1920" style="opacity:.17"><g stroke="#221B2E" stroke-width="3" fill="none"><path d="M-100 1560 L1300 760"/><path d="M-100 1760 L1300 960"/><path d="M330 -100 L1130 2100"/><path d="M-100 380 L1300 -320"/></g></svg>`;
    css(el("div", "abs", root), { width: W + "px", height: H + "px", backgroundImage: "radial-gradient(rgba(34,27,46,.22) 2.6px, transparent 3.2px)", backgroundSize: "22px 22px", webkitMaskImage: "linear-gradient(160deg, transparent 35%, #000 92%)" });
    c.lab = css(el("div", "abs body", root, "本场最快扣杀"), { fontSize: "54px", fontWeight: 600, whiteSpace: "nowrap", webkitTextStroke: "1px var(--ink)" });
    c.odo = css(el("div", "abs", root), { display: "flex" });
    c.cols = [3, 3, 0].map(d => {
      const w = css(el("div", "", c.odo), { height: "460px", overflow: "hidden" });
      const s = css(el("div", "num", w), { fontSize: "460px", lineHeight: "460px", letterSpacing: "0" });
      s.innerHTML = Array.from({ length: 30 }, (_, i) => `<div>${i % 10}</div>`).join("");
      return { s, d };
    });
    c.unit = css(el("div", "unit abs", root, "km/h"), { fontSize: "128px", whiteSpace: "nowrap" });
    c.seal = el("div", "abs", root, `<svg width="210" height="210" viewBox="0 0 100 100"><path d="${scallop(50, 50, 47, 42, 16)}" fill="#F7D95C" stroke="#221B2E" stroke-width="3"/><circle cx="50" cy="50" r="33" fill="none" stroke="#221B2E" stroke-opacity=".35" stroke-dasharray="2 2.5"/><text x="50" y="60" text-anchor="middle" font-family="PingFang SC" font-weight="600" font-size="26" fill="#221B2E">扣杀</text></svg>`);
    c.h = headline(root, "吹牛，\n从此有据可查。");
    cue(37.0, "hit", { gain: 1 }); cue(37.05, "ratchet", { dur: 0.97, gain: .8 });
    LOCK5.forEach((x, i) => cue(x, "lock", { pitch: i * .3, gain: .9 }));
    cue(38.02, "slam", { gain: 1.1 }); cue(38.12, "pop", { pitch: .7 }); cue(38.35, "stamp", { gain: .9 });
    cue(37.9, "whoosh", { gain: .6, dur: .45 }); cue(38.45, "bump", { gain: .6 }); cue(41.95, "iris", { gain: .6, rev: 1 });
    BUBBLES.add(38.65, 39.95, "刚才那个……是我？", "r");
  },
  update(lt, t) {
    const c = this;
    const r = lerp(1500, 72, E.ioQuint(prog(t, 41.95, 42.32)));
    this.root.style.clipPath = t > 41.95 ? `circle(${r}px at ${G6X(0)}px ${G6Y(0)}px)` : "";
    shake(t, 38.02, 30, 0.5);
    put(c.lab, 540, 380, 1, 0, clamp((t - 37.05) * 6));
    put(c.odo, 540, 730, 1 + wob(t - 38.02, 2.5, 5) * 0.04, 0, 1);
    c.cols.forEach(({ s, d }, i) => {
      const L = LOCK5[i], v = (20 + d) * E.outCubic(prog(t, 37.05, L)) + (t > L ? wob(t - L, 3, 7) * 0.12 : 0);
      s.style.transform = `translateY(${-v * 460}px)`;
    });
    const us = spring(t - 38.12, 2.8, 0.38);
    put(c.unit, 810, 1020, us, -5, clamp(us * 4));
    const ss = spring(t - 38.35, 3, 0.35);
    put(c.seal, 900, 360, lerp(1.9, 1, ss), 12, clamp(ss * 4));
    putTL(c.h.el, 80, 1120); popChars(c.h, t, 40.0, 0.05);
  },
  pose(lt, t) {
    if (t < 37.9) return { hidden: true };
    const I = idle(t, 5.1);
    if (t < 38.45) { const u = prog(t, 37.9, 38.45); return { x: lerp(-200, S5M.x, E.outCubic(u)), y: lerp(1250, S5M.y, E.inSine(u)), r: lerp(-540, 0, E.outCubic(u)), s: 1, mood: "dizzy", sq: -0.2 }; }
    if (t < 41.6) return Object.assign(I, { x: S5M.x, y: S5M.y, sq: I.sq + wob(t - 38.45, 3.4, 6) * 0.25, s: 1, mood: t < 38.65 ? "dizzy" : t < 40 ? "wow" : "smug", lx: 0.7, ly: -1 });
    return Object.assign(hop(t, 41.6, 41.95, S5M, { x: 180, y: 2250 }, 120), { s: 1, mood: "happy" });
  },
});

// ── S6 · 04 击球 (41.9 – 48.0 s): ten shot pictograms, then one rally's hit timeline.
S({
  t0: 41.9, t1: 48.0, z: 29,
  build(root) {
    const c = this;
    c.chap = el("div", "chap abs", root, "<b>04</b>击球");
    c.h = headline(root, "十种击球，\n一眼认出。");
    c.chips = G6.map((k, i) => ({ ch: chip(root, k, 150), lb: css(el("div", "abs", root, SHOT[k][0]), { font: "600 44px 'PingFang SC'", whiteSpace: "nowrap" }) }));
    c.card = css(el("div", "card abs", root), { width: "920px", padding: "40px 48px 24px", boxSizing: "border-box" });
    el("div", "chap", c.card, "回合 02 · 近端发球").style.fontSize = "28px";
    const hd = el("div", "", c.card); hd.style.cssText = "display:flex;align-items:center;gap:28px;margin:6px 0 10px";
    el("div", "", hd, "8 拍").style.cssText = "font:900 120px NY;letter-spacing:-3px";
    css(el("div", "pill", hd, "界内 · 远端得分"), { background: "var(--flamingo)", transform: "rotate(-4deg)", fontSize: "38px" });
    c.rows = [["serve", 48, "1.0", "第 1 拍 · 近端"], ["net", 44, "0.8", "第 2 拍 · 远端"], ["lift", 139, "0.7", "第 3 拍 · 近端"], ["smash", 241, "2.7", "第 4 拍 · 远端"]].map(([k, v, hgt, sub]) => {
      const r = el("div", "", c.card); r.style.cssText = "display:flex;align-items:center;gap:30px;height:140px";
      const ch = chip(r, k, 96); ch.el.style.position = "static";
      const mid = el("div", "", r); mid.style.cssText = "flex:1";
      el("div", "", mid, SHOT[k][0]).style.cssText = "font:600 52px 'PingFang SC';-webkit-text-stroke:1.2px var(--ink)";
      el("div", "chap", mid, sub).style.cssText = "font:700 26px SFMono;letter-spacing:3px;color:var(--inkSoft)";
      el("div", "", r, `<b style="font:900 64px NY">${v}</b><i style="font:italic 900 30px NY"> km/h</i><div class="chap" style="font-size:24px;letter-spacing:2px;text-align:right">击球高度 ${hgt} m</div>`).style.textAlign = "right";
      return { r, ch };
    });
    G6.forEach((k, i) => cue(42.25 + i * 0.12, "pop", { pitch: i / 9, gain: .55 }));
    cue(44.9, "swish", { gain: .5 }); cue(45.1, "rise", { gain: .4, dur: .4 });
    [45.3, 45.48, 45.66, 45.84].forEach((x, i) => cue(x, "tick", { pitch: .4 + i * .15 }));
    cue(45.65, "boing", { gain: .45 }); cue(47.6, "whoosh", { gain: .6, dur: .45 });
    BUBBLES.add(46.25, 47.6, "打了几拍？它比你记得清楚。", "l");
  },
  update(lt, t) {
    const c = this, ox = -W * E.ioCubic(prog(t, 47.6, 48.0));
    this.root.style.transform = ox ? `translateX(${ox}px)` : "";
    putTL(c.chap, 80, 150, 1, 0, clamp((t - 42.2) * 5));
    putTL(c.h.el, 80, 200); popChars(c.h, t, 42.4, 0.045);
    c.chips.forEach(({ ch, lb }, i) => {
      const p = 42.25 + i * 0.12, s = spring(t - p, 2.8, 0.38), q = E.inCubic(prog(t, 44.9 + i * 0.025, 45.2 + i * 0.025));
      put(ch.el, G6X(i), G6Y(i) - q * 160, s, (1 - s) * -20, clamp(s * 4) * (1 - q));
      put(lb, G6X(i), G6Y(i) + 128 - q * 160, 1, 0, clamp((t - p - 0.12) * 5) * (1 - q));
      drawChip(ch, E.outCubic(prog(t, p + 0.1, p + 0.45)));
    });
    const cs = E.outCubic(prog(t, 45.0, 45.4));
    putTL(c.card, 80, lerp(1950, 560, cs), 1, 0, cs > 0 ? 1 : 0);
    c.rows.forEach(({ r, ch }, i) => { const p = 45.3 + i * 0.18, s = spring(t - p, 2.6, 0.45); r.style.opacity = clamp(s * 3); r.style.transform = `translateX(${(1 - s) * 60}px)`; drawChip(ch, E.outCubic(prog(t, p, p + 0.35))); });
  },
  pose(lt, t) {
    if (t < 45.6) return { hidden: true };
    const I = idle(t, 6.2), h = hop(t, 45.62, 46.05, { x: 1250, y: 1450 }, S6M, 200);
    if (t < 46.05) return Object.assign(h, { s: 0.95, mood: "happy" });
    return Object.assign(I, { x: S6M.x, y: S6M.y, s: 0.95, sq: I.sq + h.sq, mood: t > 46.2 ? "smug" : "normal", lx: -0.8, ly: -0.8 });
  },
});
