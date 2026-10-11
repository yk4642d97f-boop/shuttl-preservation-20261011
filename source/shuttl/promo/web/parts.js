// Speech bubbles (typewriter, blips), phone frame, headline splitter, shot chips, squiggle.
const BUBBLES = (() => {
  const list = [];
  let layer;
  function build(parent) { layer = el("div", "", parent); layer.id = "bubbles"; }
  // side: "r" bubble to the upper-right of the mascot, "l" upper-left. at: optional fixed anchor {x,y}.
  function add(t0, t1, text, side = "r", o = {}) {
    const b = el("div", "bubble" + (side === "l" ? " left" : ""), layer);
    if (o.size) b.style.fontSize = o.size + "px";
    const spans = [];
    for (const line of text.split("\n")) {
      const row = el("div", "", b);
      for (const ch of line) spans.push(el("span", "c", row, ch === " " ? "&nbsp;" : ch));
    }
    el("div", "tail", b);
    const rate = o.rate ?? 22;
    const item = { t0, t1, b, spans, side, rate, shown: -1, at: o.at, dx: o.dx ?? 0, dy: o.dy ?? 0 };
    list.push(item);
    cue(t0, "boop", { gain: .5 });
    let n = 0;
    spans.forEach((s, i) => {
      if (/[，。？！、…—：·\s]/.test(s.textContent)) return;
      if (n++ % 2 === 0 && n < 16) cue(t0 + 0.08 + i / rate, "blip", { pitch: hash(i + t0) });
    });
    return item;
  }
  function update(t, anchor) {
    for (const it of list) {
      const on = t >= it.t0 - 0.01 && t < it.t1 + 0.25;
      if (!on) { if (it.b.style.visibility !== "hidden") it.b.style.visibility = "hidden"; continue; }
      const a = it.at || anchor;
      if (!a) { it.b.style.visibility = "hidden"; continue; }
      const k = Math.floor(clamp((t - it.t0 - 0.08) * it.rate, 0, it.spans.length));
      if (k !== it.shown) { it.spans.forEach((s, i) => s.style.display = i < k ? "inline" : "none"); it.shown = k; }
      const inS = spring(t - it.t0, 3.2, 0.36), outS = t > it.t1 ? 1 - E.inCubic(prog(t, it.t1, it.t1 + 0.22)) : 1;
      const s = Math.max(0, inS * outS);
      const w = it.b.offsetWidth, h = it.b.offsetHeight;
      let x = it.side === "l" ? a.x - w + 70 + it.dx : a.x - 70 + it.dx;
      x = clamp(x, 36, W - 36 - w);
      const y = a.y - h - 34 + it.dy;
      it.b.style.transformOrigin = it.side === "l" ? "88% 110%" : "12% 110%";
      it.b.style.transform = `translate(${x}px,${y}px) scale(${s}) rotate(${(1 - s) * (it.side === "l" ? 6 : -6)}deg)`;
      it.b.style.visibility = s < 0.01 ? "hidden" : "visible";
    }
  }
  return { build, add, update };
})();

// iPhone frame around a stack of screenshots. w = outer width.
function phone(parent, shots, w = 540) {
  const pad = 12, sw = w - pad * 2, sh = sw * 2622 / 1206, h = sh + pad * 2;
  const p = el("div", "phone", parent);
  css(p, { width: w + "px", height: h + "px", "--ro": (w * 0.155) + "px", "--ri": (sw * 0.146) + "px" });
  const shadow = el("div", "shadow", p);
  el("div", "rim", p); el("div", "bez", p);
  for (const [top, len, side] of [[0.17, 0.055, -1], [0.25, 0.09, -1], [0.36, 0.09, -1], [0.29, 0.14, 1]]) {
    const b = el("div", "btn", p);
    css(b, { top: h * top + "px", height: h * len + "px", width: "7px", [side < 0 ? "left" : "right"]: "-5px" });
  }
  const scr = el("div", "scr", p);
  const imgs = {};
  for (const n of shots) { const i = el("img", "", scr); i.src = `../assets/shots/${n}.png`; imgs[n] = i; }
  return {
    el: p, w, h, scr, shadow,
    // op: {name: opacity}
    show(op) { for (const n in imgs) imgs[n].style.opacity = op[n] ?? 0; },
  };
}

