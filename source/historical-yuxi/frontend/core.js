/* ============================================================
   羽析 · 核心: 工具 / 图标 / 路由 / 外壳 / 通用组件
   ============================================================ */
const $app = document.getElementById("app");
const API = (localStorage.getItem("yuxi.server") || "").replace(/\/$/, "");
const REDUCED = Motion.REDUCED;

// ---------------------------------------------------------------- 小工具
function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const k in attrs) {
    const v = attrs[k];
    if (k === "class") e.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(e.style, v);
    else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
    else if (k === "html") e.innerHTML = v;
    else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
async function api(path, opt = {}) {
  let r;
  try { r = await fetch(API + path, opt); }
  catch (e) { throw new Error("连不上分析服务。请确认电脑上的羽析正在运行。"); }
  if (!r.ok) {
    let msg = `请求失败 (${r.status})`;
    try { msg = (await r.json()).detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return r.headers.get("content-type")?.includes("json") ? r.json() : r;
}
function toast(msg, { bad = false, ms = 2600 } = {}) {
  document.querySelectorAll(".toast").forEach((t) => t.remove());
  const t = h("div", { class: "toast" + (bad ? " bad" : ""), role: "status" }, bad ? null : icon("check"), msg);
  document.body.append(t);
  setTimeout(() => t.remove(), ms);
}
const pad = (n) => String(n).padStart(2, "0");
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const fmtDate = (ts) => { const d = new Date(ts * 1000); return `${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const fmtClock = (s) => `${Math.floor(s / 60)}:${pad(Math.floor(s % 60))}`;
const fmtDur = (s) => (s >= 60 ? `${Math.floor(s / 60)} 分 ${Math.round(s % 60)} 秒` : `${Math.round(s)} 秒`);
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
const DEVICE = { mps: "Apple 芯片 GPU", cuda: "NVIDIA GPU", cpu: "CPU" };
const frameUrl = (id, t, w = 640) => `${API}/api/videos/${id}/frame?t=${Math.max(0, +t || 0).toFixed(2)}&w=${w}`;
const namesOf = (v) => v.request?.names || v.names || { near: "近端", far: "远端" };
const initial = (s) => (s || "?").trim().slice(0, 1).toUpperCase();
const avatar = (name, side, size = "") => h("span", { class: `avatar ${side === "far" ? "far" : ""} ${size}`, "aria-hidden": "true" }, initial(name));
const other = (s) => (s === "near" ? "far" : "near");

// ---------------------------------------------------------------- 图标 (线性, 1.8 描边, SF Symbols 风格)
const ICONS = {
  back: '<path d="M15 5l-7 7 7 7"/>',
  chev: '<path d="M9 5l7 7-7 7"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  play: '<path d="M7 4.5v15l12.5-7.5z" fill="currentColor" stroke="none"/>',
  pause: '<path d="M7 4.5h3.5v15H7zM13.5 4.5H17v15h-3.5z" fill="currentColor" stroke="none"/>',
  share: '<path d="M12 3v12M7.5 7.5L12 3l4.5 4.5M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7"/>',
  trash: '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13"/>',
  cal: '<rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  bolt: '<path d="M13 3L5 13.5h6L10 21l8-10.5h-6z"/>',
  shuttle: '<circle cx="7" cy="17" r="3"/><path d="M9.2 14.8L18 6M9 13l3-8 9 9-8 3" />',
  list: '<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r=".8" fill="currentColor"/><circle cx="4" cy="12" r=".8" fill="currentColor"/><circle cx="4" cy="18" r=".8" fill="currentColor"/>',
  chart: '<path d="M5 20V11M10 20V5M15 20v-7M20 20V9"/>',
  trend: '<path d="M3 17l6-6 4 4 8-8M15 7h6v6"/>',
  camera: '<path d="M3.5 8.5a2 2 0 012-2h2.2L9.2 4.5h5.6l1.5 2h2.2a2 2 0 012 2V18a2 2 0 01-2 2h-13a2 2 0 01-2-2z"/><circle cx="12" cy="13" r="3.6"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>',
  court: '<rect x="4" y="3" width="16" height="18" rx="1"/><path d="M4 12h16M12 3v5M12 16v5M4 7h16M4 17h16"/>',
  flame: '<path d="M12 21c-3.9 0-6.5-2.6-6.5-6.1 0-3.3 2.5-5.4 3.6-8.4.6 1.7 1.6 2.8 2.7 3.3.4-2.8 1.6-5.2 3.4-6.8-.2 3.3 3.3 5.9 3.3 10.4C18.5 18 15.9 21 12 21z" fill="currentColor" stroke="none"/>',
  ban: '<circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/>',
  net: '<path d="M3 20h18M5 20V9h14v11M5 12.7h14M5 16.3h14M8.5 9v11M12 9v11M15.5 9v11"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  help: '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.4a2.5 2.5 0 014.8.9c0 1.7-2.4 2.2-2.4 3.6M12 16.8v.2"/>',
  scissors: '<circle cx="6" cy="7" r="2.6"/><circle cx="6" cy="17" r="2.6"/><path d="M8.2 8.4L20 17M8.2 15.6L20 7"/>',
  target: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1" fill="currentColor"/>',
  run: '<circle cx="14.5" cy="4.5" r="1.8"/><path d="M6 20l3.5-5 3 2V21M9.5 15l1.5-6 4 2.5 3 1M11 9L7.5 10.5 6 13.5"/>',
  wifi: '<path d="M2.5 9a14 14 0 0119 0M5.5 12.2a9.5 9.5 0 0113 0M8.6 15.4a5 5 0 016.8 0"/><circle cx="12" cy="18.6" r="1" fill="currentColor"/>',
  cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9.5 9.5h5v5h-5zM9 2.5V6M15 2.5V6M9 18v3.5M15 18v3.5M2.5 9H6M2.5 15H6M18 9h3.5M18 15h3.5"/>',
  tripod: '<rect x="8" y="3" width="8" height="6" rx="1.5"/><path d="M12 9v4M12 13l-6 8M12 13l6 8M12 13v8"/>',
  landscape: '<rect x="3" y="6.5" width="18" height="11" rx="2"/><path d="M7 14l3-3 3 3 2-2 3 3"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.8v.2"/>',
  upload: '<path d="M12 16V4M7 8.5L12 4l5 4.5M4.5 15v3.5a2 2 0 002 2h11a2 2 0 002-2V15"/>',
  refresh: '<path d="M20 11.5A8 8 0 106.3 17.7M20 5v6.5h-6.5"/>',
  arrowUp: '<path d="M12 19V5M6 11l6-6 6 6"/>',
  arrowDown: '<path d="M12 5v14M6 13l6 6 6-6"/>',
  slow: '<circle cx="12" cy="13" r="8"/><path d="M12 13l3.5-3.5M12 3v2"/>',
};
function icon(name, cls = "") {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("fill", "none"); s.setAttribute("stroke", "currentColor");
  s.setAttribute("stroke-width", "1.8"); s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round");
  s.setAttribute("aria-hidden", "true"); s.setAttribute("class", "ico " + cls);
  s.innerHTML = ICONS[name] || "";
  return s;
}

// ---------------------------------------------------------------- 路由与生命周期
let cleanups = [];
const onCleanup = (fn) => cleanups.push(fn);
const addLoop = (fn) => onCleanup(Motion.loop(fn));
let lastTab = "/";

function route() {
  cleanups.forEach((f) => { try { f(); } catch (e) {} }); cleanups = [];
  document.querySelectorAll("dialog, .upload-hud").forEach((e) => e.remove());
  $app.innerHTML = "";
  window.scrollTo(0, 0);
  const p = location.hash.replace(/^#/, "") || "/";
  let m;
  if ((m = p.match(/^\/v\/([\w-]+)\/calib$/))) return viewCalib(m[1]);
  if ((m = p.match(/^\/v\/([\w-]+)\/wait$/))) return viewWait(m[1]);
  if ((m = p.match(/^\/v\/([\w-]+)$/))) return viewMatch(m[1]);
  if (p === "/") { lastTab = p; return viewHome(); }
  if (p === "/stats") { lastTab = p; return viewStats(); }
  if (p === "/guide") { lastTab = p; return viewGuide(); }
  if (p === "/settings") { lastTab = p; return viewSettings(); }
  return viewLost();
}
window.addEventListener("hashchange", route);
const go = (p) => { location.hash = p; };

// ---------------------------------------------------------------- 外壳
/** 导航栏。large=true 时页面里有大标题, 滚过大标题后小标题才出现 */
function navbar({ title = "", left = null, right = null, large = false } = {}) {
  const t = h("div", { class: "t", "aria-hidden": large ? "true" : null }, title);
  const bar = h("header", { class: "navbar", "data-large": String(large) }, h("div", { class: "l" }, left), t, h("div", { class: "r" }, right));
  $app.append(bar);
  let last = null;
  addLoop(() => {
    const s = String(scrollY > (large ? 44 : 4));
    if (s !== last) { last = s; bar.dataset.scrolled = s; }
  });
  return bar;
}
const backBtn = (href, label = "返回") => h("a", { class: "back", href: "#" + href }, icon("back"), label);

function tabbar(active) {
  const item = (href, ic, label) => h("a", { href: "#" + href, "aria-current": active === href ? "page" : null }, icon(ic), label);
  const bar = h("nav", { class: "tabbar", "aria-label": "主导航" },
    item("/", "list", "比赛"), item("/stats", "trend", "数据"),
    h("button", { class: "fab", onclick: pickVideo, "aria-label": "上传比赛视频" }, icon("plus")),
    item("/guide", "camera", "拍摄"), item("/settings", "gear", "设置"));
  $app.append(bar);
}
function largeTitle(text, eyebrow, right) {
  return h("div", { class: "large-title" }, h("div", {}, eyebrow ? h("span", { class: "eyebrow" }, eyebrow) : null, h("h1", {}, text)), right || null);
}
/** 进页动画: 子元素依次浮上来 (只在进页时发生一次) */
function enter(el) { [...el.children].forEach((c, i) => c.style.setProperty("--k", Math.min(i, 8))); el.classList.add("enter"); return el; }

// ---------------------------------------------------------------- 分段控件 (弹簧滑块)
function segmented(options, value, onChange, { size = "", label = "" } = {}) {
  const thumb = h("i", { class: "thumb", "aria-hidden": "true" });
  const root = h("div", { class: `seg ${size}`, role: "tablist", "aria-label": label }, thumb);
  let cur = value;
  const btns = options.map(([v, text]) => {
    const b = h("button", { role: "tab", type: "button", "aria-selected": String(v === cur), onclick: () => select(v, true) }, text);
    root.append(b); return [v, b];
  });
  const sx = Motion.spring(0, (x) => { thumb.style.transform = `translateX(${x}px)`; });
  const sw = Motion.spring(0, (w) => { thumb.style.width = w + "px"; });
  function place(animate) {
    const b = btns.find(([v]) => v === cur)?.[1]; if (!b || !b.offsetWidth) return;
    const x = b.offsetLeft, w = b.offsetWidth;
    if (animate) { sx.set(x); sw.set(w); } else { sx.jump(x); sw.jump(w); }
  }
  function select(v, user) {
    if (v === cur && user) return;
    cur = v; btns.forEach(([k, b]) => b.setAttribute("aria-selected", String(k === v)));
    place(true); if (user) onChange?.(v);
  }
  root.addEventListener("keydown", (e) => {
    const i = btns.findIndex(([v]) => v === cur);
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0; if (!d) return;
    const n = btns[(i + d + btns.length) % btns.length]; select(n[0], true); n[1].focus();
  });
  const ro = new ResizeObserver(() => place(false)); ro.observe(root); onCleanup(() => ro.disconnect());
  requestAnimationFrame(() => place(false));
  root.select = (v) => select(v, false);
  return root;
}

/** iOS 开关 */
function toggle(on, onChange, label) {
  const b = h("button", { class: "switch", role: "switch", "aria-checked": String(on), "aria-label": label, onclick: () => { on = !on; b.setAttribute("aria-checked", String(on)); onChange(on); } });
  return b;
}

// ---------------------------------------------------------------- 底部弹层: 弹簧弹出, 下拉关闭 (按速度或距离)
function sheet({ title, body, right = null, onClose }) {
  const grab = h("div", { class: "grab", "aria-hidden": "true" });
  const closeBtn = h("button", { class: "icon-btn", "aria-label": "关闭", onclick: () => close() }, icon("x"));
  const head = h("div", { class: "sheet-h" }, h("div"), h("h2", { tabindex: "-1", autofocus: true, style: "outline:none" }, title), h("div", { class: "r" }, right, closeBtn));
  const content = h("div", { class: "sheet-b" }, body);
  const dlg = h("dialog", { class: "sheet", "aria-label": title }, grab, head, content);
  document.body.append(dlg);
  dlg.showModal();
  let H = dlg.offsetHeight || innerHeight, closing = false;
  const sp = Motion.spring(H, (y) => {
    dlg.style.transform = `translateY(${Math.max(y, -12)}px)`;
    dlg.style.setProperty("--scrim", clamp(1 - y / H).toFixed(3));
  }, "sheet");
  sp.jump(H); sp.set(0);
  function close() {
    if (closing) return; closing = true;
    H = dlg.offsetHeight || H;
    sp.set(H, { done: () => { dlg.close(); dlg.remove(); onClose?.(); } });
    if (REDUCED) { dlg.close(); dlg.remove(); onClose?.(); }
  }
  dlg.addEventListener("cancel", (e) => { e.preventDefault(); close(); });
  dlg.addEventListener("click", (e) => { if (e.target === dlg) { const r = dlg.getBoundingClientRect(); if (e.clientY < r.top) close(); } });
  // 拖动: 按下记录, 跟手移动 (向上有阻尼), 松手按距离或速度决定
  let drag = null;
  const down = (e) => { if (e.target.closest("button")) return; drag = { y0: e.clientY, y: 0, t: performance.now(), v: 0 }; e.currentTarget.setPointerCapture(e.pointerId); };
  const move = (e) => {
    if (!drag) return;
    let y = e.clientY - drag.y0; if (y < 0) y = -Math.sqrt(-y) * 2;
    const now = performance.now(), dt = Math.max(1, now - drag.t);
    drag.v = ((y - drag.y) / dt) * 1000; drag.y = y; drag.t = now;
    sp.jump(y);
  };
  const up = () => { if (!drag) return; const { y, v } = drag; drag = null; if (y > 140 || v > 900) close(); else sp.set(0, { velocity: v }); };
  for (const el of [grab, head]) { el.addEventListener("pointerdown", down); el.addEventListener("pointermove", move); el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up); }
  return { dlg, close, content };
}

// ---------------------------------------------------------------- 上传
const filePicker = h("input", { type: "file", accept: "video/*,.mp4,.mov,.m4v", hidden: true, onchange: (e) => { const f = e.target.files[0]; e.target.value = ""; upload(f); } });
document.body.append(filePicker);
function pickVideo() { filePicker.click(); }
async function upload(f) {
  if (!f) return;
  const ring = h("div", { class: "ring" }, h("span", {}, "0%"));
  const hud = h("div", { class: "upload-hud", role: "status", "aria-live": "polite" },
    h("div", { class: "box" }, ring, h("b", {}, "正在上传"), h("p", {}, f.name)));
  document.body.append(hud);
  try {
    const meta = await new Promise((res, rej) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", API + "/api/videos");
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) { const p = e.loaded / e.total; ring.style.setProperty("--p", p); ring.firstChild.textContent = Math.round(p * 100) + "%"; } };
      xhr.onload = () => { let d = {}; try { d = JSON.parse(xhr.responseText || "{}"); } catch (e) {} xhr.status < 300 ? res(d) : rej(new Error(d.detail || "上传失败")); };
      xhr.onerror = () => rej(new Error("连不上分析服务。请确认电脑上的羽析正在运行。"));
      const fd = new FormData(); fd.append("file", f); xhr.send(fd);
    });
    hud.remove();
    go(`/v/${meta.id}/calib`);
  } catch (e) { hud.remove(); toast(e.message, { bad: true, ms: 4200 }); }
}

function offlineCard(msg) {
  return h("div", { class: "card error-card" }, h("div", { class: "empty" },
    h("div", { class: "art" }, icon("wifi")), h("h3", {}, "连不上分析服务"),
    h("p", {}, msg || "请在电脑上双击「启动羽析.command」再刷新。用手机打开时，手机和电脑要连同一个 Wi-Fi，并在「设置」里填电脑的地址。"),
    h("button", { class: "btn gray sm", onclick: () => location.reload() }, icon("refresh"), "重新连接")));
}

// ---------------------------------------------------------------- 比赛数据的派生量 (全部来自 result.json)
const verdictOf = (r) => {
  if (r.uncertain && !r.overridden) return { text: "存疑", cls: "review" };
  if (r.reason === "下网") return { text: "下网", cls: "out" };
  if (!r.landing) return { text: "未落地", cls: "" };
  return r.landing.in ? { text: "界内", cls: "in" } : { text: "出界", cls: "out" };
};
/** 一个回合用一句话怎么说: 谁、怎么得的分 */
function rallyStory(r, names) {
  const last = r.shots[r.shots.length - 1];
  const hitter = r.last_hitter || last?.side;
  if (!r.winner) return { text: "未判定", kind: "none" };
  if (r.uncertain && !r.overridden) return { text: `落点存疑 · 等你来判`, kind: "review" };
  if (r.winner === hitter) return { text: `${names[hitter]} ${last?.type || "击球"}得分`, kind: "win" };
  const why = r.reason === "下网" ? "下网" : r.reason === "出界" ? "出界" : "失误";
  return { text: `${names[hitter]} ${last?.type ? last.type + " " : ""}${why}`, kind: "err" };
}
function landingState(r) { return r.uncertain && !r.overridden ? "review" : r.landing?.in && r.reason !== "下网" ? "in" : "out"; }
