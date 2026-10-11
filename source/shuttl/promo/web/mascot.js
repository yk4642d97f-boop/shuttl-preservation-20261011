// The shuttlecock character: ShuttlecockMark's skirt + an oversized plush cork with a face.
// viewBox 0..120, visual centre (the pose point) at (60, 64).
const MASCOT = (() => {
  let root, body, skirt, faceG, eyes, moods = {}, cur = null;
  const C = { x: 60, y: 64 }, MS = 250;

  function build(parent) {
    root = el("div", "", parent); root.id = "mascot";
    const svg = sv("svg", { viewBox: "0 0 120 120" }, root);
    body = sv("g", {}, svg);
    // Feather skirt (scalloped top, ribs, thread band) — pivot at the band so it can jiggle.
    skirt = sv("g", { style: "transform-origin:60px 58px" }, body);
    let d = "M44 70 L16 16";
    const step = (104 - 16) / 6;
    for (let i = 0; i < 6; i++) { const x0 = 16 + i * step; d += ` Q${x0 + step / 2} 6 ${x0 + step} 16`; }
    d += " L76 70 Z";
    sv("path", { d, fill: "#FFFBF4", stroke: "none" }, skirt);
    for (let i = 1; i < 6; i++) {
      const u = i / 6;
      sv("line", { x1: 44 + 32 * u, y1: 70, x2: 16 + 88 * u, y2: 16, stroke: "#221B2E", "stroke-opacity": .5, "stroke-width": 2, "stroke-linecap": "round" }, skirt);
    }
    sv("line", { x1: 31, y1: 45, x2: 89, y2: 45, stroke: "#221B2E", "stroke-width": 5, "stroke-linecap": "round" }, skirt);
    sv("path", { d, fill: "none", stroke: "#221B2E", "stroke-width": 4.2, "stroke-linejoin": "round" }, skirt);
    // Cork
    const cork = "M34 70 L86 70 A26 26 0 0 1 34 70 Z";
    sv("path", { d: cork, fill: "#F2542D" }, body);
    const clip = sv("clipPath", { id: "corkClip" }, svg);
    sv("path", { d: cork }, clip);
    const dots = sv("g", { "clip-path": "url(#corkClip)", fill: "#221B2E", opacity: .16 }, body);
    for (let y = 72; y < 98; y += 4) for (let x = 36; x < 88; x += 4) {
      const k = clamp(((x - 50) + (y - 76)) / 34);
      if (k > 0.05) sv("circle", { cx: x + ((y / 4) % 2) * 2, cy: y, r: 1.5 * k }, dots);
    }
    sv("path", { d: "M40 74 Q48 72 56 73", fill: "none", stroke: "#FFFBF4", "stroke-opacity": .55, "stroke-width": 2.4, "stroke-linecap": "round" }, body);
    sv("path", { d: cork, fill: "none", stroke: "#221B2E", "stroke-width": 4.2, "stroke-linejoin": "round" }, body);
    // Face
    faceG = sv("g", {}, body);
    sv("ellipse", { cx: 42, cy: 86, rx: 4.2, ry: 2.6, fill: "#FF7AB6", opacity: .9 }, faceG);
    sv("ellipse", { cx: 78, cy: 86, rx: 4.2, ry: 2.6, fill: "#FF7AB6", opacity: .9 }, faceG);
    const ink = { fill: "none", stroke: "#221B2E", "stroke-width": 2.8, "stroke-linecap": "round", "stroke-linejoin": "round" };
    const g = n => (moods[n] = sv("g", { style: "display:none" }, faceG));
    // normal: tall eyes with glints
    eyes = sv("g", { style: "transform-origin:60px 80px" }, g("normal"));
    for (const x of [50, 70]) {
      sv("ellipse", { cx: x, cy: 80, rx: 3.4, ry: 4.6, fill: "#221B2E" }, eyes);
      sv("circle", { cx: x + 1.2, cy: 78.2, r: 1.3, fill: "#FFFBF4" }, eyes);
    }
    sv("path", Object.assign({ d: "M56 88 Q60 91.5 64 88" }, ink), moods.normal);
    sv("path", Object.assign({ d: "M46 81 Q50 76 54 81 M66 81 Q70 76 74 81" }, ink), g("happy"));
    sv("path", Object.assign({ d: "M55 87 Q60 94 65 87 Z", fill: "#221B2E" }, { stroke: "none" }), moods.happy);
    for (const x of [50, 70]) sv("circle", { cx: x, cy: 80, r: 4.6, fill: "#FFFBF4", stroke: "#221B2E", "stroke-width": 2.4 }, g("wow"));
    for (const x of [50, 70]) sv("circle", { cx: x, cy: 80, r: 2, fill: "#221B2E" }, moods.wow);
    sv("ellipse", { cx: 60, cy: 90, rx: 2.6, ry: 3.2, fill: "#221B2E" }, moods.wow);
    for (const x of [50, 70]) sv("path", Object.assign({ d: `M${x} 80 m-4 0 a4 4 0 1 1 4 4 a2.6 2.6 0 1 1 -2.4 -2.8` }, ink), g("dizzy"));
    sv("path", Object.assign({ d: "M55 90 q2.5 -2.5 5 0 q2.5 2.5 5 0" }, ink), moods.dizzy);
    sv("path", Object.assign({ d: "M46 77 L53 80 L46 83 M74 77 L67 80 L74 83" }, ink), g("squint"));
    sv("path", Object.assign({ d: "M55 89 L65 89" }, ink), moods.squint);
    sv("path", Object.assign({ d: "M46 80 L54 80 M66 80 L74 80" }, ink), g("smug"));
    sv("path", Object.assign({ d: "M55 87 Q61 91 66 86" }, ink), moods.smug);
    mood("normal");
  }
  function mood(n) {
    if (n === cur) return;
    for (const k in moods) moods[k].style.display = k === n ? "inline" : "none";
    cur = n;
  }
  // p: {x,y,s,r,sq,lx,ly,mood,blink,wig,o,hidden}. Returns the bubble anchor (head top).
  function set(p) {
    if (p.hidden || p.o === 0) { root.style.visibility = "hidden"; return null; }
    root.style.visibility = "visible";
    const s = p.s ?? 1, r = p.r ?? 0, sq = p.sq ?? 0;
    const sx = 1 + sq * 0.55, sy = 1 - sq;
    root.style.opacity = p.o ?? 1;
    root.style.transformOrigin = `${C.x / 120 * MS}px ${C.y / 120 * MS}px`;
    root.style.transform = `translate(${p.x - C.x / 120 * MS}px,${p.y - C.y / 120 * MS}px) rotate(${r}deg) scale(${s * sx},${s * sy})`;
    skirt.style.transform = `rotate(${p.wig ?? 0}deg)`;
    faceG.setAttribute("transform", `translate(${(p.lx ?? 0) * 3.5},${(p.ly ?? 0) * 2.5})`);
    mood(p.mood || "normal");
    eyes.style.transform = `scaleY(${1 - (p.blink ?? 0) * 0.9})`;
    return { x: p.x, y: p.y - 109 * s, s, r };
  }
  return { build, set };
})();

// Idle life: breathing, feather sway, blinks. Merge into any standing pose.
function idle(t, seed = 0) {
  const ph = t * 2 * Math.PI;
  const bl = (t + seed) % 3.1;
  return {
    sq: 0.025 * Math.sin(ph * 1.1),
    wig: 2.2 * Math.sin(ph * 0.9 + seed),
    blink: bl < 0.14 ? Math.sin(bl / 0.14 * Math.PI) : 0,
  };
}

// Hop between two points: parabola + stretch in the air, squash on landing (land wobble handled by caller).
function hop(t, t0, t1, a, b, arc = 180) {
  const u = prog(t, t0, t1), e = E.ioSine(u);
  const x = lerp(a.x, b.x, e), y = lerp(a.y, b.y, e) - arc * 4 * u * (1 - u);
  const air = u > 0 && u < 1 ? Math.sin(u * Math.PI) : 0;
  const land = t >= t1 ? wob(t - t1, 3.4, 6) * 0.22 : 0;
  const pre = t < t0 && t0 - t < 0.12 ? (1 - (t0 - t) / 0.12) * 0.16 : 0;
  return { x, y, sq: -0.14 * air + land + pre, r: (b.x - a.x) * 0.02 * Math.sin(u * Math.PI * 2) };
}
