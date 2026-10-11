// ── S11 · Finale (67.95 – 76.0 s): "该你上场了！" → racket → the shuttle becomes the app icon → Shuttl.
const S11M = { x: 540, y: 1150 }, TC = 70.5, ICO = { x: 540, y: 690, s: 440 };
const RACKET = `<svg width="420" height="1500" viewBox="0 0 420 1500" style="overflow:visible">
<path d="M210 630 L150 760 M210 630 L270 760" stroke="#221B2E" stroke-width="14" stroke-linecap="round"/>
<line x1="210" y1="630" x2="210" y2="1260" stroke="#221B2E" stroke-width="30" stroke-linecap="round"/>
<line x1="210" y1="630" x2="210" y2="1260" stroke="#C7B6F2" stroke-width="16" stroke-linecap="round"/>
<rect x="176" y="1240" width="68" height="260" rx="30" fill="#F2542D" stroke="#221B2E" stroke-width="8"/>
<path d="M180 1290 L240 1320 M180 1350 L240 1380 M180 1410 L240 1440" stroke="#221B2E" stroke-width="5"/>
<clipPath id="rh"><ellipse cx="210" cy="400" rx="168" ry="228"/></clipPath>
<g clip-path="url(#rh)" stroke="#221B2E" stroke-opacity=".55" stroke-width="4">${Array.from({ length: 13 }, (_, i) => `<line x1="${50 + i * 26}" y1="150" x2="${50 + i * 26}" y2="650"/>`).join("")}${Array.from({ length: 17 }, (_, i) => `<line x1="30" y1="${190 + i * 26}" x2="390" y2="${190 + i * 26}"/>`).join("")}</g>
<ellipse cx="210" cy="400" rx="175" ry="235" fill="none" stroke="#221B2E" stroke-width="30"/>
<ellipse cx="210" cy="400" rx="175" ry="235" fill="none" stroke="#2F4BDE" stroke-width="16"/></svg>`;
function racketAngle(t) {
  if (t < TC) return lerp(62, -35, Math.pow(prog(t, 70.1, TC), 2));
  return lerp(-35, -120, E.outCubic(prog(t, TC, TC + 0.3)));
}
S({
  t0: 67.95, t1: 76.01, z: 35, poseFrom: 68.0,
  build(root) {
    const c = this;
    c.cv = canvas(root); c.g = c.cv.getContext("2d");
    c.rk = [0.18, 0.35, 1].map(o => { const e = css(el("div", "abs", root, RACKET), { transformOrigin: "210px 1500px", opacity: o }); e.dataset.o = o; return e; });
    c.ico = css(el("div", "abs", root), { width: ICO.s + "px", height: ICO.s + "px" });
    c.dB = css(el("div", "abs", c.ico), { width: 0.74 * ICO.s + "px", height: 0.74 * ICO.s + "px", borderRadius: "50%", background: "#2F4BDE", mixBlendMode: "multiply" });
    c.dT = css(el("div", "abs", c.ico), { width: 0.66 * ICO.s + "px", height: 0.66 * ICO.s + "px", borderRadius: "50%", background: "#F2542D", mixBlendMode: "multiply" });
    c.img = css(el("div", "abs", c.ico, `<img src="../assets/icon.png" style="width:100%;height:100%;display:block">`), { width: "100%", height: "100%", borderRadius: "22.4%", overflow: "hidden", boxShadow: "0 36px 70px rgba(34,27,46,.28), 0 0 0 4px rgba(34,27,46,.9)" });
    c.wm = css(el("div", "abs", root), { font: "italic 900 230px NY", whiteSpace: "nowrap", letterSpacing: "-6px", lineHeight: 1 });
    c.letters = [..."Shuttl"].map(ch => css(el("span", "", c.wm, ch), { display: "inline-block" }));
    c.dot = css(el("span", "", c.wm, "."), { display: "inline-block", color: "var(--tomato)", transformOrigin: "50% 85%" });
    c.h = headline(root, "看清，每一拍。");
    c.sq = squiggle(c.h.el, 330, "#F2542D"); css(c.sq.svg, { left: "42%", top: "118px" });
    c.sub = css(el("div", "abs body", root, "iPhone 上的羽毛球比赛档案 · 全程在手机上分析"), { fontSize: "40px", color: "var(--inkSoft)", whiteSpace: "nowrap" });
    cue(68.0, "boing", { gain: .5 }); cue(70.1, "swing", { gain: 1 }); cue(TC, "thwack", { gain: 1.3 }); cue(TC, "boom", { gain: 1 });
    cue(70.75, "slide", { gain: .6 }); cue(70.85, "slide", { gain: .5 }); cue(71.3, "pop", { pitch: .5, gain: .9 }); cue(71.32, "chime", { gain: .6 });
    cue(71.5, "swish", { gain: .6 }); cue(72.0, "ding", { gain: 1 }); cue(72.3, "pop", { pitch: .6 }); cue(72.8, "scribble", { gain: .5 });
    cue(73.8, "boing", { gain: .35 });
    BUBBLES.add(68.55, 69.3, "好啦，别光看了——", "r");
    BUBBLES.add(69.45, 70.4, "该你上场了！", "r", { size: 64 });
  },
  update(lt, t) {
    const c = this, g = c.g;
    shake(t, TC, 34, 0.5);
    const th = racketAngle(t), P = { x: 540 + 1100 * Math.sin(35 * Math.PI / 180), y: 1150 + 1100 * Math.cos(35 * Math.PI / 180) };
    c.rk.forEach((e, i) => {
      const lag = (2 - i) * (t < TC ? -9 : 9), vis = t > 70.1 && t < TC + 0.45;
      e.style.transform = `translate(${P.x - 210}px,${P.y - 1500}px) rotate(${th + (i < 2 ? lag : 0)}deg)`;
      e.style.opacity = vis ? e.dataset.o * (1 - prog(t, TC + 0.25, TC + 0.45)) : 0;
      e.style.visibility = vis ? "visible" : "hidden";
    });
    g.clearRect(0, 0, W, H);
    const bu = prog(t, TC, TC + 0.5);
    if (bu > 0 && bu < 1) {
      const cols = ["#221B2E", "#F7D95C", "#2F4BDE", "#F2542D", "#FF7AB6", "#B9D66A"];
      for (let i = 0; i < 18; i++) {
        const a = i / 18 * 2 * Math.PI, r0 = 90 + 380 * E.outExpo(bu), len = 110 * (1 - bu) + 8;
        g.strokeStyle = cols[i % 6]; g.lineWidth = 18 * (1 - bu) + 2; g.lineCap = "round";
        g.beginPath(); g.moveTo(S11M.x + Math.cos(a) * r0, S11M.y + Math.sin(a) * r0); g.lineTo(S11M.x + Math.cos(a) * (r0 + len), S11M.y + Math.sin(a) * (r0 + len)); g.stroke();
      }
    }
    const B = ICO.s, bs = E.outQuint(prog(t, 70.75, 71.2)), ts = E.outQuint(prog(t, 70.85, 71.25));
    put(c.ico, ICO.x, ICO.y, 1, 0, t > 70.7 ? 1 : 0);
    putTL(c.dB, lerp(-900, 0.36 * B - 0.37 * B, bs), lerp(700, 0.66 * B - 0.37 * B, bs), 1, 0, 1 - prog(t, 71.3, 71.45));
    putTL(c.dT, lerp(1100, 0.65 * B - 0.33 * B, ts), lerp(-800, 0.35 * B - 0.33 * B, ts), 1, 0, 1 - prog(t, 71.3, 71.45));
    const io = prog(t, 71.28, 71.45); c.img.style.opacity = io; c.img.style.transform = `scale(${1 + wob(t - 71.3, 2.5, 6) * 0.05})`;
    put(c.wm, 540, 1100, 1, 0, t > 71.45 ? 1 : 0);
    c.letters.forEach((l, i) => { const s = spring(t - 71.5 - i * 0.05, 2.4, 0.45); l.style.transform = `translateY(${(1 - s) * 160}px) rotate(${(1 - s) * -10}deg)`; l.style.opacity = clamp(s * 3); });
    const dt = t - 72.0, dy = dt < 0 ? -1300 * (1 - clamp((t - 71.7) / 0.3)) ** 2 : -110 * Math.abs(Math.sin(dt * 7)) * Math.exp(-dt * 5.5);
    const dq = dt > 0 ? wob(dt, 3.5, 6) * 0.35 : -0.2;
    c.dot.style.transform = `translateY(${dy}px) scale(${1 + dq * 0.6},${1 - dq})`; c.dot.style.opacity = t > 71.7 ? 1 : 0;
    put(c.h.el, 540, 1350, 1, 0, 1); popChars(c.h, t, 72.3, 0.05);
    c.sq.set(E.outCubic(prog(t, 72.8, 73.2)));
    const su = E.outCubic(prog(t, 73.1, 73.5)); put(c.sub, 540, 1510 + (1 - su) * 24, 1, 0, su);
  },
  pose(lt, t) {
    const I = idle(t, 11.6);
    if (t < 68.45) return Object.assign(hop(t, 68.0, 68.45, S10M, S11M, 260), { s: lerp(0.9, 1.5, E.ioSine(prog(t, 68.0, 68.45))), mood: "happy" });
    if (t < TC) {
      const land = wob(t - 68.45, 3.4, 6) * 0.22, eek = t > 70.2;
      return Object.assign(I, { x: S11M.x, y: S11M.y, s: 1.5, sq: I.sq + land, mood: eek ? "wow" : t > 69.45 ? "happy" : "normal", lx: eek ? 1 : 0, ly: eek ? 0.3 : -0.3 });
    }
    if (t < 70.9) { const u = E.outCubic(prog(t, TC, 70.9)); return { x: lerp(S11M.x, 180, u), y: lerp(S11M.y, -300, u), s: lerp(1.5, 1, u), r: -900 * u, mood: "squint", sq: -0.25 }; }
    if (t < 70.95) return { hidden: true };
    if (t < 71.3) { const u = prog(t, 70.95, 71.3); return { x: lerp(780, 566, E.outSine(u)), y: lerp(-260, 668, E.inSine(u)), s: 1.15, r: lerp(-420, -126, E.outCubic(u)), mood: "squint", sq: -0.2 }; }
    if (t < 71.45) return { x: 566, y: 668, s: 1.15, r: -126, sq: wob(t - 71.3, 3.5, 6) * 0.25, mood: "happy", o: 1 - prog(t, 71.3, 71.45) };
    if (t < 73.7) return { hidden: true };
    const up = spring(t - 73.7, 1.8, 0.45);
    return Object.assign(I, { x: 540, y: lerp(2080, 1830, up), s: 0.9, mood: t > 74.6 && t < 75.3 ? "smug" : "happy", ly: -1 });
  },
});
