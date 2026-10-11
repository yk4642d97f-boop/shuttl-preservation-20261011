/* ============================================================
   羽析 · 球场几何与绘制
   坐标系 (米): 远端左角为原点, x 向右 0~6.10, y 向近端 0~13.40, 球网 y=6.70
   ============================================================ */
const Court = (() => {
  const W = 6.10, L = 13.40, NET = 6.70, SM = 0.46, SS = 1.98, DL = 0.76;
  const C = {
    surface: "#35353B", surround: "#26262A", line: "rgba(255,255,255,.62)", net: "#E9E9EE",
    near: "#2BB255", far: "#FF9500", out: "#FF453A", review: "#FFCC00", lime: "#C9E83C",
    hawk: "#1E7A4C", hawkDeep: "#15573A",
  };

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

  // ---------- SVG ----------
  const NS = "http://www.w3.org/2000/svg";
  function el(tag, attrs = {}, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }

  /**
   * 俯视球场。landscape=true 时远端在左、近端在右 (适合宽卡片)。
   * 返回 { svg, layer }: layer 内部一律用米坐标绘制; 文字请画在 svg 上, 用 toSvg() 换算位置。
   */
  function plot({ landscape = false, pad = 0.5, lineW = 0.045, surround = true } = {}) {
    const vw = (landscape ? L : W) + 2 * pad, vh = (landscape ? W : L) + 2 * pad;
    const svg = el("svg", { viewBox: `${-pad} ${-pad} ${vw} ${vh}`, class: "court-svg", role: "img" });
    if (surround) el("rect", { x: -pad, y: -pad, width: vw, height: vh, rx: 0.25, fill: C.surround }, svg);
    const layer = el("g", landscape ? { transform: "matrix(0 1 1 0 0 0)" } : {}, svg);
    el("rect", { x: 0, y: 0, width: W, height: L, fill: C.surface }, layer);
    const g = el("g", { stroke: C.line, "stroke-width": lineW, "stroke-linecap": "square" }, layer);
    for (const [[x1, y1], [x2, y2]] of segments()) el("line", { x1, y1, x2, y2 }, g);
    el("line", { x1: -0.22, y1: NET, x2: W + 0.22, y2: NET, stroke: C.net, "stroke-width": lineW * 1.9 }, layer);
    el("circle", { cx: -0.22, cy: NET, r: 0.07, fill: C.net }, layer);
    el("circle", { cx: W + 0.22, cy: NET, r: 0.07, fill: C.net }, layer);
    const toSvg = ([x, y]) => (landscape ? [y, x] : [x, y]);
    return { svg, layer, toSvg, landscape };
  }

  /**
   * 落点标记: 颜色 = 最后一拍的击球方, 形状 = 结果。
   * 界内 实心点 / 出界·下网 叉 / 存疑 黄色空心圈
   */
  function landingMark(parent, [x, y], { side, state, r = 0.17, i = 0 }) {
    const col = side === "far" ? C.far : C.near;
    const g = el("g", { class: `mark ${state}`, style: `--i:${i}` }, parent);
    el("circle", { class: "ripple", cx: x, cy: y, r: r * 2.4, fill: "none", stroke: state === "review" ? C.review : col, "stroke-width": 0.035 }, g);
    const body = el("g", { class: "body", style: `transform-origin:${x}px ${y}px` }, g);
    if (state === "out") {
      const d = r * 0.9;
      el("circle", { cx: x, cy: y, r: r * 1.15, fill: "rgba(0,0,0,.001)" }, body);
      el("path", { d: `M${x - d} ${y - d}L${x + d} ${y + d}M${x + d} ${y - d}L${x - d} ${y + d}`, stroke: C.out, "stroke-width": r * 0.55, "stroke-linecap": "round" }, body);
    } else if (state === "review") {
      el("circle", { cx: x, cy: y, r: r * 1.1, fill: "none", stroke: C.review, "stroke-width": r * 0.42 }, body);
    } else {
      el("circle", { cx: x, cy: y, r, fill: col, stroke: "rgba(0,0,0,.45)", "stroke-width": r * 0.22 }, body);
    }
    return g;
  }

  /** 热图: 大量半透明径向渐变圆叠加 */
  function heat(parent, pts, color, r = 0.8, alpha = 0.16) {
    const id = "hg" + Math.random().toString(36).slice(2, 8);
    const defs = el("defs", {}, parent);
    const rg = el("radialGradient", { id }, defs);
    el("stop", { offset: "0%", "stop-color": color, "stop-opacity": alpha * 2.4 }, rg);
    el("stop", { offset: "100%", "stop-color": color, "stop-opacity": 0 }, rg);
    const g = el("g", { class: "heat" }, parent);
    for (const [x, y] of pts) el("circle", { cx: x, cy: y, r, fill: `url(#${id})` }, g);
    return g;
  }

  /** 鹰眼俯视特写: 放大落点附近, 画出到判定线的距离 */
  function hawkEye(landing, matchType) {
    const [lx, ly] = landing.m;
    const vw = 2.6, vh = 1.5;
    const x0 = lx - vw / 2, y0 = ly - vh / 2;
    const svg = el("svg", { viewBox: `${x0} ${y0} ${vw} ${vh}`, role: "img", "aria-label": "落点俯视特写", class: "hawk-svg" });
    el("rect", { x: x0 - 1, y: y0 - 1, width: vw + 2, height: vh + 2, fill: C.hawkDeep }, svg);
    el("rect", { x: 0, y: 0, width: W, height: L, fill: C.hawk }, svg);
    const defs = el("defs", {}, svg);
    const pat = "hp" + Math.random().toString(36).slice(2, 7);
    const pt = el("pattern", { id: pat, width: 0.07, height: 0.07, patternUnits: "userSpaceOnUse", patternTransform: "rotate(35)" }, defs);
    el("line", { x1: 0, y1: 0, x2: 0, y2: 0.07, stroke: "#fff", "stroke-width": 0.006, opacity: 0.07 }, pt);
    el("rect", { x: 0, y: 0, width: W, height: L, fill: `url(#${pat})` }, svg);
    const g = el("g", { stroke: "#fff", "stroke-width": 0.04 }, svg);
    for (const [[x1, y1], [x2, y2]] of segments()) el("line", { x1, y1, x2, y2 }, g);
    el("line", { x1: -0.3, y1: NET, x2: W + 0.3, y2: NET, stroke: "#E9E9EE", "stroke-width": 0.05 }, svg);

    const singles = matchType !== "doubles";
    const xl = singles ? SM : 0, xr = singles ? W - SM : W;
    const yb = ly < NET ? 0 : L;
    const nearNet = landing.net_dist_m != null && landing.net_dist_m < 0.4;
    let tx = lx, ty = yb;
    if (nearNet) ty = NET;
    else if (landing.line === "左边线") { tx = xl; ty = ly; }
    else if (landing.line === "右边线") { tx = xr; ty = ly; }
    const review = landing.uncertain, isOut = !landing.in;
    const hl = nearNet || landing.line === "底线" ? [[x0, ty], [x0 + vw, ty]] : [[tx, y0], [tx, y0 + vh]];
    el("line", { x1: hl[0][0], y1: hl[0][1], x2: hl[1][0], y2: hl[1][1], stroke: review ? C.review : "#fff", "stroke-width": 0.05, class: "hl" }, svg);
    if (Math.hypot(tx - lx, ty - ly) > 0.02)
      el("line", { x1: lx, y1: ly, x2: tx, y2: ty, stroke: review ? C.review : isOut ? "#FF8A80" : "#fff", "stroke-width": 0.016, "stroke-dasharray": "0.04 0.03", class: "dim" }, svg);
    el("ellipse", { cx: lx, cy: ly, rx: 0.08, ry: 0.055, fill: "#000", opacity: 0.3 }, svg);
    el("circle", { cx: lx, cy: ly, r: 0.11, fill: "none", stroke: review ? C.review : isOut ? C.out : C.lime, "stroke-width": 0.022, class: "ring" }, svg);
    el("circle", { cx: lx, cy: ly, r: 0.036, fill: "#fff" }, svg);
    return svg;
  }

  /** 拍摄机位示意 (侧视) */
  function guideSVG() {
    const s = el("svg", { viewBox: "0 0 340 150", role: "img", "aria-label": "拍摄机位示意：手机架在底线后方 1 到 3 米，高 1.5 到 2 米，横屏拍全场" });
    el("rect", { x: 0, y: 118, width: 340, height: 32, fill: "#1C1C20" }, s);
    el("rect", { x: 78, y: 115, width: 248, height: 4, rx: 1, fill: C.near }, s);
    el("rect", { x: 200, y: 84, width: 3, height: 31, fill: "#E9E9EE" }, s);
    el("path", { d: "M201.5 84 L201.5 102", stroke: "#fff", "stroke-width": 1, "stroke-dasharray": "2 2", opacity: 0.5 }, s);
    el("path", { d: "M58 64 L202 106 L326 116 L326 118 L58 70 Z", fill: C.lime, opacity: 0.1 }, s);
    el("path", { d: "M58 64 L326 88", stroke: C.lime, "stroke-width": 1.3, "stroke-dasharray": "4 3", opacity: 0.8 }, s);
    el("path", { d: "M58 70 L326 118", stroke: C.lime, "stroke-width": 1.3, "stroke-dasharray": "4 3", opacity: 0.8 }, s);
    el("path", { d: "M40 118 L48 74 L56 118 M48 74 L48 118", stroke: "#8E8E93", "stroke-width": 2, fill: "none", "stroke-linecap": "round" }, s);
    el("rect", { x: 41, y: 60, width: 17, height: 13, rx: 3, fill: "#E9E9EE" }, s);
    el("circle", { cx: 54, cy: 66.5, r: 2, fill: "#1C1C20" }, s);
    const t = (x, y, str, anchor = "start", fill = "rgba(235,235,245,.6)") => { const e = el("text", { x, y, "font-size": 11, fill, "text-anchor": anchor }, s); e.textContent = str; };
    el("path", { d: "M28 66 L28 118 M24 66 L32 66 M24 118 L32 118", stroke: "rgba(235,235,245,.35)", "stroke-width": 1 }, s);
    t(22, 96, "1.5–2 米", "end");
    el("path", { d: "M48 132 L78 132 M48 128 L48 136 M78 128 L78 136", stroke: "rgba(235,235,245,.35)", "stroke-width": 1 }, s);
    t(63, 146, "底线后 1–3 米", "middle");
    t(201.5, 78, "球网", "middle");
    t(326, 108, "对面底线", "end");
    return s;
  }

  /** 迷你球场: 羽毛球沿弧线往返 (分析中) */
  function rallyLoop() {
    const s = el("svg", { viewBox: "0 0 220 96", class: "rally-loop", role: "img", "aria-label": "正在分析" });
    el("rect", { x: 14, y: 78, width: 192, height: 5, rx: 1.5, fill: "#3A3A40" }, s);
    el("rect", { x: 108.5, y: 52, width: 3, height: 26, rx: 1, fill: "#E9E9EE" }, s);
    el("path", { id: "yxArc", d: "M28 74 C 72 -6, 148 -6, 192 74", fill: "none", stroke: C.lime, opacity: 0.28, "stroke-width": 1.4, "stroke-dasharray": "2 5", "stroke-linecap": "round" }, s);
    const ball = el("g", {}, s);
    el("path", { d: "M-2 -1.6 L-11 -5.5 L-11 5.5 L-2 1.6 Z", fill: "#fff" }, ball);
    el("circle", { r: 3.6, fill: C.lime }, ball);
    const am = el("animateMotion", { dur: "1.5s", repeatCount: "indefinite", rotate: "auto", keyPoints: "0;1;0", keyTimes: "0;0.5;1", calcMode: "spline", keySplines: "0.35 0 0.65 1;0.35 0 0.65 1" }, ball);
    el("mpath", { href: "#yxArc" }, am);
    return s;
  }

  return { W, L, NET, SM, SS, DL, C, segments, orderCorners, homography, apply, metersToPixels,
           el, plot, landingMark, heat, hawkEye, guideSVG, rallyLoop };
})();