// Split a headline into per-character spans. Returns {el, chars}
function headline(parent, text, cls = "hl") {
  const e = el("div", cls + " abs", parent);
  const chars = [];
  text.split("\n").forEach((line, li) => {
    const row = el("div", "", e);
    for (const ch of line) chars.push(el("span", "ch", row, ch));
  });
  return { el: e, chars };
}
// Character pop-in with stagger; out = exit start (chars fly up).
function popChars(h, t, t0, stagger = 0.045, out = 1e9, dy = 90) {
  h.chars.forEach((c, i) => {
    const s = spring(t - t0 - i * stagger, 2.4, 0.42);
    const o = clamp((t - t0 - i * stagger) * 8);
    const q = E.inCubic(prog(t, out + i * 0.02, out + 0.28 + i * 0.02));
    c.style.transform = `translateY(${(1 - s) * dy - q * 120}px) rotate(${(1 - s) * 8}deg)`;
    c.style.opacity = o * (1 - q);
  });
}

// Shot glyph flights (unit square, y down) from ShotGlyph.swift
const GLYPH = {
  smash: [[.12, .14], [.45, .36], [.88, .86]], kill: [[.34, .20], [.50, .40], [.70, .86]],
  clear: [[.12, .44], [.50, -.34], [.90, .60]], lift: [[.30, .82], [.60, -.30], [.92, .58]],
  drop: [[.10, .20], [.46, .14], [.66, .86]], net: [[.34, .66], [.50, .14], [.66, .66]],
  block: [[.30, .52], [.46, .30], [.62, .84]], drive: [[.10, .44], [.50, .36], [.90, .48]],
  push: [[.30, .48], [.52, .34], [.84, .72]], serve: [[.12, .76], [.46, .00], [.74, .70]],
};
const SHOT = {
  smash: ["扣杀", "#F2542D"], kill: ["扑球", "#F2542D"], clear: ["高远", "#2F4BDE"], lift: ["挑球", "#2F4BDE"],
  drop: ["吊球", "#C7B6F2"], net: ["网前", "#B9D66A"], block: ["挡网", "#B9D66A"], drive: ["平抽", "#F7D95C"],
  push: ["推球", "#F7D95C"], serve: ["发球", "#FF7AB6"],
};
// A ShotChip tile. Returns {el, flight} — flight path uses pathLength=1 for draw-on.
function chip(parent, kind, size = 150) {
  const onInk = kind === "clear" || kind === "lift" ? "#FFFBF4" : "#221B2E";
  const box = el("div", "abs", parent);
  const sg = sv("svg", { width: size, height: size, viewBox: "0 0 100 100", style: "overflow:visible;display:block" }, box);
  sv("rect", { x: 2.75, y: 2.75, width: 94.5, height: 94.5, rx: 26, fill: SHOT[kind][1], stroke: "#221B2E", "stroke-width": 5.5 }, sg);
  const q = ([x, y]) => [14 + x * 72, 14 + y * 72];
  const [a, c, b] = GLYPH[kind].map(q);
  sv("line", { x1: 17, y1: 80, x2: 83, y2: 80, stroke: onInk, "stroke-opacity": .45, "stroke-width": 3.6, "stroke-linecap": "round" }, sg);
  sv("line", { x1: 50, y1: 80, x2: 50, y2: 56, stroke: onInk, "stroke-width": 5, "stroke-linecap": "round" }, sg);
  const f = sv("path", { d: `M${a} Q${c} ${b}`, pathLength: 1, class: "draw", stroke: onInk, "stroke-width": 6.1, "stroke-linecap": "round", "stroke-dasharray": 1, "stroke-dashoffset": 0 }, sg);
  const head = sv("circle", { cx: b[0], cy: b[1], r: 7.2, fill: onInk }, sg);
  return { el: box, flight: f, head, size };
}
function drawChip(c, u) { c.flight.setAttribute("stroke-dashoffset", 1 - u); c.head.setAttribute("opacity", u > 0.97 ? 1 : 0); }

// Hand-drawn squiggle underline; returns path for draw-on (pathLength 1).
function squiggle(parent, w, color = "#2F4BDE", amp = 11, waves = 5) {
  const s = sv("svg", { width: w + 20, height: amp * 2 + 20, style: "position:absolute;left:0;top:0;overflow:visible" }, parent);
  let d = `M10 ${amp + 10}`; const step = w / (waves * 2);
  for (let i = 0; i < waves * 2; i++) d += ` q${step / 2} ${i % 2 ? amp * 2 : -amp * 2} ${step} 0`;
  const p = sv("path", { d, pathLength: 1, fill: "none", stroke: color, "stroke-width": 11, "stroke-linecap": "round", "stroke-dasharray": 1, "stroke-dashoffset": 1 }, s);
  return { svg: s, path: p, set(u) { p.setAttribute("stroke-dashoffset", 1 - u); } };
}
