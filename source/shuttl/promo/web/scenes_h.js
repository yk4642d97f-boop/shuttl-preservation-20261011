// ── S7 · 05 落点·移动 (47.6 – 53.8 s) and S8 · 06 记分 (53.4 – 59.4 s)
const S7M = { x: 170, y: 1805 }, S8M = { x: 890, y: 1740 };
function courtSVG(parent, w, h) {
  const s = sv("svg", { width: w, height: h, style: "position:absolute;left:0;top:0;overflow:visible" }, parent);
  sv("rect", { x: 0, y: 0, width: w, height: h, rx: 10, fill: "#B9D66A", stroke: "#221B2E", "stroke-width": 4 }, s);
  const X = x => (x + 6.7) / 13.4 * w, Y = y => (y + 3.05) / 6.1 * h, L = { stroke: "#FFFBF4", "stroke-width": 3.5 };
  for (const x of [-5.94, -1.98, 1.98, 5.94]) sv("line", Object.assign({ x1: X(x), y1: 0, x2: X(x), y2: h }, L), s);
  for (const y of [-2.59, 2.59]) sv("line", Object.assign({ x1: 0, y1: Y(y), x2: w, y2: Y(y) }, L), s);
  sv("line", Object.assign({ x1: 0, y1: h / 2, x2: X(-1.98), y2: h / 2 }, L), s);
  sv("line", Object.assign({ x1: X(1.98), y1: h / 2, x2: w, y2: h / 2 }, L), s);
  sv("line", { x1: w / 2, y1: -8, x2: w / 2, y2: h + 8, stroke: "#221B2E", "stroke-width": 6, "stroke-dasharray": "3 7", "stroke-linecap": "round" }, s);
  return { s, X, Y };
}
const LAND7 = [[-6.3, 1.9, 0], [5.9, -2.2, 1], [-4.8, -2.7, 0], [6.4, 0.6, 1], [-2.3, 0.4, 0], [4.9, 2.6, 1], [-6.1, -0.6, 0], [2.4, -1.4, 1],
  [-5.5, 2.8, 1], [6.2, 2.1, 1], [-3.2, -2.2, 0], [5.4, -0.9, 1], [-6.5, -2.4, 0], [3.3, 2.7, 1]];
