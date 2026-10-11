/* ============================================================
   羽析 · 流程页: 标定 / 分析中
   ============================================================ */
async function viewCalib(id) {
  document.title = "标出球场 · 羽析";
  const nav = navbar({ title: "标出球场", left: backBtn("/", "取消") });
  const main = h("main", { class: "screen no-tab", id: "main" }, h("div", { class: "wrap-wide" }, h("div", { class: "skel", style: "aspect-ratio:16/9" })));
  $app.append(main);
  let meta;
  try { meta = await api(`/api/videos/${id}`); } catch (e) { main.firstChild.replaceChildren(offlineCard(e.message)); return; }
  const saved = JSON.parse(localStorage.getItem("yuxi.lastSetup") || "{}");
  const req = meta.request || {};
  const state = {
    t: Math.min(2, (meta.duration || 2) / 2),
    corners: req.corners ? req.corners.map((p) => [...p]) : [],
    match: req.match_type || saved.match || "singles",
    mode: req.mode || "accurate",
    names: { ...(req.names || saved.names || { near: "近端", far: "远端" }) },
  };
  const image = new Image();
  const canvas = h("canvas", { "aria-label": "视频画面。依次点击球场最外圈的四个角，点错了可以按住拖动。", tabindex: "0" });
  const loupeC = h("canvas", { width: 256, height: 256 });
  const loupe = h("div", { class: "loupe" }, loupeC);
  const stage = h("div", { class: "calib-stage" }, h("div", { class: "placeholder skel" }), loupe);
  const stepN = h("div", { class: "n num" }, "1");
  const stepT = h("p", {}, ""), stepS = h("small", {}, "");
  const bars = h("div", { class: "steps4", "aria-hidden": "true" }, h("i"), h("i"), h("i"), h("i"));
  const tLabel = h("span", {}, "");
  const startBtn = h("button", { class: "btn block", onclick: start }, "开始分析");
  const reuse = saved.corners && saved.w === meta.width && saved.h === meta.height && !req.corners
    ? h("button", { class: "btn gray sm", onclick: () => { state.corners = saved.corners.map((p) => [...p]); draw(); } }, "用上次的位置") : null;
  const MODE_NOTE = { accurate: "精确：每一帧看 8 次，更准，耗时约是快速的 5 到 8 倍。", fast: "快速：先看个大概，之后随时可以用精确模式重新分析。" };
  const modeNote = h("p", { class: "group-f", style: "margin:8px 2px 0" }, MODE_NOTE[state.mode]);
  const nameIn = (side, label) => h("label", {}, avatar(state.names[side], side), h("span", { class: "field" }, h("span", {}, label),
    h("input", { class: "input", value: state.names[side], maxlength: 8, oninput: (e) => { state.names[side] = e.target.value.trim() || (side === "near" ? "近端" : "远端"); e.target.closest("label").querySelector(".avatar").textContent = initial(state.names[side]); } })));

  nav.querySelector(".r").append(h("span", { class: "chip", title: meta.name }, fmtClock(meta.duration || 0)));
  main.firstChild.replaceChildren(h("div", { class: "calib-layout" },
    h("div", { class: "stack" }, stage,
      h("div", { class: "card", style: "display:grid;gap:12px" },
        h("div", { class: "scrub-row" }, icon("eye"),
          h("input", { type: "range", min: 0, max: Math.max(0.1, (meta.duration || 1) - 0.1), step: 0.1, value: state.t, "aria-label": "换一帧画面",
            oninput: (e) => { state.t = +e.target.value; tLabel.textContent = fmtClock(state.t); }, onchange: loadFrame }), tLabel),
        h("div", { style: "display:flex;gap:8px;flex-wrap:wrap;align-items:center" },
          h("button", { class: "btn gray sm", onclick: () => { state.corners = []; draw(); } }, icon("refresh"), "重新点"), reuse,
          h("span", { style: "font-size:13px;color:var(--text-3)" }, "角被人挡住时，拖动上面的滑块换一帧。")))),
    h("div", { class: "side stack" },
      h("section", { class: "card", style: "display:grid;gap:14px" }, h("div", { class: "instr" }, stepN, h("div", {}, stepT, stepS)), bars),
      h("section", { class: "card", style: "display:grid;gap:18px" },
        h("div", { class: "field" }, h("span", {}, "比赛类型"), segmented([["singles", "单打"], ["doubles", "双打"]], state.match, (v) => { state.match = v; }, { label: "比赛类型" })),
        h("div", { class: "field" }, h("span", {}, "选手"), h("div", { class: "names2" }, nameIn("near", "近端 · 离镜头近"), nameIn("far", "远端"))),
        h("div", { class: "field" }, h("span", {}, "分析方式"), segmented([["accurate", "精确"], ["fast", "快速"]], state.mode, (v) => { state.mode = v; modeNote.textContent = MODE_NOTE[v]; }, { label: "分析方式" }), modeNote)),
      h("div", { class: "bottom-cta" }, startBtn))));
  tLabel.textContent = fmtClock(state.t);

  function loadFrame() {
    image.onload = () => { canvas.width = image.naturalWidth; canvas.height = image.naturalHeight; if (!canvas.isConnected) stage.firstChild.replaceWith(canvas); draw(); };
    image.onerror = () => toast("取不到视频画面，视频格式可能不支持，建议用 mp4。", { bad: true, ms: 4200 });
    image.src = `${API}/api/videos/${id}/frame?t=${state.t}`;
  }
  const scale = () => meta.width / (canvas.width || meta.width);
  const TXT = ["点球场最外圈的一个角", "再点下一个角", "第三个角", "最后一个角"];
  function draw() {
    const n = state.corners.length;
    stepN.textContent = n < 4 ? String(n + 1) : "✓";
    stepT.textContent = n < 4 ? TXT[n] : "看看黄绿色的线和场地白线是否重合";
    stepS.textContent = n < 4 ? "双打边线和底线的交点，顺序随意" : "不准的话按住角点拖动微调，放大镜会帮你对准。";
    [...bars.children].forEach((b, i) => b.classList.toggle("on", i < n));
    startBtn.disabled = n < 4;
    if (!image.naturalWidth) return;
    const c = canvas.getContext("2d");
    c.drawImage(image, 0, 0);
    c.fillStyle = "rgba(10,10,12,.25)"; c.fillRect(0, 0, canvas.width, canvas.height);
    const k = scale(), pts = state.corners.map(([x, y]) => [x / k, y / k]);
    const lw = Math.max(1.6, canvas.width / 640);
    c.lineCap = "round";
    if (pts.length === 4) {
      const Hm = Court.metersToPixels(pts);
      c.strokeStyle = "rgba(201,232,60,.95)"; c.lineWidth = lw;
      for (const [a, b] of Court.segments()) { const p = Court.apply(Hm, a), q = Court.apply(Hm, b); c.beginPath(); c.moveTo(p[0], p[1]); c.lineTo(q[0], q[1]); c.stroke(); }
      c.setLineDash([lw * 4, lw * 3]); c.strokeStyle = "#fff";
      const n1 = Court.apply(Hm, [0, Court.NET]), n2 = Court.apply(Hm, [Court.W, Court.NET]); c.beginPath(); c.moveTo(...n1); c.lineTo(...n2); c.stroke(); c.setLineDash([]);
    } else if (pts.length > 1) {
      c.strokeStyle = "rgba(201,232,60,.85)"; c.lineWidth = lw; c.setLineDash([lw * 4, lw * 3]);
      c.beginPath(); pts.forEach((p, i) => (i ? c.lineTo(...p) : c.moveTo(...p))); c.stroke(); c.setLineDash([]);
    }
    pts.forEach(([x, y], i) => {
      const r = lw * 10;
      c.beginPath(); c.arc(x, y, r, 0, 7); c.fillStyle = "rgba(201,232,60,.18)"; c.fill(); c.lineWidth = lw * 1.4; c.strokeStyle = "#C9E83C"; c.stroke();
      c.beginPath(); c.arc(x, y, lw * 1.8, 0, 7); c.fillStyle = "#C9E83C"; c.fill();
      c.font = `700 ${Math.round(lw * 9)}px -apple-system, "PingFang SC", sans-serif`; c.textAlign = "center";
      c.fillStyle = "#C9E83C"; c.fillText(String(i + 1), x, y - r - lw * 4);
    });
  }
  let drag = -1;
  const toImg = (e) => { const r = canvas.getBoundingClientRect(); return [(e.clientX - r.left) / r.width * canvas.width, (e.clientY - r.top) / r.height * canvas.height]; };
  function showLoupe(e, p) {
    const sr = stage.getBoundingClientRect(), lx = e.clientX - sr.left, ly = e.clientY - sr.top;
    loupe.style.display = "block";
    loupe.style.left = clamp(lx - 64, 4, sr.width - 132) + "px";
    loupe.style.top = (ly - 160 < 0 ? ly + 36 : ly - 160) + "px";
    const z = 3.5, lc = loupeC.getContext("2d"), s = (256 / z) * (canvas.width / canvas.getBoundingClientRect().width) / 2;
    lc.clearRect(0, 0, 256, 256); lc.drawImage(canvas, p[0] - s, p[1] - s, s * 2, s * 2, 0, 0, 256, 256);
    lc.strokeStyle = "#C9E83C"; lc.lineWidth = 2; lc.beginPath(); lc.moveTo(128, 100); lc.lineTo(128, 156); lc.moveTo(100, 128); lc.lineTo(156, 128); lc.stroke();
  }
  canvas.addEventListener("pointerdown", (e) => {
    const p = toImg(e), k = scale(), hit = (canvas.width / canvas.getBoundingClientRect().width) * 28;
    drag = state.corners.findIndex(([x, y]) => Math.hypot(x / k - p[0], y / k - p[1]) < hit);
    if (drag < 0 && state.corners.length < 4) { state.corners.push([p[0] * k, p[1] * k]); drag = state.corners.length - 1; }
    if (drag >= 0) { canvas.setPointerCapture(e.pointerId); draw(); showLoupe(e, p); }
  });
  canvas.addEventListener("pointermove", (e) => {
    if (drag < 0) return;
    const p = toImg(e), k = scale();
    state.corners[drag] = [clamp(p[0], 0, canvas.width) * k, clamp(p[1], 0, canvas.height) * k];
    draw(); showLoupe(e, p);
  });
  const up = () => { drag = -1; loupe.style.display = "none"; };
  canvas.addEventListener("pointerup", up); canvas.addEventListener("pointercancel", up);

  async function start() {
    startBtn.classList.add("busy"); startBtn.textContent = "正在提交";
    const body = { corners: state.corners, match_type: state.match, mode: state.mode, names: state.names };
    localStorage.setItem("yuxi.lastSetup", JSON.stringify({ corners: state.corners, w: meta.width, h: meta.height, match: state.match, names: state.names }));
    try {
      await api(`/api/videos/${id}/analyze`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      go(`/v/${id}/wait`);
    } catch (e) { toast(e.message, { bad: true }); startBtn.classList.remove("busy"); startBtn.textContent = "开始分析"; }
  }
  draw();
  loadFrame();
}

// ================================================================ 分析中
const STAGES = [["排队中", "等前面的视频分析完"], ["加载模型", "TrackNetV3 · YOLOX"], ["生成背景模型", "把静止的场地从画面里分出来"], ["追踪羽毛球", "逐帧找到羽毛球的位置"],
  ["轨迹补全", "补上被人挡住的那几帧"], ["识别球员", "判断每一拍是谁打的"], ["生成报告", "切回合、判落点、算跑动"]];
async function viewWait(id) {
  document.title = "正在分析 · 羽析";
  const nav = navbar({ title: "正在分析", left: backBtn("/", "比赛") });
  const C = 2 * Math.PI * 88;
  const arc = Court.el("circle", { cx: 98, cy: 98, r: 88, fill: "none", stroke: "#C9E83C", "stroke-width": 10, "stroke-linecap": "round", "stroke-dasharray": `0 ${C}` });
  const ringSvg = Court.el("svg", { viewBox: "0 0 196 196", "aria-hidden": "true" });
  Court.el("circle", { cx: 98, cy: 98, r: 88, fill: "none", stroke: "#34343A", "stroke-width": 10 }, ringSvg); ringSvg.append(arc);
  const num = h("b", { class: "num" }, "0", h("small", {}, "%"));
  const eta = h("span", {}, "正在估算剩余时间");
  const stages = h("ol", { class: "list stages", "aria-label": "分析步骤" });
  const rows = STAGES.map(([s, d]) => { const li = h("li", {}, h("span", { class: "st" }), h("div", { class: "k" }, s, h("div", { style: "font-size:12.5px;color:var(--text-3)" }, d)), h("span", { class: "d" }, "")); stages.append(li); return li; });
  const errBox = h("div");
  const title = h("h1", { style: "font-size:22px;font-weight:700;margin-top:6px" }, "正在分析");
  $app.append(h("main", { class: "screen no-tab", id: "main" }, enter(h("div", { class: "wrap" },
    h("section", { class: "card wait-hero" }, h("div", { class: "big-ring" }, ringSvg, h("div", { class: "val" }, num, eta)), Court.rallyLoop(), title,
      h("p", { style: "color:var(--text-2);font-size:14px;max-width:32ch" }, "分析在电脑上进行，可以离开这一页，完成后会出现在「比赛」里。")),
    errBox, h("h2", { class: "group-h" }, "步骤"), stages))));
  const shown = Motion.spring(0, (p) => { arc.setAttribute("stroke-dasharray", `${Math.max(0, p) * C} ${C}`); }, "default");
  const seen = {}; let alive = true, t0 = Date.now(), p0 = null;
  onCleanup(() => { alive = false; });
  api(`/api/videos/${id}`).then((m) => { const n = m.request?.names; if (n) title.textContent = `${n.near} 对 ${n.far}`; }).catch(() => {});
  while (alive) {
    try {
      const m = await api(`/api/videos/${id}`);
      if (!alive) return;
      const s = m.status || {}, p = s.progress || 0;
      shown.set(p);
      num.firstChild.textContent = Math.round(p * 100);
      const name = s.stage === "追踪完成" ? "轨迹补全" : s.stage;
      let si = STAGES.findIndex(([n]) => n === name); if (si < 0 && s.state === "queued") si = 0;
      if (si >= 0 && !(si in seen)) seen[si] = Date.now();
      rows.forEach((li, i) => {
        li.className = i < si ? "done" : i === si ? "now" : "";
        const st = li.querySelector(".st"); st.replaceChildren(i < si ? icon("check") : "");
        const d = li.querySelector(".d");
        if (i < si && seen[i] != null) { const nx = Object.keys(seen).map(Number).filter((k) => k > i).sort((a, b) => a - b)[0]; d.textContent = nx != null ? `${((seen[nx] - seen[i]) / 1000).toFixed(1)} 秒` : ""; }
      });
      if (p > 0.03 && p0 == null) { p0 = p; t0 = Date.now(); }
      if (p0 != null && p - p0 > 0.02) { const el = (Date.now() - t0) / 1000; eta.textContent = `还需约 ${fmtDur(Math.max(1, (el / (p - p0)) * (1 - p)))}`; }
      if (s.state === "done" || m.state === "done") { shown.set(1); num.firstChild.textContent = "100"; setTimeout(() => alive && go(`/v/${id}`), REDUCED ? 0 : 500); return; }
      if (s.state === "error" || m.state === "error") {
        errBox.replaceChildren(h("div", { class: "card error-card", style: "margin-top:12px" }, h("div", { class: "empty" }, h("div", { class: "art" }, icon("info")),
          h("h3", {}, "分析没有完成"), h("p", {}, m.error || s.stage || "未知错误"), h("a", { class: "btn sm", href: `#/v/${id}/calib` }, "重新标定"))));
        eta.textContent = "已停止";
        return;
      }
    } catch (e) { eta.textContent = "连接中断，正在重试…"; }
    await new Promise((r) => setTimeout(r, 1000));
  }
}
