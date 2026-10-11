/* ============================================================
   羽析 · 标签页: 比赛 / 数据 / 拍摄 / 设置 / 404
   ============================================================ */
const WEEK = ["日", "一", "二", "三", "四", "五", "六"];
const todayLabel = () => { const d = new Date(); return `${d.getMonth() + 1}月${d.getDate()}日 星期${WEEK[d.getDay()]}`; };

/** 缩略图里的小球场: 所有落点 (绿 = 界内, 红叉 = 出界) */
function miniCourt(landings) {
  const { svg, layer } = Court.plot({ landscape: true, pad: 0.35, lineW: 0.09, surround: false });
  for (const [x, y, inn] of landings || []) {
    if (inn) Court.el("circle", { cx: x, cy: y, r: 0.32, fill: "#30D158" }, layer);
    else Court.el("path", { d: `M${x - .3} ${y - .3}L${x + .3} ${y + .3}M${x + .3} ${y - .3}L${x - .3} ${y + .3}`, stroke: "#FF453A", "stroke-width": 0.2, "stroke-linecap": "round" }, layer);
  }
  return svg;
}

function thumbImg(src, alt = "") {
  const img = h("img", { src, alt, loading: "lazy", decoding: "async", "data-loading": "" });
  img.addEventListener("load", () => img.removeAttribute("data-loading"));
  img.addEventListener("error", () => { img.removeAttribute("data-loading"); img.style.visibility = "hidden"; });
  return img;
}

