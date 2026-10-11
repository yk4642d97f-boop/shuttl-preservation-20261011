/* ============================================================
   羽析 · 球场几何与绘制
   坐标系 (米): 远端左角为原点, x 向右 0~6.10, y 向近端 0~13.40, 球网 y=6.70
   ============================================================ */
const Court = (() => {
  const W = 6.10, L = 13.40, NET = 6.70, SM = 0.46, SS = 1.98, DL = 0.76;
  const C = { court: "#1D6B4F", deep: "#0B2E23", line: "#FFFFFF", out: "#E5452F", review: "#F2C230",
              near: "#FFB340", far: "#A9A6FF", nearOn: "#FFB340", farOn: "#A9A6FF" };

  function segments() {
    return [
      [[0, 0], [W, 0]], [[0, L], [W, L]],
      [[0, 0], [0, L]], [[W, 0], [W, L]],
      [[SM, 0], [SM, L]], [[W - SM, 0], [W - SM, L]],
      [[0, NET - SS], [W, NET - SS]], [[0, NET + SS], [W, NET + SS]],
      [[0, DL], [W, DL]], [[0, L - DL], [W, L - DL]],
      [[W / 2, 0], [W / 2, NET - SS]], [[W / 2, NET + SS], [W / 2, L]],
    ];
  }

  // ---------- 透视变换 (与后端 court.py 一致) ----------
  function orderCorners(pts) {
    const s = [...pts].sort((a, b) => a[1] - b[1]);
    const top = s.slice(0, 2).sort((a, b) => a[0] - b[0]);
    const bot = s.slice(2).sort((a, b) => a[0] - b[0]);
    return [top[0], top[1], bot[1], bot[0]];           // 远左 远右 近右 近左
  }
  function solve(A, b) {                                  // 高斯消元
    const n = b.length, M = A.map((r, i) => [...r, b[i]]);
    for (let c = 0; c < n; c++) {
      let p = c;
      for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
      [M[c], M[p]] = [M[p], M[c]];
      for (let r = 0; r < n; r++) if (r !== c) {
        const f = M[r][c] / M[c][c];
        for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
      }
    }
    return M.map((r, i) => r[n] / r[i]);
  }
  function homography(src, dst) {                         // src -> dst, 4 点
    const A = [], b = [];
    for (let i = 0; i < 4; i++) {
      const [x, y] = src[i], [u, v] = dst[i];
      A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.push(u);
      A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); b.push(v);
    }
    const h = solve(A, b);
    return [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1]];
  }
  function apply(H, [x, y]) {
    const w = H[2][0] * x + H[2][1] * y + H[2][2];
    return [(H[0][0] * x + H[0][1] * y + H[0][2]) / w, (H[1][0] * x + H[1][1] * y + H[1][2]) / w];
  }
  /** 米 -> 像素 的变换 (用于在视频帧上叠加场线) */
  function metersToPixels(cornersPx) {
    return homography([[0, 0], [W, 0], [W, L], [0, L]], orderCorners(cornersPx));
  }

  // ---------- SVG 工具 ----------
  const NS = "http://www.w3.org/2000/svg";
  function el(tag, attrs = {}, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }

  /** 俯视球场 (竖向, 远端在上) */
  function svgCourt({ pad = 0.7, lineW = 0.05, showNet = true, bg = true } = {}) {
    const svg = el("svg", { viewBox: `${-pad} ${-pad} ${W + 2 * pad} ${L + 2 * pad}`, class: "court-svg", role: "img" });
    if (bg) el("rect", { x: -pad, y: -pad, width: W + 2 * pad, height: L + 2 * pad, fill: C.deep }, svg);
    el("rect", { x: 0, y: 0, width: W, height: L, fill: C.court }, svg);
    const g = el("g", { stroke: C.line, "stroke-width": lineW, "stroke-linecap": "square" }, svg);
    for (const [[x1, y1], [x2, y2]] of segments()) el("line", { x1, y1, x2, y2 }, g);
    if (showNet) {
      el("line", { x1: -0.25, y1: NET, x2: W + 0.25, y2: NET, stroke: "#0B1F18", "stroke-width": 0.09 }, svg);
      el("line", { x1: -0.25, y1: NET, x2: W + 0.25, y2: NET, stroke: "#fff", "stroke-width": 0.03, "stroke-dasharray": "0.06 0.06", opacity: 0.55 }, svg);
      el("circle", { cx: -0.25, cy: NET, r: 0.07, fill: "#fff" }, svg);
      el("circle", { cx: W + 0.25, cy: NET, r: 0.07, fill: "#fff" }, svg);
    }
    return svg;
  }

  /** 落点标记: 界内白点 / 出界红叉 / 存疑黄圈 */
  function landingMark(parent, [x, y], state, r = 0.14) {
    const g = el("g", {}, parent);
    if (state === "out") {
      const d = r * 0.95;
      el("path", { d: `M${x - d} ${y - d}L${x + d} ${y + d}M${x + d} ${y - d}L${x - d} ${y + d}`, stroke: C.out, "stroke-width": r * 0.62, "stroke-linecap": "round" }, g);
    } else {
      el("circle", { cx: x, cy: y, r, fill: "#fff", stroke: C.deep, "stroke-width": r * 0.25 }, g);
    }
    if (state === "review") el("circle", { cx: x, cy: y, r: r * 1.9, fill: "none", stroke: C.review, "stroke-width": r * 0.4 }, g);
    return g;
  }

  /** 热图: 大量半透明圆叠加 */
  function heat(parent, pts, color, r = 0.75, alpha = 0.16) {
    const id = "hg" + Math.random().toString(36).slice(2, 8);
    const defs = el("defs", {}, parent);
    const rg = el("radialGradient", { id }, defs);
    el("stop", { offset: "0%", "stop-color": color, "stop-opacity": alpha * 2.2 }, rg);
    el("stop", { offset: "100%", "stop-color": color, "stop-opacity": 0 }, rg);
    const g = el("g", {}, parent);
    for (const [x, y] of pts) el("circle", { cx: x, cy: y, r, fill: `url(#${id})` }, g);
    return g;
  }

  /** 鹰眼挑战卡: 放大落点附近, 标出距最近边线的距离 */
  function hawkEye(landing, matchType) {
    const [lx, ly] = landing.m;
    const vw = 2.6, vh = 1.55;
    const x0 = lx - vw / 2, y0 = ly - vh / 2;
    const svg = el("svg", { viewBox: `${x0} ${y0} ${vw} ${vh}`, role: "img", "aria-label": "落点放大图" });
    el("rect", { x: x0 - 1, y: y0 - 1, width: vw + 2, height: vh + 2, fill: C.deep }, svg);
    const clip = "hc" + Math.random().toString(36).slice(2, 7);
    const cp = el("clipPath", { id: clip }, el("defs", {}, svg));
    el("rect", { x: 0, y: 0, width: W, height: L }, cp);
    el("rect", { x: 0, y: 0, width: W, height: L, fill: C.court }, svg);
    // 地胶纹理: 细密斜线
    const pat = "hp" + Math.random().toString(36).slice(2, 7);
    const pt = el("pattern", { id: pat, width: 0.08, height: 0.08, patternUnits: "userSpaceOnUse", patternTransform: "rotate(30)" }, svg.querySelector("defs"));
    el("line", { x1: 0, y1: 0, x2: 0, y2: 0.08, stroke: "#fff", "stroke-width": 0.006, opacity: 0.08 }, pt);
    el("rect", { x: 0, y: 0, width: W, height: L, fill: `url(#${pat})` }, svg);
    const g = el("g", { stroke: C.line, "stroke-width": 0.04, "stroke-linecap": "butt" }, svg);
    for (const [[x1, y1], [x2, y2]] of segments()) el("line", { x1, y1, x2, y2 }, g);
    el("line", { x1: -0.3, y1: NET, x2: W + 0.3, y2: NET, stroke: "#0B1F18", "stroke-width": 0.06 }, svg);

    // 相关边界线高亮
    const singles = matchType !== "doubles";
    const xl = singles ? SM : 0, xr = singles ? W - SM : W;
    const side = ly < NET ? "far" : "near";
    const yb = side === "far" ? 0 : L;
    let target = null;
    const nearNet = landing.net_dist_m != null && landing.net_dist_m < 0.4;
    if (nearNet) target = [[lx, NET], [lx, NET]];
    else if (landing.line === "左边线") target = [[xl, ly], [xl, ly]];
    else if (landing.line === "右边线") target = [[xr, ly], [xr, ly]];
    else target = [[lx, yb], [lx, yb]];
    const isOut = !landing.in, review = landing.uncertain;
    if (!nearNet) {
      const hl = landing.line === "底线" ? [[x0, yb], [x0 + vw, yb]] : [[target[0][0], y0], [target[0][0], y0 + vh]];
      el("line", { x1: hl[0][0], y1: hl[0][1], x2: hl[1][0], y2: hl[1][1], stroke: "#fff", "stroke-width": 0.05, opacity: 0.95 }, svg);
    } else {
      el("line", { x1: x0, y1: NET, x2: x0 + vw, y2: NET, stroke: C.review, "stroke-width": 0.02, opacity: 0.9 }, svg);
    }

    // 距离标注线
    const [tx, ty] = target[0];
    if (Math.hypot(tx - lx, ty - ly) > 0.02) {
      el("line", { x1: lx, y1: ly, x2: tx, y2: ty, stroke: review ? C.review : (isOut ? "#FF8C7D" : "#fff"), "stroke-width": 0.018, "stroke-dasharray": "0.04 0.03" }, svg);
    }
    // 羽毛球落地印: 椭圆阴影 + 球头
    el("ellipse", { cx: lx, cy: ly, rx: 0.075, ry: 0.05, fill: "#000", opacity: 0.28 }, svg);
    const ring = review ? C.review : (isOut ? C.out : "#fff");
    el("circle", { cx: lx, cy: ly, r: 0.1, fill: "none", stroke: ring, "stroke-width": 0.022 }, svg);
    el("circle", { cx: lx, cy: ly, r: 0.034, fill: "#fff" }, svg);
    return svg;
  }

  /** 首页列表里的迷你球场 */
  function mini(landings) {
    const svg = svgCourt({ pad: 0.35, lineW: 0.09, showNet: true });
    svg.setAttribute("class", "mini");
    for (const [x, y, inn] of (landings || [])) landingMark(svg, [x, y], inn ? "in" : "out", 0.3);
    return svg;
  }

  /** 拍摄指南插图 (侧视) */
  function guideSVG() {
    const s = el("svg", { viewBox: "0 0 320 120", role: "img", "aria-label": "拍摄机位示意: 手机架在底线后方, 高约 1.5 到 2 米, 横屏拍全场" });
    el("rect", { x: 0, y: 96, width: 320, height: 24, fill: "rgba(118,118,128,.14)" }, s);
    el("rect", { x: 70, y: 94, width: 236, height: 4, fill: C.court }, s);
    el("line", { x1: 188, y1: 94, x2: 188, y2: 64, stroke: "currentColor", "stroke-width": 2 }, s);
    el("rect", { x: 186, y: 64, width: 4, height: 30, fill: "currentColor" }, s);
    el("path", { d: "M188 64 L188 82", stroke: "#fff", "stroke-width": 1, "stroke-dasharray": "2 2" }, s);
    // 三脚架 + 手机
    el("path", { d: "M34 96 L42 56 L50 96 M42 56 L42 96", stroke: "currentColor", "stroke-width": 2, fill: "none" }, s);
    el("rect", { x: 36, y: 44, width: 14, height: 11, rx: 2, fill: "currentColor" }, s);
    // 视野
    el("path", { d: "M50 49 L306 90 L306 98 L50 52 Z", fill: C.review, opacity: 0.18 }, s);
    el("path", { d: "M50 47 L306 60", stroke: C.review, "stroke-width": 1.4, "stroke-dasharray": "4 3" }, s);
    el("path", { d: "M50 53 L306 98", stroke: C.review, "stroke-width": 1.4, "stroke-dasharray": "4 3" }, s);
    // 标注
    const t = (x, y, str, anchor = "start") => { const e = el("text", { x, y, "font-size": 11, fill: "currentColor", opacity: 0.6, "text-anchor": anchor, "font-family": "PingFang SC, sans-serif" }, s); e.textContent = str; };
    el("path", { d: "M26 56 L26 96", stroke: "currentColor", opacity: 0.35, "stroke-width": 1 }, s);
    el("path", { d: "M22 56 L30 56 M22 96 L30 96", stroke: "currentColor", opacity: 0.35, "stroke-width": 1 }, s);
    t(56, 34, "高 1.5–2m", "start");
    el("path", { d: "M42 108 L70 108", stroke: "currentColor", opacity: 0.35, "stroke-width": 1 }, s);
    t(56, 118, "底线后 1–3m", "middle");
    t(188, 58, "球网", "middle");
    t(300, 86, "对面底线", "end");
    return s;
  }

  /** 分析中动画: 羽毛球在迷你场地上来回飞 */
  function progressSVG() {
    const s = el("svg", { viewBox: "0 0 200 120", class: "progress-court", role: "img", "aria-label": "正在分析" });
    el("rect", { x: 10, y: 88, width: 180, height: 10, fill: C.court, rx: 1 }, s);
    el("rect", { x: 98.5, y: 58, width: 3, height: 30, fill: "currentColor" }, s);
    const path = el("path", { id: "flight", d: "M24 84 C 70 -8, 130 -8, 176 84", fill: "none", stroke: "currentColor", opacity: 0.3, "stroke-width": 1.5, "stroke-dasharray": "3 4" }, s);
    const ball = el("g", {}, s);
    el("circle", { r: 4.2, fill: "#FFCC00", stroke: "currentColor", "stroke-width": 1.4 }, ball);
    el("path", { d: "M-3 -2 L-12 -6 M-3 0 L-13 0 M-3 2 L-12 6", stroke: "currentColor", "stroke-width": 1.2 }, ball);
    const am = el("animateMotion", { dur: "1.6s", repeatCount: "indefinite", rotate: "auto", keyPoints: "0;1;0", keyTimes: "0;0.5;1", calcMode: "spline", keySplines: "0.3 0 0.7 1;0.3 0 0.7 1" }, ball);
    el("mpath", { href: "#flight" }, am);
    return s;
  }

  return { W, L, NET, SM, C, segments, orderCorners, homography, apply, metersToPixels,
           el, svgCourt, landingMark, heat, hawkEye, mini, guideSVG, progressSVG };
})();
