/* ============================================================
   羽析 · 前端主程序 v3 (原生 JS, 无构建步骤)
   #/            首页: 封面 (球场舞台) · 往期 · 拍摄 · 设置
   #/v/:id       报告: 封面 · 概览 · 飞行 (滚动驱动) · 落点 · 回合 · 双方 · 信息
   #/v/:id/calib 标定      #/v/:id/wait 分析中
   ============================================================ */
const $app = document.getElementById("app");
const API = (localStorage.getItem("yuxi.server") || "").replace(/\/$/, "");
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------------------------------------------------------------- 小工具
function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const k in attrs) {
    const v = attrs[k];
    if (k === "class") e.className = v;
    else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
    else if (k === "html") e.innerHTML = v;
    else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
async function api(path, opt = {}) {
  const r = await fetch(API + path, opt);
  if (!r.ok) {
    let msg = `请求失败 (${r.status})`;
    try { msg = (await r.json()).detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return r.headers.get("content-type")?.includes("json") ? r.json() : r;
}
function toast(msg, ms = 2800) {
  document.querySelectorAll(".toast").forEach((t) => t.remove());
  const t = h("div", { class: "toast", role: "status" }, msg);
  document.body.append(t);
  setTimeout(() => t.remove(), ms);
}
const pad = (n) => String(n).padStart(2, "0");
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const smooth = (t) => { t = clamp(t); return t * t * (3 - 2 * t); };
const fmtDate = (ts) => { const d = new Date(ts * 1000); return `${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const fmtDur = (s) => s >= 60 ? `${Math.floor(s / 60)} 分 ${Math.round(s % 60)} 秒` : `${Math.round(s)} 秒`;
const REASON = { "界内得分": "落在界内", "出界": "出界", "下网": "下网", "未检测到落地": "未检测到落地" };
const DEVICE = { mps: "Apple 芯片 GPU", cuda: "NVIDIA GPU", cpu: "CPU" };
const frameUrl = (id, t, w = 640) => `${API}/api/videos/${id}/frame?t=${Math.max(0, +t || 0).toFixed(2)}&w=${w}`;
const titleOf = (v) => v.request?.names ? `${v.request.names.near} 对 ${v.request.names.far}` : (v.name || "未命名视频").replace(/\.\w+$/, "");
const longest = (R) => R.rallies.reduce((a, r) => (!a || r.num_shots > a.num_shots ? r : a), null);

const ICON = {
  mark: '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true"><circle cx="16" cy="16" r="14.4"/><path d="M5.5 22.5C10 7 21 5.5 25.5 13" stroke-dasharray="1.4 2.6"/><circle cx="25.6" cy="13.2" r="2.6" fill="#F2C230" stroke="none"/></svg>',
  plus: '<svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M7 1v12M1 7h12"/></svg>',
  play: '<svg viewBox="0 0 14 14" fill="currentColor" aria-hidden="true"><path d="M3 1.5v11l9-5.5z"/></svg>',
  pause: '<svg viewBox="0 0 14 14" fill="currentColor" aria-hidden="true"><path d="M3 1.5h3v11H3zM8 1.5h3v11H8z"/></svg>',
};

// ---------------------------------------------------------------- 路由生命周期
let cleanups = [];
const onCleanup = (fn) => cleanups.push(fn);
const loops = new Set();
function addLoop(fn) { loops.add(fn); onCleanup(() => loops.delete(fn)); }
let lastT = performance.now();
(function tick(now) {
  const dt = Math.min(0.05, (now - lastT) / 1000); lastT = now;
  for (const fn of loops) fn(dt, now);
  requestAnimationFrame(tick);
})(lastT);

function route() {
  cleanups.forEach((f) => { try { f(); } catch (e) {} }); cleanups = [];
  document.querySelectorAll("dialog, .uploading, .peek").forEach((e) => e.remove());
  $app.innerHTML = "";
  window.scrollTo(0, 0);
  const p = location.hash.replace(/^#/, "") || "/";
  let m;
  if ((m = p.match(/^\/v\/([\w-]+)\/calib$/))) return viewCalib(m[1]);
  if ((m = p.match(/^\/v\/([\w-]+)\/wait$/))) return viewWait(m[1]);
  if ((m = p.match(/^\/v\/([\w-]+)$/))) return viewReport(m[1]);
  if (p === "/" || p === "/matches" || p === "/settings" || p === "/guide") return viewHome(p.slice(1));
  return viewLost();
}
window.addEventListener("hashchange", route);
const go = (p) => { location.hash = p; };

// ---------------------------------------------------------------- 固定外框: 顶栏 + 底部章节仪表
function chrome({ left, right, hudL, hudR, chapters = [] }) {
  const top = h("header", { class: "topbar chrome", "data-on": "ink" },
    h("div", { class: "left" }, left),
    h("a", { class: "mark", href: "#/", "aria-label": "羽析 首页", html: ICON.mark + "<span>羽析</span>" }),
    h("div", { class: "right" }, right));
  const bar = h("i");
  const nav = h("nav", { "aria-label": "章节" }, h("span", { class: "bar", "aria-hidden": "true" }, bar),
    chapters.map(([id, name], i) => h("a", { href: "#" + id, "data-i": i, "aria-label": name,
      onclick: (e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: REDUCED ? "auto" : "smooth" }); } }, pad(i))));
  const l = h("div", { class: "l", "aria-live": "polite" }, hudL || "");
  const r = h("div", { class: "r" }, hudR || "");
  const hud = h("footer", { class: "hud chrome", "data-on": "ink" }, l, nav, r);
  $app.append(top, hud);

  // 顶栏与仪表各自读取自己下方那一屏的地面颜色; 当前章节 = 仪表所在的那一屏
  const secs = () => chapters.map(([id]) => document.getElementById(id)).filter(Boolean);
  let cur = -1;
  addLoop(() => {
    const yb = innerHeight - 26, yt = 30;
    let gb = null, gt = null, ci = -1;
    document.querySelectorAll("[data-ground]").forEach((s) => {
      const rc = s.getBoundingClientRect();
      if (rc.top <= yb && rc.bottom > yb) gb = s.dataset.ground;
      if (rc.top <= yt && rc.bottom > yt) gt = s.dataset.ground;
    });
    secs().forEach((s, i) => { const rc = s.getBoundingClientRect(); if (rc.top <= yb && rc.bottom > yb) ci = i; });
    if (gb && hud.dataset.on !== gb) hud.dataset.on = gb;
    if (gt && top.dataset.on !== gt) top.dataset.on = gt;
    if (ci !== cur && ci >= 0) {
      cur = ci;
      nav.querySelectorAll("a").forEach((a) => a.setAttribute("aria-current", String(+a.dataset.i === ci)));
      if (!hudL) l.innerHTML = `<b>${pad(ci)}</b> · ${chapters[ci][1]}`;
    }
    const max = document.documentElement.scrollHeight - innerHeight;
    bar.style.width = (max > 0 ? clamp(scrollY / max) * 100 : 0) + "%";
  });
  return { top, hud, l, r };
}
const newMatchBtn = () => h("button", { class: "btn sm", onclick: pickVideo, html: ICON.plus + "<span>新比赛</span>" });

// ---------------------------------------------------------------- 滚动驱动的三种效果
/** 标题逐字点亮: 未点亮的字压暗而不是隐藏, 滚回去会重新变暗 */
function wipe(el) {
  const units = [];
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
  el.setAttribute("aria-label", el.textContent.replace(/\s+/g, " ").trim());
  for (const n of nodes) {
    const frag = document.createDocumentFragment();
    for (const tok of n.textContent.match(/[A-Za-z0-9.%:]+|\s+|./gu) || []) {
      if (/^\s+$/.test(tok)) { frag.append(tok); continue; }
      const s = h("span", { class: "ch", "aria-hidden": "true" }, tok); units.push(s); frag.append(s);
    }
    n.replaceWith(frag);
  }
  el.classList.add("wipe");
  if (REDUCED) return el;
  const last = new Array(units.length).fill(-1);
  addLoop(() => {
    const rc = el.getBoundingClientRect();
    if (rc.bottom < -50 || rc.top > innerHeight + 50) return;
    const q = clamp((innerHeight * 0.92 - rc.top) / (innerHeight * 0.55));
    units.forEach((u, i) => {
      const key = (i / Math.max(1, units.length)) * 0.7;
      const o = Math.round((0.16 + 0.84 * smooth((q - key) / 0.3)) * 100) / 100;
      if (o !== last[i]) { last[i] = o; u.style.setProperty("--o", o); }
    });
  });
  return el;
}
/** 数字计数: 第一次进入视野时从 0 数到真实值, 最后一定停在真实值上 */
function countUp(el, value, digits = 0) {
  const fmt = (v) => v.toFixed(digits);
  if (REDUCED) { el.textContent = fmt(value); return el; }
  el.textContent = fmt(0);
  let t0 = null;
  const fn = (dt, now) => {
    if (t0 == null) { if (el.getBoundingClientRect().top < innerHeight * 0.88) t0 = now; else return; }
    const u = clamp((now - t0) / 1300);
    el.textContent = fmt(value * (1 - Math.pow(1 - u, 3)));
    if (u >= 1) { el.textContent = fmt(value); loops.delete(fn); }
  };
  addLoop(fn);
  return el;
}
/** 元素穿过视口的进度 0..1, 写到 CSS 变量上 */
function scrub(el, prop, from = 0.95, span = 0.5) {
  if (REDUCED) { el.style.setProperty(prop, 1); return; }
  let lastV = -1;
  addLoop(() => {
    const rc = el.getBoundingClientRect();
    const v = Math.round(smooth((innerHeight * from - rc.top) / (innerHeight * span)) * 1000) / 1000;
    if (v !== lastV) { lastV = v; el.style.setProperty(prop, v); }
  });
}

// ---------------------------------------------------------------- 上传
const filePicker = h("input", { type: "file", accept: "video/*", hidden: true, onchange: (e) => { const f = e.target.files[0]; e.target.value = ""; upload(f); } });
document.body.append(filePicker);
function pickVideo() { filePicker.click(); }
async function upload(f) {
  if (!f) return;
  const num = h("div", { class: "numeral", "aria-live": "polite" }, "0");
  const bar = h("i");
  const ov = h("div", { class: "uploading g-ink", role: "status" },
    h("div", {}, h("div", { class: "label" }, `正在上传 · ${f.name}`), num, h("div", { class: "bar" }, bar)));
  document.body.append(ov);
  try {
    const meta = await new Promise((res, rej) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", API + "/api/videos");
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) { const p = e.loaded / e.total; num.innerHTML = `${Math.round(p * 100)}<small style="font-size:.3em;color:var(--fg-3)">%</small>`; bar.style.width = p * 100 + "%"; } };
      xhr.onload = () => xhr.status < 300 ? res(JSON.parse(xhr.responseText)) : rej(new Error(JSON.parse(xhr.responseText || "{}").detail || "上传失败"));
      xhr.onerror = () => rej(new Error("连不上分析服务。请确认电脑上的羽析正在运行。"));
      const fd = new FormData(); fd.append("file", f); xhr.send(fd);
    });
    ov.remove();
    go(`/v/${meta.id}/calib`);
  } catch (e) { ov.remove(); toast(e.message, 4200); }
}

function offline(msg) {
  return h("div", { class: "error-state" }, h("h3", {}, "连不上分析服务"),
    h("p", {}, msg || "请在电脑上双击「启动羽析.command」，然后刷新这一页。用手机打开时，手机和电脑要连同一个 Wi-Fi，并在设置里填电脑的地址。"),
    h("div", {}, h("button", { class: "btn sm", onclick: () => location.reload() }, "重新连接")));
}

// ================================================================ 首页
async function viewHome(focus) {
  document.title = "羽析 · 羽毛球比赛视频 AI 分析";
  const ro = h("span", { class: "label" }, "");
  chrome({ left: h("a", { class: "link", href: "#/matches", onclick: (e) => { e.preventDefault(); document.getElementById("matches").scrollIntoView({ behavior: "smooth" }); } }, "往期"),
    right: newMatchBtn(), hudR: "拍一段球，看清每一拍",
    chapters: [["cover", "封面"], ["matches", "往期比赛"], ["guide", "拍摄指南"], ["settings", "设置"]] });

  // ---- 封面: 球场舞台
  const canvas = h("canvas", { class: "stage", "aria-hidden": "true" });
  const cover = h("section", { class: "cover g-ink", id: "cover", "data-ground": "ink" }, canvas,
    h("div", { class: "over grid" },
      h("div", { class: "eyebrow" }, h("span", { class: "label" }, "羽毛球比赛视频 · 逐拍 AI 分析"), ro),
      h("div"),
      h("div", { class: "foot" },
        h("h1", { class: "wordmark" }, "羽析"),
        h("div", { class: "pitch" },
          h("p", { class: "statement" }, "拍一段球，", h("br"), "看清每一拍。"),
          h("p", { class: "body" }, "上传手机拍的比赛视频。羽析逐帧追踪羽毛球，切出每个回合，认出每一拍是谁打的，再像鹰眼一样判定落点。"),
          h("div", { style: "display:flex;gap:12px;flex-wrap:wrap" },
            h("button", { class: "btn solid", onclick: pickVideo }, "选择比赛视频"),
            h("a", { class: "btn", href: "#/guide", onclick: (e) => { e.preventDefault(); document.getElementById("guide").scrollIntoView({ behavior: "smooth" }); } }, "怎么拍"))))),
    h("div", { class: "cue", "aria-hidden": "true" }, h("span", { class: "label" }, "向下"), h("i")));
  const stage = Stage.create(canvas, { mode: "cover", offsetX: 0.14, offsetY: -0.06 });
  onCleanup(() => stage.destroy());
  stage.onFrame((f) => {
    const txt = f.demo ? "示意回合" : `第 ${f.rally.index} 回合 · ${pad(f.nShots)} / ${pad(f.total)} 拍`;
    if (ro.textContent !== txt) ro.textContent = txt;
  });

  // ---- 往期比赛
  const table = h("div", { class: "table", role: "list" });
  const matches = h("section", { class: "sec g-bone", id: "matches", "data-ground": "bone" },
    h("div", { class: "grid" },
      h("div", { class: "index-head" },
        wipe(h("h2", { class: "display" }, "往期比赛")),
        h("div", { class: "aside" }, h("div", { class: "chapter-no" }, "01"),
          h("p", { class: "body" }, "每一场分析都保存在这台电脑上。点开一场，从最长的那一回合看起。"))),
      table));

  // ---- 拍摄指南
  const step = (n, b, s) => h("li", {}, h("span", { class: "n" }, n), h("div", {}, h("b", {}, b), h("p", {}, s)));
  const guide = h("section", { class: "sec g-ink guide", id: "guide", "data-ground": "ink" },
    h("div", { class: "grid" },
      h("div", { style: "grid-column:1/-1;display:grid;gap:18px;margin-bottom:clamp(48px,9vh,96px)" },
        h("div", { class: "chapter-no" }, "02"), wipe(h("h2", { class: "display" }, "这样拍，分析最准。"))),
      h("figure", { class: "art" }, Court.guideSVG()),
      h("ol", { class: "steps" },
        step("01", "架在底线后方", "离底线 1 到 3 米，高 1.5 到 2 米。看台、椅子或三脚架都可以。"),
        step("02", "横屏拍全场", "画面里要能看到球场的四个角。角被人挡住时，标定可以换一帧。"),
        step("03", "机位固定不动", "一段 1 到 10 分钟最合适。光线越亮，球越好认。"))));

  // ---- 设置
  const status = h("dd", {}, "检查中…"), devDd = h("dd", {}, "—");
  const server = h("input", { value: localStorage.getItem("yuxi.server") || "", placeholder: "留空 = 本机", inputmode: "url", autocapitalize: "off", spellcheck: "false", id: "server" });
  const settings = h("section", { class: "sec g-bone settings", id: "settings", "data-ground": "bone" },
    h("div", { class: "grid" },
      h("div", { class: "col-a" }, h("div", { class: "chapter-no" }, "03"), wipe(h("h2", { class: "display" }, "设置")),
        h("p", { class: "body" }, "在电脑浏览器里用时什么都不用改。用手机打开时，把电脑启动羽析后显示的地址填在这里，例如 http://192.168.1.5:8000。")),
      h("div", { class: "col-b" },
        h("div", { class: "row" },
          h("label", { class: "field", for: "server" }, h("span", { class: "label" }, "分析服务地址"), server),
          h("button", { class: "btn sm", onclick: () => {
            const v = server.value.trim();
            if (v && !/^https?:\/\//.test(v)) { toast("地址要以 http:// 开头"); server.focus(); return; }
            v ? localStorage.setItem("yuxi.server", v) : localStorage.removeItem("yuxi.server");
            location.reload();
          } }, "保存并重连")),
        h("dl", { class: "spec" }, h("dt", {}, "连接"), status, h("dt", {}, "计算设备"), devDd,
          h("dt", {}, "羽毛球追踪"), h("dd", {}, "TrackNetV3 · MIT"), h("dt", {}, "球员检测"), h("dd", {}, "YOLOX-S · Apache-2.0"),
          h("dt", {}, "评估数据"), h("dd", {}, "TrackNetV2 数据集 (NYCU)"))),
      h("div", { class: "foot-note" }, h("span", { class: "label" }, "羽析 · 0.3"),
        h("span", { class: "label" }, "回合切分、击球判定、落点与鹰眼复核为本项目原创"))));

  $app.append(h("main", { id: "main" }, cover, matches, guide, settings));
  if (focus) requestAnimationFrame(() => document.getElementById(focus)?.scrollIntoView());

  api("/api/health").then((hl) => { status.textContent = "已连接"; status.className = "status-ok"; devDd.textContent = DEVICE[hl.device] || hl.device; })
    .catch(() => { status.textContent = "未连接"; status.className = "status-bad"; });

  // ---- 目录内容
  let list;
  try { list = await api("/api/videos"); } catch (e) { table.append(offline()); return; }
  const done = list.filter((v) => v.state === "done" && v.summary);
  if (done[0]) api(`/api/videos/${done[0].id}/result`).then((R) => { const r = longest(R); if (r) stage.setRally(Stage.rallyFrom(R, r)); }).catch(() => {});
  if (!list.length) {
    table.append(h("div", { class: "empty-state" }, h("p", { class: "statement" }, "还没有比赛。"),
      h("p", { class: "body" }, "选一段手机拍的比赛视频，分析完会出现在这里。"),
      h("button", { class: "btn solid", onclick: pickVideo }, "选择比赛视频")));
    return;
  }
  table.append(h("div", { class: "th", "aria-hidden": "true" }, ...["#", "对阵", "比分", "回合", "日期", ""].map((t) => h("span", { class: "label" }, t))));
  const peek = h("div", { class: "peek", "aria-hidden": "true" }, h("img", { alt: "" }));
  document.body.append(peek);
  const pp = { x: 0, y: 0, tx: 0, ty: 0 };
  addLoop((dt) => { const k = 1 - Math.exp(-12 * dt); pp.x += (pp.tx - pp.x) * k; pp.y += (pp.ty - pp.y) * k; peek.style.transform = `translate(${pp.x + 24}px, ${pp.y - 90}px)`; });
  const pollIds = [];
  list.forEach((v, i) => {
    const ok = v.state === "done" && v.summary;
    const target = ok ? `/v/${v.id}` : (v.state === "queued" || v.state === "running") ? `/v/${v.id}/wait` : `/v/${v.id}/calib`;
    const stateTag = ok ? h("span", { class: "tag in" }, "查看报告")
      : v.state === "error" ? h("span", { class: "tag out" }, "失败 · 重新标定")
      : v.state === "uploaded" ? h("span", { class: "tag review" }, "待标定")
      : h("span", { class: "tag review", "data-poll": v.id }, "分析中");
    if (v.state === "queued" || v.state === "running") pollIds.push([v.id, stateTag]);
    const row = h("a", { class: "tr", href: "#" + target, role: "listitem" },
      h("span", { class: "idx" }, pad(list.length - i)),
      h("span", { class: "who" }, titleOf(v)),
      h("span", { class: "score" }, ok ? `${v.summary.points.near} : ${v.summary.points.far}` : "—"),
      h("span", { class: "meta hide-sm" }, ok ? `${v.summary.num_rallies} 回合 · ${v.summary.total_shots} 拍` : fmtDur(v.duration || 0)),
      h("span", { class: "meta hide-sm" }, fmtDate(v.created)),
      h("span", { class: "state" }, stateTag));
    row.addEventListener("pointerenter", (e) => { peek.querySelector("img").src = frameUrl(v.id, Math.min(2, (v.duration || 2) / 2), 480); pp.x = pp.tx = e.clientX; pp.y = pp.ty = e.clientY; peek.classList.add("on"); });
    row.addEventListener("pointermove", (e) => { pp.tx = e.clientX; pp.ty = e.clientY; });
    row.addEventListener("pointerleave", () => peek.classList.remove("on"));
    table.append(row);
  });
  if (pollIds.length) {
    let alive = true; onCleanup(() => { alive = false; });
    (async () => {
      while (alive) {
        for (const [id, tag] of pollIds) {
          try {
            const m = await api(`/api/videos/${id}`);
            if (m.state === "done") { if (alive) route(); return; }
            tag.textContent = m.status?.state === "running" ? `分析中 ${Math.round((m.status.progress || 0) * 100)}%` : "排队中";
          } catch (e) {}
        }
        await new Promise((r) => setTimeout(r, 1500));
      }
    })();
  }
}

// ================================================================ 报告
async function viewReport(id) {
  const ui = chrome({ left: h("a", { class: "link", href: "#/matches" }, "往期"), right: newMatchBtn(),
    chapters: [["r-cover", "封面"], ["r-summary", "概览"], ["r-flight", "最长的一回合"], ["r-landing", "落点"], ["r-rallies", "每个回合"], ["r-duel", "双方"], ["r-info", "信息"]] });
  let R, meta;
  try { [R, meta] = await Promise.all([api(`/api/videos/${id}/result`), api(`/api/videos/${id}`)]); }
  catch (e) {
    $app.append(h("main", { class: "sec g-ink full", "data-ground": "ink" }, h("div", { class: "grid", style: "padding-top:12vh" },
      h("div", { style: "grid-column:1/-1" }, h("div", { class: "error-state" }, h("h3", {}, "打不开这场比赛"), h("p", {}, e.message),
        h("div", { style: "display:flex;gap:12px" }, h("a", { class: "btn sm", href: "#/matches" }, "回到往期"), h("a", { class: "btn sm", href: `#/v/${id}/calib` }, "重新标定")))))));
    return;
  }
  const names = R.names || { near: "近端", far: "远端" };
  const S = R.summary;
  const matchName = `${names.near} 对 ${names.far}`;
  document.title = `${matchName} · 羽析`;
  const typeCN = R.match_type === "doubles" ? "双打" : "单打";
  const best = longest(R);
  const scoreEls = [];
  const scoreSpan = (side) => { const e = h("span", { "data-side": side }, S.points[side]); scoreEls.push(e); return e; };
  ui.r.innerHTML = "";
  ui.r.append(h("b", {}, names.near), " ", scoreSpan("near"), " : ", scoreSpan("far"), " ", h("b", {}, names.far));

  // ---- 00 封面
  const coverCanvas = h("canvas", { class: "stage", "aria-hidden": "true" });
  const cover = h("section", { class: "cover g-ink", id: "r-cover", "data-ground": "ink" }, coverCanvas,
    h("div", { class: "over grid" },
      h("div", { class: "eyebrow" }, h("span", { class: "label" }, `比赛报告 · ${fmtDate(meta.created)}`), h("span", { class: "label" }, `${typeCN} · 视频 ${fmtDur(R.video.duration)}`)),
      h("div"),
      h("div", { class: "foot" },
        h("div", { class: "matchup" }, h("span", { class: "label" }, "对阵"),
          h("h1", {}, names.near, h("em", {}, "对"), names.far)),
        h("div", { class: "scoreline" }, h("span", { class: "label" }, "这段视频里的比分"),
          h("div", { class: "numeral", "aria-label": `比分 ${S.points.near} 比 ${S.points.far}` }, scoreSpan("near"), h("i", {}, ":"), scoreSpan("far"))))),
    h("div", { class: "cue", "aria-hidden": "true" }, h("span", { class: "label" }, "向下 · 重看最长的一回合"), h("i")));
  const coverStage = Stage.create(coverCanvas, { mode: "cover", offsetX: 0.12, offsetY: -0.08, rally: best ? Stage.rallyFrom(R, best) : null });
  onCleanup(() => coverStage.destroy());

  // ---- 01 概览: 一段由真实数据写出的话 + 数字
  const unc = R.rallies.filter((r) => r.uncertain && !r.overridden).length;
  const a = S.points.near, b = S.points.far;
  const lead = a === b ? `双方 ${a} 比 ${b} 打平` : `${a > b ? names.near : names.far}以 ${Math.max(a, b)} 比 ${Math.min(a, b)} 领先`;
  const mv = R.movement;
  const summaryText = h("p", { class: "statement" },
    `这段视频里一共 ${S.num_rallies} 个回合、${S.total_shots} 拍，${lead}。`,
    best ? `最长的是第 ${best.index} 回合，来回 ${best.num_shots} 拍，持续 ${fmtDur(best.duration)}。` : "",
    mv ? `${mv.near.distance_m >= mv.far.distance_m ? names.near : names.far}跑得更多，${Math.round(Math.max(mv.near.distance_m, mv.far.distance_m))} 米。` : "",
    unc ? `有 ${unc} 个回合 AI 没有把握，标成了存疑，等你来判。` : "");
  const stat = (label, value, unit) => h("div", {}, h("span", { class: "label" }, label), h("b", {}, countUp(h("span"), value), unit ? h("small", {}, unit) : null));
  const summary = h("section", { class: "sec g-bone summary", id: "r-summary", "data-ground": "bone" },
    h("div", { class: "grid" },
      h("div", { class: "side" }, h("div", { class: "chapter-no" }, "01"), h("span", { class: "label" }, "概览")),
      h("div", { class: "main" }, wipe(summaryText)),
      h("div", { class: "stats" },
        stat("回合", S.num_rallies),
        stat("总拍数", S.total_shots),
        stat("最长回合", S.longest_rally_shots, "拍"),
        mv ? stat("双方跑动", Math.round(mv.near.distance_m + mv.far.distance_m), "米") : stat("平均每回合", S.avg_shots_per_rally, "拍"))));

  // ---- 02 飞行: 滚动驱动, 重演最长的一回合
  let flight = null;
  if (best) {
    const fCanvas = h("canvas", { class: "stage", "aria-label": `第 ${best.index} 回合的飞行重演，随滚动播放` });
    const shotNo = h("div", { class: "numeral", "aria-live": "off" }, "01");
    const who = h("div", { class: "who" }, "");
    const sub = h("span", { class: "label" }, "");
    const brBox = h("div", { class: "br" });
    const railFill = h("i");
    const rail = h("div", { class: "rail", "aria-hidden": "true" }, railFill);
    const span = best.end_t + 1.1 - best.start_t;
    best.shots.forEach((s) => rail.append(h("span", { style: `top:${((s.t - best.start_t) / span) * 100}%` })));
    flight = h("section", { class: "flight g-ink", id: "r-flight", "data-ground": "ink" },
      h("div", { class: "pin" }, fCanvas,
        h("div", { class: "ov" },
          h("div", { class: "tl" }, h("div", { class: "chapter-no" }, "02"),
            h("p", { class: "statement" }, `最长的一回合：第 ${best.index} 回合，${best.num_shots} 拍。往下滚，球会按真实的击球顺序飞一遍。`)),
          h("div", { class: "bl" }, h("span", { class: "label" }, "第"), shotNo),
          brBox),
        rail));
    const fStage = Stage.create(fCanvas, { mode: "flight", rally: Stage.rallyFrom(R, best), offsetY: -0.04 });
    onCleanup(() => fStage.destroy());
    addLoop(() => {
      const rc = flight.getBoundingClientRect();
      const p = clamp(-rc.top / Math.max(1, rc.height - innerHeight));
      fStage.setProgress(p);
      railFill.style.height = p * 100 + "%";
    });
    let lastKey = "";
    fStage.onFrame((f) => {
      const key = `${f.nShots}|${f.done}`;
      if (key === lastKey) return; lastKey = key;
      shotNo.innerHTML = `${pad(Math.max(1, f.nShots))}<small>/ ${pad(f.total)} 拍</small>`;
      brBox.innerHTML = "";
      if (f.done) {
        const L = best.landing, v = verdictOf(best);
        brBox.append(h("span", { class: "label" }, "鹰眼判定"), h("div", { class: `verdict ${v.cls}` }, v.text),
          h("span", { class: "label" }, best.winner ? `${names[best.winner]} 得分 · ${REASON[best.reason] || best.reason}` : "未判定"),
          h("button", { class: "btn sm", onclick: () => openRally(best) }, "看视频回放"));
      } else if (f.cur) {
        const i = best.shots.findIndex((s) => Math.abs(s.t - f.cur.t) < 1e-6);
        const prev = best.shots[i - 1];
        who.textContent = `${names[f.cur.side]} · ${f.cur.type}`;
        sub.textContent = `T+${(f.cur.t - best.start_t).toFixed(2)}s${prev ? ` · 距上一拍 ${(f.cur.t - prev.t).toFixed(2)} 秒` : " · 发球"}`;
        brBox.append(h("span", { class: "label" }, f.cur.side === "near" ? "近端" : "远端"), who, sub);
      } else {
        brBox.append(h("span", { class: "label" }, "待发球"));
      }
    });
  }

  // ---- 03 落点
  const courtBox = h("div");
  const legend = h("div", { class: "legend" });
  let layer = "land";
  function renderCourt() {
    courtBox.innerHTML = ""; legend.innerHTML = "";
    const svg = Court.svgCourt({});
    if (layer === "land") {
      for (const r of R.rallies) if (r.landing) {
        const st = r.uncertain && !r.overridden ? "review" : (r.landing.in && r.reason !== "下网" ? "in" : "out");
        const g = Court.landingMark(svg, r.landing.m, st, 0.16);
        g.style.cursor = "pointer"; g.addEventListener("click", () => openRally(r));
        Court.el("title", {}, g).textContent = `第 ${r.index} 回合`;
        const t = Court.el("text", { x: r.landing.m[0] + 0.3, y: r.landing.m[1] - 0.22, fill: "rgba(255,255,255,.8)", "font-size": 0.34, "font-family": "IBM Plex Mono, monospace" }, svg);
        t.textContent = pad(r.index);
      }
      legend.append(h("span", {}, h("i", { style: "background:#fff;border-radius:50%" }), "界内"),
        h("span", {}, h("i", { style: "background:var(--out)" }), "出界 / 下网"),
        h("span", {}, h("i", { style: "border:2px solid var(--shuttle);border-radius:50%" }), "存疑"));
    } else if (layer === "move" && R.movement) {
      Court.heat(svg, R.movement.near.positions_m, Court.C.nearOn);
      Court.heat(svg, R.movement.far.positions_m, Court.C.farOn);
      legend.append(h("span", {}, h("i", { style: "background:#FFB340" }), `${names.near} ${R.movement.near.distance_m} 米`),
        h("span", {}, h("i", { style: "background:#A9A6FF" }), `${names.far} ${R.movement.far.distance_m} 米`));
    } else {
      for (const r of R.rallies) for (const s of r.shots) if (s.player_m)
        Court.el("circle", { cx: s.player_m[0], cy: s.player_m[1], r: 0.12, fill: s.side === "near" ? Court.C.nearOn : Court.C.farOn }, svg);
      legend.append(h("span", {}, "每个点 = 一次击球时击球者站的位置"));
    }
    courtBox.append(svg);
  }
  const tabs = h("div", { class: "tabs", role: "tablist", "aria-label": "场地图层" });
  for (const [v, label] of [["land", "落点"], ["move", "跑动"], ["hit", "击球站位"]]) {
    tabs.append(h("button", { role: "tab", "aria-selected": String(v === layer), onclick: (e) => {
      layer = v; tabs.querySelectorAll("button").forEach((x) => x.setAttribute("aria-selected", String(x === e.currentTarget))); renderCourt();
    } }, label));
  }
  renderCourt();
  const verdicts = h("ol", { class: "verdicts" });
  const verdictEls = {};
  for (const r of R.rallies) {
    const v = verdictOf(r);
    const li = h("li", { tabindex: "0", role: "button", "aria-label": `第 ${r.index} 回合：${v.text}，打开回放`, onclick: () => openRally(r), onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openRally(r); } } },
      h("span", { class: "r" }, `R${pad(r.index)}`), h("span", { class: "v" }, v.text), h("span", { class: "d" }, verdictDetail(r)));
    verdictEls[r.index] = li;
    verdicts.append(li);
  }
  const landing = h("section", { class: "sec g-bone landing", id: "r-landing", "data-ground": "bone" },
    h("div", { class: "grid" },
      h("div", { class: "court-col" }, tabs, courtBox, legend),
      h("div", { class: "text-col" }, h("div", { class: "chapter-no" }, "03"), wipe(h("h2", { class: "display" }, "落点")),
        h("p", { class: "body" }, "只用球第一次触地的位置来判：球落地后常被腿或球拍碰走，最后停下的地方不算。离线不到 8 厘米、或离网不到 40 厘米的，AI 不下结论，标成存疑。"),
        verdicts)));

  // ---- 04 每个回合
  const rallyList = h("div", { class: "rally-list" });
  const resEls = {};
  if (!R.rallies.length) rallyList.append(h("div", { class: "empty-state" }, h("p", { class: "statement" }, "没有识别到完整的回合。"),
    h("p", { class: "body" }, "可以检查四个角是否标准，或者换一段机位固定、光线充足的视频。"), h("a", { class: "btn sm", href: `#/v/${id}/calib` }, "重新标定")));
  for (const r of R.rallies) {
    const nn = r.shots.filter((s) => s.side === "near").length;
    const res = h("div", { class: "res" });
    const paintRes = () => { res.innerHTML = ""; res.append(h("b", {}, r.winner ? `${names[r.winner]} 得分` : "未判定"),
      r.uncertain ? h("span", { class: "tag review" }, r.overridden ? "已改判" : "存疑") : (REASON[r.reason] || r.reason)); };
    paintRes(); resEls[r.index] = paintRes;
    rallyList.append(h("button", { class: "rally-row", onclick: () => openRally(r), "aria-label": `第 ${r.index} 回合，${r.num_shots} 拍，打开回放` },
      h("span", { class: "no" }, pad(r.index)),
      h("span", { class: "what" }, `${r.num_shots} 拍 · ${REASON[r.reason] || r.reason}`,
        h("small", {}, `${fmtDur(r.duration)} · ${names.near} ${nn} 拍 / ${names.far} ${r.num_shots - nn} 拍`)),
      h("span", { class: "strip", "aria-hidden": "true" }, r.shots.map((s) => h("i", { class: s.side }))),
      res, h("span", { class: "go" }, "回放")));
  }
  const rallies = h("section", { class: "sec g-ink rallies", id: "r-rallies", "data-ground": "ink" },
    h("div", { class: "grid" },
      h("div", { class: "head" }, h("div", { style: "display:grid;gap:18px" }, h("div", { class: "chapter-no" }, "04"), wipe(h("h2", { class: "display" }, "每个回合"))),
        h("div", { style: "display:flex;gap:18px;align-items:center" }, h("span", { class: "label" }, h("span", { class: "dot near" }), " ", names.near), h("span", { class: "label" }, h("span", { class: "dot far" }), " ", names.far))),
      rallyList));

  // ---- 05 双方
  const count = (side, fn) => R.rallies.reduce((acc, r) => acc + r.shots.filter((s) => s.side === side && fn(s)).length, 0);
  const types = ["发球", "高远球", "杀球", "吊球", "平抽", "网前球", "挑球"].filter((t) => count("near", (s) => s.type === t) + count("far", (s) => s.type === t) > 0);
  const errs = (side, why) => R.rallies.filter((r) => r.last_hitter === side && r.reason === why).length;
  const rows = [["得分", S.points.near, S.points.far], ["击球", count("near", () => true), count("far", () => true)],
    ["出界", errs("near", "出界"), errs("far", "出界")], ["下网", errs("near", "下网"), errs("far", "下网")],
    ...(mv ? [["跑动 · 米", Math.round(mv.near.distance_m), Math.round(mv.far.distance_m)]] : []),
    ...types.map((t) => [t, count("near", (s) => s.type === t), count("far", (s) => s.type === t)])];
  const bars = h("div", { class: "bars" });
  for (const [k, l, r] of rows) {
    const m = Math.max(1, l, r);
    bars.append(h("div", { class: "b" },
      h("div", { class: "l" }, h("i", { style: `--w:${(l / m) * 100}` }), h("span", { class: "v" }, l)),
      h("div", { class: "k" }, k),
      h("div", { class: "r" }, h("span", { class: "v" }, r), h("i", { style: `--w:${(r / m) * 100}` }))));
  }
  if (types.length) bars.append(h("p", { class: "note" }, "击球类型由 AI 根据击球者离网距离、飞行时间和出球速度推断，仅供参考。"));
  scrub(bars, "--grow", 0.95, 0.6);
  const duel = h("section", { class: "sec g-bone duel", id: "r-duel", "data-ground": "bone" },
    h("div", { class: "grid" },
      h("div", { style: "grid-column:1/-1;margin-bottom:28px" }, h("div", { class: "chapter-no" }, "05")),
      h("div", { class: "names" }, h("div", { class: "n" }, h("span", { class: "dot near" }), names.near), h("span", { class: "vs" }, "对"),
        h("div", { class: "n far" }, names.far, h("span", { class: "dot far" }))),
      bars));

  // ---- 06 信息
  const info = h("section", { class: "sec g-ink info", id: "r-info", "data-ground": "ink" },
    h("div", { class: "grid" },
      h("div", { class: "col-a" }, h("div", { class: "chapter-no" }, "06"), wipe(h("h2", { class: "display" }, "信息")),
        h("p", { class: "body" }, "存疑的回合可以在回放里改判，比分会跟着更新。换了标定、单双打，重新分析会复用已有的追踪结果，几秒就出。"),
        h("div", { class: "actions" },
          h("button", { class: "btn solid", onclick: () => openPoster(R, names, meta) }, "生成分享图"),
          h("a", { class: "btn", href: `#/v/${id}/calib` }, "重新标定"),
          h("button", { class: "btn danger", onclick: async () => {
            if (!confirm(`删除「${matchName}」的视频和分析结果？删除后无法恢复。`)) return;
            try { await api(`/api/videos/${id}`, { method: "DELETE" }); toast("已删除"); go("/matches"); } catch (e) { toast(e.message); }
          } }, "删除这场"))),
      h("div", { class: "col-b" }, h("dl", { class: "spec" },
        ...[["比赛类型", typeCN], ["视频", `${fmtDur(R.video.duration)} · ${R.video.width}×${R.video.height} · ${Math.round(R.video.fps)} 帧/秒`],
            ["分析方式", R.meta.mode === "fast" ? "快速" : "精确"], ["计算设备", DEVICE[R.meta.device] || R.meta.device || "复用上次的追踪结果"],
            ["分析用时", fmtDur(R.meta.time_total_s)], ["上传时间", fmtDate(meta.created)], ["分析引擎", R.meta.engine]].flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]))),
      h("div", { class: "foot-note" }, h("span", { class: "label" }, "羽析 · 比赛报告"), h("a", { class: "link", href: "#/matches" }, "回到往期"))));

  $app.append(h("main", { id: "main" }, cover, summary, flight, landing, rallies, duel, info));

  // ============ 回放 (全屏) ============
  function openRally(r) {
    const fps = R.video.fps, T = R.trajectory;
    const video = h("video", { src: `${API}/api/videos/${id}/file`, playsinline: true, muted: true, preload: "auto" });
    const ov = h("canvas");
    const t0 = Math.max(0, r.start_t - 0.6), t1 = r.end_t + 0.9;
    const timeEl = h("span", { class: "label time" }, "");
    const playBtn = h("button", { class: "btn solid sm", onclick: () => (video.paused ? play() : video.pause()), html: ICON.play + "<span>播放</span>" });
    const slowBtn = h("button", { class: "btn sm", "aria-pressed": "false", onclick: () => {
      video.playbackRate = video.playbackRate === 1 ? 0.35 : 1;
      slowBtn.setAttribute("aria-pressed", String(video.playbackRate !== 1)); slowBtn.textContent = video.playbackRate === 1 ? "慢放" : "正常速度"; } }, "慢放");
    const shotBtns = r.shots.map((s, i) => h("button", { onclick: () => { video.currentTime = Math.max(0, s.t - 0.3); video.pause(); } },
      h("span", { class: "i" }, pad(i + 1)), h("b", {}, h("span", { class: `dot ${s.side}` }), `${names[s.side]} · ${s.type}`), h("span", {}, `+${(s.t - r.start_t).toFixed(1)}s`)));
    const idx = R.rallies.indexOf(r);
    const nav = (d) => { const nr = R.rallies[idx + d]; if (nr) { close(); openRally(nr); } };
    const v = verdictOf(r);
    const dlg = h("dialog", { class: "replay g-ink", "aria-label": `第 ${r.index} 回合回放` },
      h("div", { class: "top" },
        h("span", { class: "label" }, `回合 ${pad(r.index)} / ${pad(R.rallies.length)}`),
        h("div", { style: "display:flex;gap:18px;align-items:center" },
          idx > 0 ? h("button", { class: "link", onclick: () => nav(-1) }, "上一回合") : null,
          idx < R.rallies.length - 1 ? h("button", { class: "link", onclick: () => nav(1) }, "下一回合") : null,
          h("button", { class: "btn sm", onclick: () => close() }, "关闭"))),
      h("div", { class: "body-grid" },
        h("div", { class: "player-col" }, h("div", { class: "player" }, video, ov), h("div", { class: "ctl" }, playBtn, slowBtn, timeEl)),
        h("div", { class: "side-col" },
          h("div", { style: "display:grid;gap:10px" }, h("span", { class: "label" }, r.winner ? `${names[r.winner]} 得分` : "未判定"),
            h("h2", { class: "title" }, `${r.num_shots} 拍 · ${REASON[r.reason] || r.reason}`)),
          r.landing ? hawkCard(r) : null,
          h("div", { class: "shots" }, shotBtns))));
    document.body.append(dlg);
    dlg.showModal();
    let raf = 0;
    function close() { cancelAnimationFrame(raf); video.pause(); dlg.close(); }
    dlg.addEventListener("close", () => { cancelAnimationFrame(raf); video.pause(); dlg.remove(); });
    video.addEventListener("loadedmetadata", () => { video.currentTime = t0; });
    video.addEventListener("play", () => { playBtn.innerHTML = ICON.pause + "<span>暂停</span>"; tick(); });
    video.addEventListener("pause", () => { playBtn.innerHTML = ICON.play + "<span>播放</span>"; });
    video.addEventListener("seeked", drawOverlay);
    function play() { if (video.currentTime >= t1 - 0.05 || video.currentTime < t0 - 0.05) video.currentTime = t0; video.play().catch(() => {}); }
    function tick() {
      drawOverlay();
      if (video.currentTime >= t1) { video.pause(); return; }
      if (!video.paused) raf = requestAnimationFrame(tick);
    }
    function drawOverlay() {
      const cw = ov.clientWidth, ch = ov.clientHeight; if (!cw) return;
      const dpr = Math.min(devicePixelRatio || 1, 2);
      if (ov.width !== Math.round(cw * dpr)) { ov.width = Math.round(cw * dpr); ov.height = Math.round(ch * dpr); }
      const c = ov.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, cw, ch);
      const kx = cw / R.video.width, ky = ch / R.video.height;
      const f = Math.round(video.currentTime * fps);
      timeEl.textContent = `T+${Math.max(0, video.currentTime - r.start_t).toFixed(2)}s · ${video.playbackRate === 1 ? "1×" : "0.35×"}`;
      for (let j = Math.max(0, f - 14); j <= f && j < T.vis.length; j++) {
        if (!T.vis[j]) continue;
        const al = 1 - (f - j) / 15;
        c.beginPath(); c.arc(T.x[j] * kx, T.y[j] * ky, j === f ? 5 : 2.4, 0, 7);
        c.fillStyle = j === f ? "#F2C230" : `rgba(242,194,48,${al * 0.8})`; c.fill();
        if (j === f) { c.lineWidth = 1.5; c.strokeStyle = "#07211A"; c.stroke(); }
      }
      shotBtns.forEach((b, i) => { const s = r.shots[i]; b.classList.toggle("on", f >= s.frame && f < (r.shots[i + 1]?.frame ?? Infinity)); });
      for (const s of r.shots) {
        if (f >= s.frame && f < s.frame + fps * 0.7) {
          const x = s.px[0] * kx, y = s.px[1] * ky, txt = `${names[s.side]} ${s.type}`;
          c.font = '500 12px "IBM Plex Mono", ui-monospace, monospace';
          const w = c.measureText(txt).width + 18;
          c.fillStyle = s.side === "near" ? "rgba(255,179,64,.95)" : "rgba(169,166,255,.95)";
          c.beginPath(); c.roundRect ? c.roundRect(x - w / 2, y - 38, w, 24, 12) : c.rect(x - w / 2, y - 38, w, 24); c.fill();
          c.fillStyle = "#07211A"; c.textAlign = "center"; c.fillText(txt, x, y - 21.5);
        }
      }
      if (r.landing && f >= r.landing.frame) {
        const x = r.landing.px[0] * kx, y = r.landing.px[1] * ky;
        c.lineWidth = 2.5; c.strokeStyle = r.uncertain && !r.overridden ? "#F2C230" : (r.landing.in ? "#fff" : "#E5452F");
        c.beginPath(); c.ellipse(x, y, 18, 7, 0, 0, 7); c.stroke();
      }
    }
    requestAnimationFrame(drawOverlay);
  }

  function hawkCard(r) {
    const L = r.landing, v = verdictOf(r);
    const box = h("section", { class: "hawk", "aria-label": "鹰眼判定" }, Court.hawkEye(L, R.match_type));
    const nearNet = L.net_dist_m != null && L.net_dist_m < 0.4;
    let cm = Math.round(Math.abs(L.margin_m) * 100), txt;
    if (nearNet) { cm = Math.round(L.net_dist_m * 100); txt = `距球网 · ${L.side === "far" ? "远端一侧" : "近端一侧"}`; }
    else if (r.reason === "下网") txt = "落在击球方一侧";
    else txt = L.in ? `距${L.line}` : `超出${L.line}`;
    box.append(h("div", { class: "call" },
      h("div", {}, h("span", { class: "label", style: "color:rgba(255,255,255,.6)" }, "鹰眼判定"), h("div", { class: `verdict ${v.cls}` }, v.text)),
      h("div", { class: "dist" }, (nearNet || r.reason !== "下网") ? h("b", {}, cm >= 100 ? `${(cm / 100).toFixed(2)} 米` : `${cm} 厘米`) : null, txt)));
    const wrap = h("div", { style: "display:grid;gap:14px" }, box);
    if (r.uncertain) {
      const why = L.net_dist_m < 0.4 ? "球落在球网附近，分不清落在哪一侧" : L.confidence === "low" ? "落地前球出了画面" : "落点离边线太近，超出了测量精度";
      const btn = (side) => h("button", { class: "btn sm", "aria-pressed": String(!!(r.overridden && r.winner === side)), onclick: async (e) => {
        try {
          const res = await api(`/api/videos/${id}/rallies/${r.index}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ winner: side }) });
          r.winner = side; r.overridden = true; S.points = res.points;
          scoreEls.forEach((el) => { el.textContent = res.points[el.dataset.side]; });
          resEls[r.index]?.();
          const li = verdictEls[r.index]; if (li) li.querySelector(".v").textContent = verdictOf(r).text;
          wrap.querySelectorAll(".review .btn").forEach((x) => x.setAttribute("aria-pressed", String(x === e.currentTarget)));
          toast(`已改判：${names[side]} 得分`);
        } catch (err) { toast(err.message); }
      } }, `判${names[side]}得分`);
      wrap.append(h("div", { class: "review" }, h("p", {}, h("b", {}, "AI 不确定。"), `${why}。看完回放，由你来判。`), h("div", { class: "btns" }, btn("near"), btn("far"))));
    }
    return wrap;
  }
}

function verdictOf(r) {
  const L = r.landing;
  if (r.uncertain && !r.overridden) return { text: "存疑", cls: "review" };
  if (r.reason === "下网") return { text: "下网", cls: "out" };
  if (!L) return { text: "未落地", cls: "" };
  return L.in ? { text: "界内", cls: "in" } : { text: "出界", cls: "out" };
}
function verdictDetail(r) {
  const L = r.landing;
  if (!L) return "没有检测到落地";
  if (L.net_dist_m != null && L.net_dist_m < 0.4) return `离网 ${Math.round(L.net_dist_m * 100)} 厘米`;
  const cm = Math.round(Math.abs(L.margin_m) * 100);
  return L.in ? `距${L.line} ${cm} 厘米` : `超出${L.line} ${cm} 厘米`;
}

// ================================================================ 分享图
function openPoster(R, names, meta) {
  const W = 1080, H = 1440, cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  const c = cv.getContext("2d");
  const SERIF = '"Instrument Serif", "YX Serif SC", "Songti SC", serif', MONO = '"IBM Plex Mono", ui-monospace, monospace';
  c.fillStyle = "#07211A"; c.fillRect(0, 0, W, H);
  c.strokeStyle = "rgba(160,220,196,.08)"; c.lineWidth = 1;
  for (let r = 120; r < 1400; r += 90) { c.beginPath(); c.arc(W * 0.7, H * 0.62, r, 0, 7); c.stroke(); }
  c.fillStyle = "rgba(241,239,232,.6)"; c.font = `500 22px ${MONO}`;
  c.fillText(`羽析 · 比赛报告 · ${fmtDate(meta.created)}`, 72, 96);
  c.fillStyle = "#F1EFE8"; c.font = `400 76px ${SERIF}`;
  c.fillText(`${names.near} 对 ${names.far}`, 70, 206);
  c.font = `400 360px ${SERIF}`; c.fillStyle = "#F1EFE8";
  c.fillText(`${R.summary.points.near}`, 60, 560);
  const wN = c.measureText(`${R.summary.points.near}`).width;
  c.fillStyle = "rgba(241,239,232,.34)"; c.font = `400 180px ${SERIF}`; c.fillText(":", 60 + wN + 20, 520);
  c.fillStyle = "#F2C230"; c.font = `400 360px ${SERIF}`; c.fillText(`${R.summary.points.far}`, 60 + wN + 120, 560);
  // 场地 + 落点
  const cw = 300, sc = cw / 6.1, chh = 13.4 * sc, cx = W - 72 - cw, cy = 640;
  c.fillStyle = "#0B2E23"; c.fillRect(cx - 24, cy - 24, cw + 48, chh + 48);
  c.fillStyle = "#1D6B4F"; c.fillRect(cx, cy, cw, chh);
  c.strokeStyle = "#fff"; c.lineWidth = 2.4;
  for (const [[x1, y1], [x2, y2]] of Court.segments()) { c.beginPath(); c.moveTo(cx + x1 * sc, cy + y1 * sc); c.lineTo(cx + x2 * sc, cy + y2 * sc); c.stroke(); }
  c.strokeStyle = "#07211A"; c.lineWidth = 6; c.beginPath(); c.moveTo(cx - 12, cy + 6.7 * sc); c.lineTo(cx + cw + 12, cy + 6.7 * sc); c.stroke();
  for (const r of R.rallies) if (r.landing) {
    const x = cx + r.landing.m[0] * sc, y = cy + r.landing.m[1] * sc;
    if (r.landing.in && r.reason !== "下网") { c.beginPath(); c.arc(x, y, 10, 0, 7); c.fillStyle = "#fff"; c.fill(); }
    else { c.strokeStyle = "#E5452F"; c.lineWidth = 6; c.lineCap = "round"; c.beginPath(); c.moveTo(x - 9, y - 9); c.lineTo(x + 9, y + 9); c.moveTo(x + 9, y - 9); c.lineTo(x - 9, y + 9); c.stroke(); }
  }
  const S = R.summary, items = [[S.num_rallies, "回合"], [S.total_shots, "总拍数"], [S.longest_rally_shots, "最长回合 · 拍"]];
  if (R.movement) items.push([Math.round(R.movement.near.distance_m + R.movement.far.distance_m), "双方跑动 · 米"]);
  items.forEach(([v, label], i) => {
    const y = 700 + i * 170;
    c.fillStyle = "rgba(241,239,232,.28)"; c.fillRect(72, y, 480, 1);
    c.fillStyle = "rgba(241,239,232,.6)"; c.font = `500 20px ${MONO}`; c.fillText(label, 72, y + 40);
    c.fillStyle = "#F1EFE8"; c.font = `400 110px ${SERIF}`; c.fillText(String(v), 70, y + 150);
  });
  c.fillStyle = "rgba(241,239,232,.45)"; c.font = `500 20px ${MONO}`; c.fillText("由羽析从比赛视频自动生成 · 击球类型为 AI 推断", 72, H - 64);
  const url = cv.toDataURL("image/png");
  const dlg = h("dialog", { class: "poster g-ink", "aria-label": "分享图" },
    h("div", { class: "in" },
      h("div", { class: "row" }, h("span", { class: "label" }, "分享图"), h("button", { class: "btn sm", onclick: () => dlg.close() }, "关闭")),
      h("img", { src: url, alt: "比赛分享图" }),
      h("div", { class: "row" }, h("span", { class: "label" }, "手机上长按图片保存"), h("a", { class: "btn solid sm", href: url, download: `羽析-${names.near}对${names.far}.png` }, "保存图片"))));
  dlg.addEventListener("close", () => dlg.remove());
  document.body.append(dlg); dlg.showModal();
}

// ================================================================ 标定
async function viewCalib(id) {
  document.title = "标出球场 · 羽析";
  const ui = chrome({ left: h("a", { class: "link", href: "#/matches" }, "取消"), right: h("span", { class: "label" }, "标定"), hudL: "标定 · 标出球场的四个角" });
  let meta;
  try { meta = await api(`/api/videos/${id}`); } catch (e) { $app.append(h("main", { class: "calib g-ink", "data-ground": "ink" }, h("div", { class: "grid", style: "padding-top:10vh" }, h("div", { style: "grid-column:1/-1" }, offline())))); return; }
  ui.r.textContent = meta.name || "";
  const saved = JSON.parse(localStorage.getItem("yuxi.lastSetup") || "{}");
  const req = meta.request || {};
  const state = {
    t: Math.min(2, (meta.duration || 2) / 2),
    corners: req.corners ? req.corners.map((p) => [...p]) : [],
    match: req.match_type || saved.match || "singles",
    mode: req.mode || "accurate",
    names: req.names || saved.names || { near: "近端", far: "远端" },
  };
  const image = new Image();
  const canvas = h("canvas", { "aria-label": "视频画面。依次点击球场最外圈的四个角；点错了可以按住拖动。" });
  const loupeC = h("canvas", { width: 264, height: 264 });
  const loupe = h("div", { class: "loupe" }, loupeC);
  const stage = h("div", { class: "calib-stage" }, canvas, loupe, h("div", { class: "ticks", "aria-hidden": "true" }, h("i"), h("i"), h("i"), h("i")));
  const stepNo = h("div", { class: "numeral" }, "01");
  const stepTxt = h("p", {}, "");
  const tLabel = h("span", { class: "label" }, "");
  const startBtn = h("button", { class: "btn solid", onclick: start, style: "width:100%" }, "开始分析");
  const reuse = saved.corners && saved.w === meta.width && saved.h === meta.height && !req.corners
    ? h("button", { class: "link", onclick: () => { state.corners = saved.corners.map((p) => [...p]); draw(); } }, "用上次的位置") : null;
  const seg = (opts, key, onChange) => {
    const s = h("div", { class: "seg", role: "group" });
    for (const [v, label] of opts) s.append(h("button", { "aria-pressed": String(state[key] === v), onclick: (e) => {
      state[key] = v; s.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === e.currentTarget))); onChange?.(); } }, label));
    return s;
  };
  const MODE_NOTE = { accurate: "精确：每一帧看 8 次，更准，耗时约是快速的 5 到 8 倍。", fast: "快速：先看个大概，之后随时可以用精确模式重新分析。" };
  const modeNote = h("p", { class: "hint" }, MODE_NOTE[state.mode]);
  const nameIn = (side, label) => h("label", { class: "field" }, h("span", { class: "label" }, h("span", { class: `dot ${side}` }), label),
    h("input", { value: state.names[side], maxlength: 8, oninput: (e) => { state.names[side] = e.target.value.trim() || (side === "near" ? "近端" : "远端"); } }));

  $app.append(h("main", { class: "calib g-ink", id: "main", "data-ground": "ink" }, h("div", { class: "grid" },
    h("div", { class: "stage-col" }, stage,
      h("div", { style: "display:flex;gap:22px;align-items:center;flex-wrap:wrap" },
        h("button", { class: "link", onclick: () => { state.corners = []; draw(); } }, "重新点"), reuse,
        h("div", { class: "scrub", style: "flex:1;min-width:220px" },
          h("input", { type: "range", min: 0, max: Math.max(0.1, (meta.duration || 1) - 0.1), step: 0.1, value: state.t, "aria-label": "换一帧画面",
            oninput: (e) => { state.t = +e.target.value; tLabel.textContent = `${state.t.toFixed(1)} 秒`; }, onchange: loadFrame }), tLabel)),
      h("p", { class: "hint", style: "color:var(--fg-3);font-size:13px" }, "角被人挡住时，拖动滑块换一帧画面。")),
    h("div", { class: "panel" },
      h("div", { class: "step" }, stepNo, stepTxt),
      h("div", { class: "field" }, h("span", { class: "label" }, "比赛类型"), seg([["singles", "单打"], ["doubles", "双打"]], "match")),
      h("div", { class: "names" }, nameIn("near", "近端 · 离镜头近"), nameIn("far", "远端")),
      h("div", { class: "field" }, h("span", { class: "label" }, "分析方式"), seg([["accurate", "精确"], ["fast", "快速"]], "mode", () => { modeNote.textContent = MODE_NOTE[state.mode]; }), modeNote),
      startBtn))));
  tLabel.textContent = `${state.t.toFixed(1)} 秒`;

  function loadFrame() {
    image.onload = () => { canvas.width = image.naturalWidth; canvas.height = image.naturalHeight; draw(); };
    image.onerror = () => toast("取不到视频画面。视频格式可能不支持，建议用 mp4。", 4200);
    image.src = `${API}/api/videos/${id}/frame?t=${state.t}`;
  }
  const scale = () => meta.width / (canvas.width || meta.width);
  function draw() {
    if (!image.naturalWidth) return;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(image, 0, 0);
    ctx.fillStyle = "rgba(7,33,26,.28)"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    const k = scale(), pts = state.corners.map(([x, y]) => [x / k, y / k]);
    const lw = Math.max(1.5, canvas.width / 700);
    if (pts.length === 4) {
      const Hm = Court.metersToPixels(pts);
      ctx.save(); ctx.lineWidth = lw; ctx.strokeStyle = "rgba(242,194,48,.95)";
      for (const [a, b] of Court.segments()) { const p = Court.apply(Hm, a), q = Court.apply(Hm, b); ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke(); }
      const n1 = Court.apply(Hm, [0, Court.NET]), n2 = Court.apply(Hm, [Court.W, Court.NET]);
      ctx.setLineDash([lw * 4, lw * 3]); ctx.beginPath(); ctx.moveTo(...n1); ctx.lineTo(...n2); ctx.stroke(); ctx.restore();
    } else if (pts.length > 1) {
      ctx.save(); ctx.strokeStyle = "rgba(242,194,48,.85)"; ctx.lineWidth = lw; ctx.setLineDash([lw * 4, lw * 3]);
      ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(...p) : ctx.moveTo(...p))); ctx.stroke(); ctx.restore();
    }
    // 编号准星
    ctx.font = `500 ${Math.round(lw * 9)}px "IBM Plex Mono", ui-monospace, monospace`;
    pts.forEach(([x, y], i) => {
      const r = lw * 9, g = lw * 3;
      ctx.strokeStyle = "#F2C230"; ctx.lineWidth = lw;
      ctx.beginPath(); ctx.moveTo(x - r, y); ctx.lineTo(x - g, y); ctx.moveTo(x + g, y); ctx.lineTo(x + r, y);
      ctx.moveTo(x, y - r); ctx.lineTo(x, y - g); ctx.moveTo(x, y + g); ctx.lineTo(x, y + r); ctx.stroke();
      ctx.beginPath(); ctx.arc(x, y, r * 0.62, 0, 7); ctx.stroke();
      ctx.fillStyle = "#F2C230"; ctx.fillText(pad(i + 1), x + r * 0.8, y - r * 0.8);
    });
    const n = state.corners.length;
    stepNo.innerHTML = n < 4 ? `${pad(n + 1)}<small> / 04</small>` : `OK`;
    stepTxt.textContent = n < 4
      ? ["点球场最外圈的一个角：双打边线和底线的交点。", "再点下一个角。", "第三个角。", "最后一个角。"][n]
      : "黄线应该和场地白线重合。不准的话，按住角点拖动微调。";
    startBtn.disabled = n < 4;
  }
  // 触控: 按下记录, 拖动微调, 放大镜
  let drag = -1;
  const toImg = (e) => { const r = canvas.getBoundingClientRect(); return [(e.clientX - r.left) / r.width * canvas.width, (e.clientY - r.top) / r.height * canvas.height]; };
  function showLoupe(e, p) {
    const r = canvas.getBoundingClientRect(), sr = stage.getBoundingClientRect();
    const lx = e.clientX - sr.left, ly = e.clientY - sr.top;
    loupe.style.display = "block";
    loupe.style.left = Math.min(sr.width - 136, Math.max(4, lx - 66)) + "px";
    loupe.style.top = (ly - 170 < 0 ? ly + 44 : ly - 170) + "px";
    const z = 3.5, c = loupeC.getContext("2d"), s = 264 / z * (canvas.width / r.width) / 2;
    c.clearRect(0, 0, 264, 264); c.drawImage(canvas, p[0] - s, p[1] - s, s * 2, s * 2, 0, 0, 264, 264);
    c.strokeStyle = "#F2C230"; c.lineWidth = 1.5; c.beginPath(); c.moveTo(132, 108); c.lineTo(132, 156); c.moveTo(108, 132); c.lineTo(156, 132); c.stroke();
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
    startBtn.disabled = true; startBtn.textContent = "正在提交…";
    const body = { corners: state.corners, match_type: state.match, mode: state.mode, names: state.names };
    localStorage.setItem("yuxi.lastSetup", JSON.stringify({ corners: state.corners, w: meta.width, h: meta.height, match: state.match, names: state.names }));
    try {
      await api(`/api/videos/${id}/analyze`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      go(`/v/${id}/wait`);
    } catch (e) { toast(e.message); startBtn.disabled = false; startBtn.textContent = "开始分析"; }
  }
  loadFrame();
}

// ================================================================ 分析中
const STAGES = ["排队中", "加载模型", "生成背景模型", "追踪羽毛球", "轨迹补全", "识别球员", "生成报告"];
async function viewWait(id) {
  document.title = "正在分析 · 羽析";
  const ui = chrome({ left: h("a", { class: "link", href: "#/matches" }, "往期"), right: newMatchBtn(), hudL: "分析 · 在电脑上进行，可以离开这一页", hudR: "" });
  const canvas = h("canvas", { class: "stage", "aria-hidden": "true" });
  const num = h("div", { class: "numeral", "aria-live": "polite" }, "0");
  const bar = h("i");
  const eta = h("span", { class: "label" }, "");
  const log = h("ol", { class: "log", "aria-label": "分析步骤" });
  const rows = STAGES.map((s, i) => { const li = h("li", {}, h("span", {}, pad(i)), h("span", { class: "s" }, s), h("span", { class: "d" }, "")); log.append(li); return li; });
  const errBox = h("div");
  $app.append(h("main", { class: "wait g-ink", id: "main", "data-ground": "ink" }, canvas,
    h("div", { class: "over grid" },
      h("div", { class: "pct" }, h("span", { class: "label" }, "正在分析"), num, h("div", { class: "bar" }, bar), h("div", { style: "margin-top:14px;display:flex;justify-content:space-between;gap:14px" }, eta, h("span", { class: "label" }, "示意回合")), errBox),
      log)));
  const stage = Stage.create(canvas, { mode: "wait", offsetX: 0.18 });
  onCleanup(() => stage.destroy());
  const seen = {}; let alive = true, t0 = Date.now(), p0 = null;
  onCleanup(() => { alive = false; });
  api(`/api/videos/${id}`).then((m) => { ui.r.textContent = m.request?.names ? `${m.request.names.near} 对 ${m.request.names.far}` : (m.name || ""); }).catch(() => {});
  while (alive) {
    try {
      const m = await api(`/api/videos/${id}`);
      const s = m.status || {};
      const p = s.progress || 0;
      num.innerHTML = `${Math.round(p * 100)}<small>%</small>`; bar.style.width = p * 100 + "%";
      const name = s.stage === "追踪完成" ? "轨迹补全" : s.stage;
      let si = STAGES.indexOf(name); if (si < 0 && s.state === "queued") si = 0;
      if (si >= 0 && !(si in seen)) seen[si] = Date.now();
      rows.forEach((li, i) => {
        li.className = i < si ? "done" : i === si ? "now" : "";
        const d = li.querySelector(".d");
        if (i < si && seen[i] != null) { const nx = Object.keys(seen).map(Number).filter((k) => k > i).sort((a, b) => a - b)[0]; d.textContent = nx != null ? `${((seen[nx] - seen[i]) / 1000).toFixed(1)}s` : "✓"; }
        else if (i < si) d.textContent = "✓";
      });
      if (p > 0.03 && p0 == null) { p0 = p; t0 = Date.now(); }
      if (p0 != null && p - p0 > 0.02) { const el = (Date.now() - t0) / 1000; eta.textContent = `预计还需 ${fmtDur(Math.max(1, el / (p - p0) * (1 - p)))}`; }
      if (s.state === "done" || m.state === "done") { go(`/v/${id}`); return; }
      if (s.state === "error" || m.state === "error") {
        errBox.append(h("div", { class: "error-state", style: "margin-top:28px" }, h("h3", {}, "分析没有完成"), h("p", {}, m.error || s.stage || "未知错误"),
          h("div", {}, h("a", { class: "btn sm", href: `#/v/${id}/calib` }, "重新标定"))));
        return;
      }
    } catch (e) { eta.textContent = "连接中断，正在重试…"; }
    await new Promise((r) => setTimeout(r, 1000));
  }
}

// ================================================================ 404
function viewLost() {
  document.title = "找不到这一页 · 羽析";
  chrome({ left: h("a", { class: "link", href: "#/" }, "首页"), right: newMatchBtn(), hudL: "404" });
  $app.append(h("main", { class: "g-ink lost grid", id: "main", "data-ground": "ink" },
    h("div", { class: "numeral" }, "出界。"),
    h("p", { class: "statement" }, "这一页不存在，可能是链接写错了。"),
    h("a", { class: "btn", href: "#/" }, "回到首页")));
}

route();