// ================================================================ 比赛
async function viewHome() {
  document.title = "羽析 · 羽毛球比赛 AI 分析";
  navbar({ title: "比赛", large: true });
  tabbar("/");
  const feed = h("div", { class: "feed grid2" }, h("div", { class: "skel", style: "height:300px" }), h("div", { class: "skel", style: "height:300px" }));
  const top = h("div", { class: "stack" });
  $app.append(h("main", { class: "screen", id: "main" }, h("div", { class: "wrap-wide" },
    largeTitle("比赛", todayLabel()), top, feed)));

  let list;
  try { list = await api("/api/videos"); }
  catch (e) { feed.replaceWith(offlineCard()); return; }
  feed.innerHTML = "";

  if (!list.length) {
    feed.classList.remove("grid2");
    feed.append(h("div", { class: "card" }, h("div", { class: "empty" },
      h("div", { class: "art" }, icon("shuttle")), h("h3", {}, "还没有比赛"),
      h("p", {}, "把手机架在底线后方，横屏拍一段比赛，上传后羽析会切出每个回合、认出每一拍、判出每个落点。"),
      h("div", { style: "display:flex;gap:10px;flex-wrap:wrap;justify-content:center" },
        h("button", { class: "btn", onclick: pickVideo }, icon("upload"), "选择比赛视频"),
        h("a", { class: "btn gray", href: "#/guide" }, "怎么拍")))));
    return;
  }

  // ---- 最近 7 天汇总 (没有就用全部)
  const done = list.filter((v) => v.state === "done" && v.summary);
  if (done.length) {
    const wk = done.filter((v) => Date.now() / 1000 - v.created < 7 * 86400);
    const set = wk.length ? wk : done;
    const sum = (f) => set.reduce((a, v) => a + (f(v) || 0), 0);
    const inn = sum((v) => v.summary.in_count), out = sum((v) => v.summary.out_count);
    const cell = (v, label, suf = "") => h("div", {}, h("b", { class: "num" }, Motion.countUp(h("span"), v), suf ? h("small", { style: "font-size:14px;color:var(--text-2)" }, suf) : null), h("span", {}, label));
    top.append(h("section", { class: "card", "aria-label": wk.length ? "最近 7 天" : "全部比赛" },
      h("div", { class: "card-head" }, h("h3", {}, wk.length ? "最近 7 天" : "全部比赛"), h("a", { class: "link", href: "#/stats", style: "font-size:14px" }, "查看走势")),
      h("div", { class: "week" }, cell(set.length, "场比赛"), cell(sum((v) => v.summary.num_rallies), "个回合"), cell(sum((v) => v.summary.total_shots), "拍击球"), cell(pct(inn, inn + out), "落点界内", "%"))));
    top.append(h("h2", { class: "section-h" }, "全部比赛", h("small", {}, `${list.length} 场`)));
  }

  const polls = [];
  list.forEach((v) => {
    const names = namesOf(v), S = v.summary;
    const ok = v.state === "done" && S;
    const busy = v.state === "queued" || v.state === "running";
    const href = ok ? `/v/${v.id}` : busy ? `/v/${v.id}/wait` : `/v/${v.id}/calib`;
    const thumb = h("div", { class: "thumb" }, thumbImg(frameUrl(v.id, Math.min(3, (v.duration || 2) / 2), 720)),
      h("div", { class: "tl" }, h("span", { class: "chip glass" }, v.request?.match_type === "doubles" ? "双打" : "单打")),
      h("div", { class: "br" }, h("span", { class: "chip glass num" }, fmtClock(v.duration || 0))),
      ok && S.landings_m?.length ? h("div", { class: "mini", "aria-hidden": "true" }, miniCourt(S.landings_m)) : null);
    const meta = h("div", { class: "meta" }, h("span", {}, icon("cal"), fmtDate(v.created)), h("span", {}, icon("clock"), fmtClock(v.duration || 0)),
      h("span", {}, icon("bolt"), v.track_mode === "fast" || v.request?.mode === "fast" ? "快速分析" : "精确分析"));
    let body;
    if (ok) {
      const pr = (side) => h("div", { class: `prow ${S.points[side] > S.points[other(side)] ? "win" : ""}` }, avatar(names[side], side),
        h("span", { class: "name" }, names[side]), h("span", { class: "pts num" }, icon("check", "check"), S.points[side]));
      body = [meta, h("div", { class: "scorecard" }, pr("near"), pr("far")),
        h("div", { class: "foot" }, h("div", { class: "stats" }, h("span", {}, icon("list"), `${S.num_rallies} 回合`), h("span", {}, icon("shuttle"), `${S.total_shots} 拍`)),
          h("span", {}, `最长 ${S.longest_rally_shots} 拍`))];
    } else if (busy) {
      const ring = h("div", { class: "ring", style: `--p:${v.status?.progress || 0}` }, h("span", {}, Math.round((v.status?.progress || 0) * 100) + "%"));
      const txt = h("span", {}, v.status?.stage || "排队中");
      polls.push([v.id, ring, txt]);
      body = [meta, h("div", { class: "processing" }, ring, h("div", {}, h("b", {}, `${names.near} 对 ${names.far}`), txt), icon("chev", "chev"))];
    } else if (v.state === "error") {
      body = [meta, h("div", { class: "state" }, h("span", { class: "chip out" }, "分析失败"), h("p", {}, "点开重新标定后再试"))];
    } else {
      body = [meta, h("div", { class: "state" }, h("span", { class: "chip review" }, "待标定"), h("p", {}, "标出球场四个角就能开始分析"))];
    }
    feed.append(h("a", { class: "card mcard pressable", href: "#" + href, "aria-label": `${names.near} 对 ${names.far}，${fmtDate(v.created)}` }, thumb, h("div", { class: "body" }, body)));
  });
  enter(feed);

  if (polls.length) {
    let alive = true; onCleanup(() => { alive = false; });
    (async () => {
      while (alive) {
        await new Promise((r) => setTimeout(r, 1500));
        for (const [id, ring, txt] of polls) {
          try {
            const m = await api(`/api/videos/${id}`);
            if (!alive) return;
            if (m.state === "done") { route(); return; }
            const p = m.status?.progress || 0;
            ring.style.setProperty("--p", p); ring.firstChild.textContent = Math.round(p * 100) + "%";
            txt.textContent = m.status?.stage || "排队中";
          } catch (e) {}
        }
      }
    })();
  }
}