S({
  t0: 47.6, t1: 53.8, z: 31,
  build(root) {
    const c = this;
    c.chap = el("div", "chap abs", root, "<b>05</b>落点 · 移动");
    c.h = headline(root, "球落哪儿，\n人跑哪儿。");
    c.cards = ["落点地图 · 每个印章是一分", "场上移动 · 点越大，停留越久"].map((lb, k) => {
      const cd = css(el("div", "card abs", root), { width: "920px", height: "486px" });
      css(el("div", "chap abs", cd, lb), { left: "40px", top: "26px", fontSize: "28px", letterSpacing: "3px" });
      const cr = css(el("div", "abs", cd), { left: "76px", top: "80px" });
      const ct = courtSVG(cr, 760, 346);
      css(el("div", "chap abs", cd, "← 近端"), { left: "76px", top: "440px", fontSize: "24px", letterSpacing: "2px" });
      css(el("div", "chap abs", cd, "远端 →"), { left: "auto", right: "76px", top: "440px", fontSize: "24px", letterSpacing: "2px" });
      return { cd, ct };
    });
    const A = c.cards[0].ct;
    c.stamps = LAND7.map(([x, y, far], i) => {
      const g = sv("g", {}, A.s);
      sv("circle", { cx: 0, cy: 0, r: 25, fill: far ? "#2F4BDE" : "#FF7AB6", stroke: "#221B2E", "stroke-width": 4 }, g);
      const tx = sv("text", { x: 0, y: 9, "text-anchor": "middle", "font-family": "NY", "font-weight": 900, "font-size": 26, fill: far ? "#FFFBF4" : "#221B2E" }, g);
      tx.textContent = i + 1;
      return { g, x: A.X(x), y: A.Y(y), t: 48.75 + i * 0.1 };
    });
    const B = c.cards[1].ct;
    c.dots = [];
    for (let x = -6.3; x < -0.4; x += 0.55) for (let y = -2.8; y <= 2.85; y += 0.56) {
      const hsum = 1.0 * Math.exp(-(((x + 5.2) ** 2) / 1.3 + (y ** 2) / 2.4)) + 0.7 * Math.exp(-(((x + 2.2) ** 2) / 0.6 + ((y - 0.5) ** 2) / 1.2)) + 0.6 * Math.exp(-(((x + 5.6) ** 2) / 0.5 + ((y - 2.2) ** 2) / 0.4));
      c.dots.push({ e: sv("circle", { cx: B.X(x), cy: B.Y(y), r: 0, fill: "#2F4BDE" }, B.s), r: 3 + 16 * clamp(hsum), x });
    }
    c.pct = css(el("div", "abs", c.cards[1].cd), { left: "476px", top: "140px", textAlign: "center", width: "340px" });
    c.pctN = el("div", "num", c.pct); c.pctN.style.fontSize = "150px";
    el("div", "", c.pct, "覆盖了半场").style.cssText = "font:600 36px 'PingFang SC';margin-top:6px";
    LAND7.forEach((_, i) => cue(48.75 + i * 0.1, "stamp", { gain: .35, pitch: hash(i) }));
    cue(50.6, "rise", { gain: .4, dur: .6 }); cue(51.4, "ratchet", { dur: .45, gain: .35 }); cue(51.85, "pop", { pitch: .8 });
    cue(53.4, "whoosh", { gain: .6, dur: .45 });
    BUBBLES.add(51.95, 53.3, "又往后场跑？地图上一清二楚。", "r");
  },
  update(lt, t) {
    const c = this, ox = W * (1 - E.ioCubic(prog(t, 47.6, 48.0))) - W * E.ioCubic(prog(t, 53.4, 53.8));
    this.root.style.transform = ox ? `translateX(${ox}px)` : "";
    putTL(c.chap, 80, 150, 1, 0, clamp((t - 47.95) * 5));
    putTL(c.h.el, 80, 200); popChars(c.h, t, 48.0, 0.045);
    c.cards.forEach(({ cd }, k) => { const s = spring(t - 48.35 - k * 1.8, 1.9, 0.5); putTL(cd, 80, [500, 1020][k] + (1 - s) * 260, 1, 0, clamp(s * 2)); });
    c.stamps.forEach(({ g, x, y, t: t0 }) => { const s = spring(t - t0, 3, 0.35); g.setAttribute("transform", `translate(${x},${y}) scale(${t < t0 ? 0 : lerp(1.8, 1, s)})`); g.setAttribute("opacity", clamp((t - t0) * 8)); });
    c.dots.forEach(d => { const u = spring(t - 50.6 - (d.x + 6.3) * 0.12, 2.2, 0.5); d.e.setAttribute("r", Math.max(0, d.r * u).toFixed(2)); });
    c.pctN.textContent = Math.round(44 * E.outCubic(prog(t, 51.4, 51.85))) + "%";
    c.pct.style.opacity = clamp((t - 51.35) * 5);
  },
  pose(lt, t) {
    if (t < 51.5) return { hidden: true };
    const I = idle(t, 7.1), h = hop(t, 51.5, 51.9, { x: -150, y: 1650 }, S7M, 200);
    if (t < 51.9) return Object.assign(h, { s: 0.9, mood: "happy" });
    if (t > 53.4) return Object.assign(hop(t, 53.4, 53.8, S7M, { x: -300, y: 1750 }, 160), { s: 0.9 });
    return Object.assign(I, { x: S7M.x, y: S7M.y, s: 0.9, sq: I.sq + h.sq, mood: "smug", lx: 0.8, ly: -0.8 });
  },
});
