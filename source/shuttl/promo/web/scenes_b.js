// ── S1 · Reveal (5.55 – 12.5 s): the phone rises, "Shuttl." + "看清，每一拍。"
const S1M = { x: 905, y: 1575 };
S({
  t0: 5.55, t1: 12.5, z: 22,
  build(root) {
    const c = this;
    c.ph = phone(root, ["detail", "matches"], 540);
    c.wm = el("div", "abs", root); css(c.wm, { font: "italic 900 200px NY", whiteSpace: "nowrap", letterSpacing: "-5px", lineHeight: 1 });
    c.letters = [..."Shuttl"].map(ch => css(el("span", "", c.wm, ch), { display: "inline-block" }));
    c.dot = css(el("span", "", c.wm, "."), { display: "inline-block", color: "var(--tomato)" });
    c.h = headline(root, "看清，每一拍。");
    c.sq = squiggle(c.h.el, 330, "#2F4BDE"); css(c.sq.svg, { left: "42%", top: "118px" });
    c.sub = el("div", "abs body", root, "一台 iPhone，一个三脚架。剩下的，交给 AI。");
    css(c.sub, { fontSize: "42px", color: "var(--inkSoft)", whiteSpace: "nowrap" });
    cue(5.62, "rise", { gain: .7 }); cue(6.15, "swish", { gain: .6 }); cue(6.86, "pop", { pitch: .9, gain: .9 });
    cue(7.2, "pop", { pitch: .5 }); cue(7.75, "scribble", { gain: .5 }); cue(9.62, "swish", { gain: .45 });
    cue(11.95, "whoosh", { gain: .7, dur: .5 });
    BUBBLES.add(8.55, 9.95, "终于有人给我写传记了。", "l");
  },
  update(lt, t) {
    const c = this, ox = -W * E.ioCubic(prog(t, 11.95, 12.5));
    this.root.style.transform = ox ? `translateX(${ox}px)` : "";
    // phone
    const u = spring(t - 5.6, 1.35, 0.5), fl = 7 * Math.sin((t - 6) * 1.7);
    const y = lerp(2500, 1330, u) + fl * clamp(t - 6.3), rx = lerp(34, 5, u), ry = lerp(-22, -9, u), rz = lerp(10, -3, u);
    c.ph.el.style.transform = `translate(${540 - c.ph.w / 2}px,${y - c.ph.h / 2}px) perspective(2600px) rotateX(${rx}deg) rotateY(${ry}deg) rotate(${rz}deg)`;
    const x = prog(t, 9.55, 9.8);
    c.ph.show({ detail: 1 - x, matches: x });
    // wordmark
    put(c.wm, 540, 200, 1, 0, t > 6.1 ? 1 : 0);
    c.letters.forEach((l, i) => { const s = spring(t - 6.15 - i * 0.05, 2.4, 0.45); l.style.transform = `translateY(${(1 - s) * 140}px) rotate(${(1 - s) * -10}deg)`; l.style.opacity = clamp(s * 3); });
    const dt = t - 6.86;
    let dy = dt < 0 ? -1100 * (1 - clamp((t - 6.55) / 0.31)) ** 2 : -95 * Math.abs(Math.sin(dt * 7)) * Math.exp(-dt * 5.5);
    const dsq = dt > 0 ? wob(dt, 3.5, 6) * 0.35 : -0.2;
    c.dot.style.transform = `translateY(${dy}px) scale(${1 + dsq * 0.6},${1 - dsq})`;
    c.dot.style.transformOrigin = "50% 85%"; c.dot.style.opacity = t > 6.55 ? 1 : 0;
    put(c.h.el, 540, 420, 1, 0, 1);
    popChars(c.h, t, 7.2, 0.045);
    c.sq.set(E.outCubic(prog(t, 7.75, 8.2)));
    const su = E.outCubic(prog(t, 8.2, 8.6));
    put(c.sub, 540, 560 + (1 - su) * 24, 1, 0, su);
  },
  pose(lt, t) {
    const I = idle(t, 1.3);
    if (t < 6.2) return Object.assign(hop(t, 5.62, 6.12, { x: 335, y: FLOOR0 - 67 }, S1M, 420), { mood: t < 5.95 ? "happy" : "normal", s: lerp(1, 0.95, prog(t, 5.62, 6.12)) });
    const h = hop(t, 5.62, 6.12, { x: 335, y: FLOOR0 - 67 }, S1M, 420);
    return Object.assign(I, { x: S1M.x, y: S1M.y, s: 0.95, sq: h.sq + I.sq, lx: -0.8, ly: -0.5, mood: t > 8.5 && t < 10 ? "happy" : "normal" });
  },
});