// ================================================================ 数据 (多场走势)
const METRICS = [
  { key: "avg", name: "平均每回合拍数", unit: "拍", get: (s) => s.avg_shots_per_rally, digits: 1 },
  { key: "inrate", name: "落点界内率", unit: "%", get: (s) => (s.in_count + s.out_count ? (s.in_count / (s.in_count + s.out_count)) * 100 : null), digits: 0 },
  { key: "long", name: "最长回合", unit: "拍", get: (s) => s.longest_rally_shots, digits: 0 },
  { key: "dur", name: "平均回合时长", unit: "秒", get: (s) => s.avg_rally_duration, digits: 1 },
  { key: "rallies", name: "每场回合数", unit: "个", get: (s) => s.num_rallies, digits: 0 },
  { key: "shots", name: "每场击球", unit: "拍", get: (s) => s.total_shots, digits: 0 },
];
function sparkPath(vals, w, hgt, padY = 3) {
  const xs = vals.map((_, i) => (vals.length === 1 ? w / 2 : (i / (vals.length - 1)) * w));
  const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
  const ys = vals.map((v) => padY + (1 - (v - lo) / span) * (hgt - padY * 2));
  // Catmull-Rom 转贝塞尔, 线条圆润但必过每个数据点
  let d = `M${xs[0]},${ys[0]}`;
  for (let i = 0; i < xs.length - 1; i++) {
    const x0 = xs[i - 1] ?? xs[i], y0 = ys[i - 1] ?? ys[i], x3 = xs[i + 2] ?? xs[i + 1], y3 = ys[i + 2] ?? ys[i + 1];
    d += ` C${xs[i] + (xs[i + 1] - x0) / 6},${ys[i] + (ys[i + 1] - y0) / 6} ${xs[i + 1] - (x3 - xs[i]) / 6},${ys[i + 1] - (y3 - ys[i]) / 6} ${xs[i + 1]},${ys[i + 1]}`;
  }
  return { d, xs, ys };
}
async function viewStats() {
  document.title = "数据 · 羽析";
  navbar({ title: "数据", large: true });
  tabbar("/stats");
  const box = h("div", { class: "stack" }, h("div", { class: "skel", style: "height:320px" }));
  $app.append(h("main", { class: "screen", id: "main" }, h("div", { class: "wrap" }, largeTitle("数据", "每一场都在变化"), box)));
  let list;
  try { list = await api("/api/videos"); } catch (e) { box.replaceChildren(offlineCard()); return; }
  const done = list.filter((v) => v.state === "done" && v.summary).sort((a, b) => a.created - b.created);
  box.innerHTML = "";
  if (done.length < 2) {
    box.append(h("div", { class: "card" }, h("div", { class: "empty" }, h("div", { class: "art" }, icon("trend")),
      h("h3", {}, done.length ? "再分析一场就能看走势" : "还没有分析完的比赛"),
      h("p", {}, "至少两场比赛，才能看出回合长度、界内率这些数字是在变好还是变差。"),
      h("button", { class: "btn", onclick: pickVideo }, icon("upload"), "上传比赛视频"))));
    return;
  }
  let metric = METRICS[0], range = "all";
  const hero = h("section", { class: "card trend-hero" });
  const rows = h("div", { class: "list trend-list", role: "group", "aria-label": "指标" });
  box.append(h("div", { style: "margin-bottom:12px" }, segmented([["all", "全部"], ["5", "最近 5 场"]], range, (v) => { range = v; paint(); }, { label: "范围" })), hero, h("h2", { class: "section-h" }, "各项指标"), rows);

  function series(m) {
    const set = range === "5" ? done.slice(-5) : done;
    return set.map((v) => ({ v, y: m.get(v.summary) })).filter((p) => p.y != null && isFinite(p.y));
  }
  const fmt = (m, y) => (m.digits ? y.toFixed(m.digits) : Math.round(y));
  function paint() {
    const S = series(metric);
    const last = S[S.length - 1], prev = S[S.length - 2];
    const delta = prev && prev.y ? ((last.y - prev.y) / Math.abs(prev.y)) * 100 : 0;
    const W = Math.max(300, Math.round(hero.clientWidth - 32) || 600), H = 190, P = { l: 34, r: 12, t: 12, b: 26 };
    const vals = S.map((p) => p.y);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const { d, xs, ys } = sparkPath(vals, W - P.l - P.r, H - P.t - P.b, 8);
    const svg = Court.el("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": `${metric.name}走势` });
    const defs = Court.el("defs", {}, svg);
    const lg = Court.el("linearGradient", { id: "trendFill", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    Court.el("stop", { offset: 0, "stop-color": "#2BB255", "stop-opacity": 0.32 }, lg);
    Court.el("stop", { offset: 1, "stop-color": "#2BB255", "stop-opacity": 0 }, lg);
    const g = Court.el("g", { transform: `translate(${P.l},${P.t})` }, svg);
    const gw = W - P.l - P.r, gh = H - P.t - P.b;
    const grid = Court.el("g", { class: "grid" }, g), axis = Court.el("g", { class: "axis" }, g);
    [0, 0.5, 1].forEach((f) => {
      Court.el("line", { x1: 0, x2: gw, y1: 8 + f * (gh - 16), y2: 8 + f * (gh - 16) }, grid);
      const t = Court.el("text", { x: -8, y: 8 + f * (gh - 16) + 4, "text-anchor": "end" }, axis); t.textContent = fmt(metric, hi - f * (hi - lo));
    });
    S.forEach((p, i) => { if (S.length <= 8 || i % Math.ceil(S.length / 6) === 0 || i === S.length - 1) { const dt = new Date(p.v.created * 1000); const t = Court.el("text", { x: xs[i], y: gh + 18, "text-anchor": "middle" }, axis); t.textContent = `${dt.getMonth() + 1}/${dt.getDate()}`; } });
    Court.el("path", { class: "area", d: `${d} L${xs[xs.length - 1]},${gh} L${xs[0]},${gh} Z` }, g);
    const line = Court.el("path", { class: "line", d }, g);
    S.forEach((p, i) => Court.el("circle", { class: "pt" + (i === S.length - 1 ? " last" : ""), cx: xs[i], cy: ys[i], r: i === S.length - 1 ? 5 : 3.5 }, g));
    hero.replaceChildren(
      h("div", { class: "top" }, h("div", {}, h("h3", {}, metric.name), h("div", { class: "sub" },
        prev ? h("span", { class: `chip ${delta >= 0 ? "in" : "out"}` }, icon(delta >= 0 ? "arrowUp" : "arrowDown"), `${Math.abs(delta).toFixed(0)}%`) : null, h("span", {}, `比上一场 · 共 ${S.length} 场`))),
        h("div", { class: "big num" }, fmt(metric, last.y), h("small", { style: "font-size:15px;color:var(--text-2);margin-left:3px" }, metric.unit))),
      svg);
    if (!REDUCED) { const len = line.getTotalLength?.() || 1000; line.style.strokeDasharray = len; line.style.strokeDashoffset = len; Motion.tween(900, (u) => { line.style.strokeDashoffset = len * (1 - u); }); }
    rows.innerHTML = "";
    for (const m of METRICS) {
      const s = series(m); if (!s.length) continue;
      const v = s.map((p) => p.y), sp = sparkPath(v, 96, 26, 3);
      const up = v.length > 1 && v[v.length - 1] >= v[v.length - 2];
      const mini = Court.el("svg", { class: "spark", viewBox: "0 0 96 26", preserveAspectRatio: "none", "aria-hidden": "true" });
      Court.el("path", { d: sp.d, fill: "none", stroke: up ? "#30D158" : "#FF453A", "stroke-width": 1.8, "stroke-linecap": "round" }, mini);
      rows.append(h("button", { "aria-pressed": String(m === metric), onclick: () => { metric = m; paint(); } },
        h("span", { class: "k" }, m.name), mini, h("span", { class: `tv ${up ? "up" : "down"}` }, fmt(m, v[v.length - 1]), m.unit === "%" ? "%" : "")));
    }
  }
  paint();
}

// ================================================================ 拍摄指南
function viewGuide() {
  document.title = "怎么拍 · 羽析";
  navbar({ title: "拍摄", large: true });
  tabbar("/guide");
  const tip = (ic, b, p) => h("div", { class: "card tip" }, h("div", { class: "n" }, icon(ic)), h("b", {}, b), h("p", {}, p));
  const check = (t, s) => h("div", {}, h("span", { class: "ico-tile", style: "background:var(--near-soft);color:var(--near)" }, icon("check")), h("div", { class: "k" }, t, s ? h("div", { style: "font-size:13px;color:var(--text-3)" }, s) : null));
  $app.append(h("main", { class: "screen", id: "main" }, enter(h("div", { class: "wrap" },
    largeTitle("拍摄", "这样拍，分析最准"),
    h("figure", { class: "card guide-art" }, Court.guideSVG(), h("figcaption", { class: "group-f", style: "margin:10px 0 0" }, "侧面看：手机在底线后方，镜头略微朝下，整片球场都在画面里。")),
    h("div", { class: "tips", style: "margin-top:12px" },
      tip("tripod", "架在底线后方", "离底线 1 到 3 米，高 1.5 到 2 米。看台、椅子、三脚架都行。"),
      tip("landscape", "横屏，拍全场", "四个角都要在画面里。角被人挡住没关系，标定时可以换一帧。"),
      tip("sun", "机位不动，光线要亮", "一段 1 到 10 分钟最合适。灯越亮，羽毛球越好认。")),
    h("h2", { class: "group-h" }, "上传前检查"),
    h("div", { class: "list" },
      check("球场四个角都在画面里"),
      check("帧率 30 帧以上", "60 帧更好，快速杀球不容易丢"),
      check("拍摄时手机没有移动", "移动过的画面落点会算偏"),
      check("mp4 或 mov 格式", "iPhone 直接拍的视频就可以")),
    h("div", { style: "margin-top:20px" }, h("button", { class: "btn block", onclick: pickVideo }, icon("upload"), "选择比赛视频"))))));
}

// ================================================================ 设置
function viewSettings() {
  document.title = "设置 · 羽析";
  navbar({ title: "设置", large: true });
  tabbar("/settings");
  const status = h("span", { class: "v" }, "检查中…"), dev = h("span", { class: "v" }, "—");
  const dot = h("span", { class: "dot", style: "background:var(--text-4)" });
  const server = h("input", { class: "input", id: "server", value: localStorage.getItem("yuxi.server") || "", placeholder: "留空 = 本机", inputmode: "url", autocapitalize: "off", spellcheck: "false", "aria-describedby": "server-help" });
  const err = h("div", { class: "err", role: "alert" });
  const save = h("button", { class: "btn sm", onclick: () => {
    const v = server.value.trim();
    if (v && !/^https?:\/\/[^\s]+$/.test(v)) { server.setAttribute("aria-invalid", "true"); err.textContent = "地址要以 http:// 开头，例如 http://192.168.1.5:8000"; server.focus(); return; }
    server.removeAttribute("aria-invalid"); err.textContent = "";
    v ? localStorage.setItem("yuxi.server", v) : localStorage.removeItem("yuxi.server");
    save.classList.add("busy"); setTimeout(() => location.reload(), 300);
  } }, "保存");
  server.addEventListener("input", () => { server.removeAttribute("aria-invalid"); err.textContent = ""; });
  const row = (tile, k, v, color) => h("div", {}, h("span", { class: "ico-tile", style: color ? `background:${color}` : "" }, icon(tile)), h("span", { class: "k" }, k), v);
  $app.append(h("main", { class: "screen", id: "main" }, enter(h("div", { class: "wrap" },
    largeTitle("设置"),
    h("div", {}, h("h2", { class: "group-h" }, "分析服务"),
      h("div", { class: "list" }, row("wifi", "连接", h("span", { class: "v", style: "display:flex;align-items:center;gap:8px" }, dot, status), "#2BB255"), row("cpu", "计算设备", dev, "#5E5CE6"))),
    h("div", {}, h("h2", { class: "group-h" }, "服务器地址"),
      h("div", { class: "card" }, h("label", { class: "field", for: "server" }, h("span", {}, "用手机打开时填写电脑上显示的地址"),
        h("div", { style: "display:flex;gap:10px;align-items:center" }, server, save), err)),
      h("p", { class: "group-f", id: "server-help" }, "在电脑浏览器里使用时什么都不用改。启动羽析后终端里会显示类似 http://192.168.1.5:8000 的局域网地址。")),
    h("div", {}, h("h2", { class: "group-h" }, "关于"),
      h("div", { class: "list" },
        row("info", "版本", h("span", { class: "v" }, "羽析 0.4"), "#8E8E93"),
        row("shuttle", "羽毛球追踪", h("span", { class: "v" }, "TrackNetV3 · MIT"), "#C9A400"),
        row("run", "球员检测", h("span", { class: "v" }, "YOLOX-S · Apache-2.0"), "#FF9500"),
        row("chart", "评估数据", h("span", { class: "v" }, "TrackNetV2 (NYCU)"), "#32ADE6")),
      h("p", { class: "group-f" }, "回合切分、击球判定、击球方识别、落点与鹰眼复核为本项目原创。所有视频只保存在这台电脑上。"))))));
  api("/api/health").then((hl) => { status.textContent = "已连接"; dot.style.background = "var(--in)"; dev.textContent = DEVICE[hl.device] || hl.device; })
    .catch(() => { status.textContent = "未连接"; dot.style.background = "var(--out)"; });
}

// ================================================================ 404
function viewLost() {
  document.title = "找不到这一页 · 羽析";
  navbar({ left: backBtn(lastTab, "比赛") });
  $app.append(h("main", { class: "screen no-tab", id: "main" }, h("div", { class: "wrap lost" },
    h("div", { class: "big" }, "出界"), h("h1", { style: "font-size:22px" }, "这一页不存在"),
    h("p", { style: "color:var(--text-2)" }, "链接可能写错了，或者这场比赛已经被删除。"),
    h("a", { class: "btn", href: "#/" }, "回到比赛"))));
}
