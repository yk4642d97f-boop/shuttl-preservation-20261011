/* ============================================================
   羽析 · 比赛详情 (对标 SwingVision 的 Match 页)
   左: 记分卡 + 视频 (实时比分牌 / 落点小地图 / 击球标签 / 轨迹) + 回合缩略图
   右: 比赛数据 / 回合记录 / 击球分析 / 落点   + 信息与操作
   ============================================================ */
const SHOT_TYPES = ["发球", "高远球", "杀球", "吊球", "平抽", "网前球", "挑球"];

function matchModel(R) {
  const names = R.names || { near: "近端", far: "远端" };
  const shotsOf = (side) => R.rallies.flatMap((r) => r.shots.filter((s) => !side || s.side === side));
  const hitterOf = (r) => r.last_hitter || r.shots[r.shots.length - 1]?.side;
  const winners = (side) => R.rallies.filter((r) => r.winner === side && hitterOf(r) === side).length;
  const errs = (side, why) => R.rallies.filter((r) => hitterOf(r) === side && r.winner && r.winner !== side && (!why || r.reason === why)).length;
  const gaps = R.rallies.flatMap((r) => r.shots.slice(1).map((s, i) => s.t - r.shots[i].t)).filter((g) => g > 0.15);
  const longest = R.rallies.reduce((a, r) => (!a || r.num_shots > a.num_shots ? r : a), null);
  const landed = R.rallies.filter((r) => r.landing && !(r.uncertain && !r.overridden));
  const inRate = landed.length ? pct(landed.filter((r) => r.landing.in && r.reason !== "下网").length, landed.length) : null;
  return { names, shotsOf, hitterOf, winners, errs, gaps, longest, inRate };
}

async function viewMatch(id) {
  const nav = navbar({ title: "比赛", left: backBtn("/", "比赛") });
  const main = h("main", { class: "screen no-tab", id: "main" }, h("div", { class: "wrap-wide match-layout" },
    h("div", { class: "left" }, h("div", { class: "skel", style: "height:150px" }), h("div", { class: "skel", style: "aspect-ratio:16/9" })),
    h("div", { class: "right" }, h("div", { class: "skel", style: "height:44px" }), h("div", { class: "skel", style: "height:420px" }))));
  $app.append(main);
  let R, meta;
  try { [R, meta] = await Promise.all([api(`/api/videos/${id}/result`), api(`/api/videos/${id}`)]); }
  catch (e) {
    main.firstChild.replaceChildren(h("div", { style: "grid-column:1/-1" }, h("div", { class: "card error-card" }, h("div", { class: "empty" },
      h("div", { class: "art" }, icon("info")), h("h3", {}, "打不开这场比赛"), h("p", {}, e.message),
      h("div", { style: "display:flex;gap:10px" }, h("a", { class: "btn gray sm", href: "#/" }, "回到比赛"), h("a", { class: "btn sm", href: `#/v/${id}/calib` }, "重新标定"))))));
    return;
  }
  const M = matchModel(R), names = M.names, S = R.summary;
  document.title = `${names.near} 对 ${names.far} · 羽析`;
  const ctx = { R, meta, id, M, names, refresh: () => {} };

  // ---- 右上: 分享
  nav.querySelector(".r").append(h("button", { class: "icon-btn lg", "aria-label": "生成分享图", onclick: () => openPoster(ctx) }, icon("share")));

  // ---- 记分卡
  const header = h("section", { class: "card", "aria-label": "比分" });
  function paintHeader() {
    const pr = (side) => h("div", { class: `prow ${S.points[side] > S.points[other(side)] ? "win" : ""}` }, avatar(names[side], side),
      h("span", { class: "name" }, names[side]), h("span", { class: "pts num" }, icon("check", "check"), S.points[side]));
    header.replaceChildren(
      h("div", { class: "meta", style: "margin-bottom:14px" }, h("span", {}, icon("cal"), fmtDate(meta.created)), h("span", {}, icon("clock"), fmtClock(R.video.duration)),
        h("span", {}, R.match_type === "doubles" ? "双打" : "单打"), h("span", {}, icon("bolt"), R.meta.mode === "fast" ? "快速分析" : "精确分析")),
      h("div", { class: "scorecard" }, pr("near"), pr("far")),
      h("div", { class: "meta", style: "margin-top:14px;padding-top:12px;border-top:.5px solid var(--hairline-2)" },
        h("span", {}, icon("list"), `${S.num_rallies} 回合`), h("span", {}, icon("shuttle"), `${S.total_shots} 拍`),
        R.movement ? h("span", {}, icon("run"), `跑动 ${Math.round(R.movement.near.distance_m + R.movement.far.distance_m)} 米`) : null));
  }
  paintHeader();

  // ---- 播放器 + 回合带
  const player = matchPlayer(ctx);
  ctx.player = player;
  const reel = h("div", { class: "reel", role: "list", "aria-label": "每个回合" });
  const reelBtns = {};
  for (const r of R.rallies) {
    const v = verdictOf(r);
    const b = h("button", { role: "listitem", "aria-label": `播放第 ${r.index} 回合，${r.num_shots} 拍，${v.text}`, onclick: () => player.playRally(r) },
      h("div", { class: "im" }, thumbImg(frameUrl(id, r.start_t + Math.min(1.5, r.duration / 3), 360)), h("span", { class: `chip ${v.cls || "glass"}` }, v.text), h("span", { class: "play" }, icon("play"))),
      h("div", { class: "cap" }, h("b", {}, `第 ${r.index} 回合`), h("span", { class: "num" }, `${r.num_shots} 拍`)));
    reelBtns[r.index] = b; reel.append(b);
  }
  player.onRally((r) => {
    Object.entries(reelBtns).forEach(([k, b]) => b.setAttribute("aria-current", String(r && +k === r.index)));
    const b = r && reelBtns[r.index];
    if (b) reel.scrollTo({ left: b.offsetLeft - reel.clientWidth / 2 + b.offsetWidth / 2, behavior: REDUCED ? "auto" : "smooth" });
  });

  const wide = matchMedia("(min-width: 1024px)").matches;
  const left = h("div", { class: "left" }, wide ? null : header, player.el, player.trim,
    R.rallies.length ? h("div", {}, h("h2", { class: "section-h", style: "margin-top:10px" }, "每个回合", h("small", {}, "点一下直接播放")), reel) : null);

  // ---- 分页
  const pane = h("div", { class: "stack" });
  let tab = "stats";
  const tabs = segmented([["stats", "比赛数据"], ["history", "回合记录"], ["shots", "击球分析"], ["place", "落点"]], tab, (v) => { tab = v; paintTab(); }, { size: "lg", label: "数据分页" });
  function paintTab() {
    pane.replaceChildren(...({ stats: statsTab, history: historyTab, shots: shotsTab, place: placementTab }[tab])(ctx, player));
    enter(pane);
  }
  ctx.refresh = () => { paintHeader(); player.refresh(); paintTab(); Object.values(reelBtns).forEach((b, i) => { const r = R.rallies[i], v = verdictOf(r); const c = b.querySelector(".chip"); c.className = `chip ${v.cls || "glass"}`; c.textContent = v.text; }); };
  paintTab();

  const right = h("div", { class: "right" }, wide ? header : null, tabs, pane, infoCard(ctx));
  main.firstChild.replaceChildren(left, right);
}

// ================================================================ 播放器
function matchPlayer(ctx) {
  const { R, id, names } = ctx;
  const fps = R.video.fps, T = R.trajectory, dur = R.video.duration;
  const video = h("video", { src: `${API}/api/videos/${id}/file`, playsinline: true, preload: "metadata", "aria-label": "比赛视频" });
  const ov = h("canvas", { class: "ov", "aria-hidden": "true" });
  const scN = h("span", { class: "sc num" }, "0"), scF = h("span", { class: "sc num" }, "0");
  const bug = h("div", { class: "scorebug", "aria-live": "off" }, h("span", { class: "nm" }, h("span", { class: "dot" }), names.near), scN, h("span", { class: "nm" }, h("span", { class: "dot far" }), names.far), scF);
  const rallyChip = h("span", { class: "chip glass" }, "");
  const mini = h("div", { class: "hud-tr", "aria-hidden": "true" });
  const shotbug = h("div", { class: "shotbug", style: "visibility:hidden" }, h("span", { class: "ty" }, ""), h("span", { class: "who" }, ""));
  const bigplay = h("button", { class: "bigplay", "aria-label": "播放" }, icon("play"));
  const playBtn = h("button", { class: "icon-btn glass", "aria-label": "播放" }, icon("play"));
  const time = h("span", { class: "time" }, "0:00 / " + fmtClock(dur));
  const head = h("i", { class: "head" });
  const track = h("div", { class: "track", role: "slider", tabindex: "0", "aria-label": "进度", "aria-valuemin": 0, "aria-valuemax": Math.round(dur) }, h("i", { class: "base" }));
  const segEls = R.rallies.map((r) => { const s = h("i", { class: "seg-r", style: `left:${(r.start_t / dur) * 100}%;width:${Math.max(0.6, ((r.end_t - r.start_t) / dur) * 100)}%` }); track.append(s); return s; });
  track.append(head);
  const SPEEDS = [1, 0.5, 0.25];
  const spd = h("button", { class: "spd", "aria-pressed": "false", "aria-label": "慢放" }, "1×");
  const el = h("div", { class: "player", "data-playing": "false" }, video, ov,
    h("div", { class: "hud-tl" }, bug, rallyChip), mini, h("div", { class: "hud-br" }, shotbug), bigplay,
    h("div", { class: "ctl" }, playBtn, track, time, spd));

  // 去掉死球时间: 只播每个回合 (前 0.6 秒 + 后 0.9 秒)
  const windows = R.rallies.map((r) => [Math.max(0, r.start_t - 0.6), Math.min(dur, r.end_t + 0.9), r]);
  const trimmedLen = windows.reduce((a, [s, e]) => a + (e - s), 0);
  let trim = windows.length > 0;
  const trimEl = h("div", { class: "card trimbar" },
    h("div", { style: "display:flex;gap:12px;align-items:center" }, h("span", { class: "ico-tile", style: "width:32px;height:32px;border-radius:9px;display:grid;place-items:center;background:var(--lime-soft);color:var(--lime)" }, icon("scissors")),
      h("p", {}, h("b", {}, "去掉死球时间"), h("br"), `${fmtClock(dur)} 的视频只看 ${fmtClock(trimmedLen)}`)),
    toggle(trim, (v) => { trim = v; }, "去掉死球时间"));
  if (!windows.length || trimmedLen > dur * 0.9) trimEl.hidden = true;

  let onRallyCb = null, curRally = undefined, lastScore = "", lastShot = null, lastMiniN = -1, dirty = true;
  const rallyAt = (t) => R.rallies.find((r) => t >= r.start_t - 0.6 && t <= r.end_t + 0.9) || null;

  function paintMini(t) {
    const done = R.rallies.filter((r) => r.landing && t >= r.landing.t);
    if (done.length === lastMiniN) return; lastMiniN = done.length;
    const { svg, layer } = Court.plot({ landscape: true, pad: 0.3, lineW: 0.08, surround: false });
    done.forEach((r, i) => Court.landingMark(layer, r.landing.m, { side: ctx.M.hitterOf(r), state: landingState(r), r: 0.3, i }));
    svg.classList.add("play"); mini.replaceChildren(svg);
  }
  function paintScore(t) {
    let a = 0, b = 0;
    for (const r of R.rallies) if (t >= r.end_t && r.winner) r.winner === "near" ? a++ : b++;
    const key = a + ":" + b; if (key === lastScore) return;
    const prev = lastScore.split(":"); lastScore = key;
    scN.textContent = a; scF.textContent = b;
    if (prev.length === 2 && !REDUCED) { const el = +prev[0] !== a ? scN : +prev[1] !== b ? scF : null; if (el) { el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump"); } }
  }
  function draw() {
    const t = video.currentTime, f = Math.round(t * fps);
    const cw = ov.clientWidth, ch = ov.clientHeight; if (!cw) return;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    if (ov.width !== Math.round(cw * dpr)) { ov.width = Math.round(cw * dpr); ov.height = Math.round(ch * dpr); }
    const c = ov.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, cw, ch);
    // 视频是 contain 显示, 先算出画面实际占的矩形
    const s = Math.min(cw / R.video.width, ch / R.video.height), ox = (cw - R.video.width * s) / 2, oy = (ch - R.video.height * s) / 2;
    const P = (x, y) => [ox + x * s, oy + y * s];
    const r = rallyAt(t);
    if (r) {
      // 轨迹: 最近 18 帧, 越旧越淡越小
      for (let j = Math.max(0, f - 18); j <= f && j < T.vis.length; j++) {
        if (!T.vis[j]) continue;
        const k = 1 - (f - j) / 19, [x, y] = P(T.x[j], T.y[j]);
        c.beginPath(); c.arc(x, y, j === f ? 5 : 1.4 + k * 2.4, 0, 7);
        c.fillStyle = j === f ? "#C9E83C" : `rgba(201,232,60,${k * 0.85})`; c.fill();
        if (j === f) { c.lineWidth = 1.5; c.strokeStyle = "rgba(0,0,0,.6)"; c.stroke(); }
      }
      const L = r.landing;
      if (L && f >= L.frame && t < L.t + 1.4) {
        const [x, y] = P(L.px[0], L.px[1]), a = clamp((t - L.t) / 0.5);
        const col = r.uncertain && !r.overridden ? "255,204,0" : L.in && r.reason !== "下网" ? "48,209,88" : "255,69,58";
        c.lineWidth = 2.5; c.strokeStyle = `rgba(${col},${1 - a * 0.4})`;
        c.beginPath(); c.ellipse(x, y, 10 + a * 16, 4 + a * 6, 0, 0, 7); c.stroke();
      }
    }
    // 击球标签
    const shot = r ? [...r.shots].reverse().find((sh) => sh.t <= t && t - sh.t < 1.3) : null;
    if (shot !== lastShot) {
      lastShot = shot;
      if (shot) { shotbug.style.visibility = "visible"; shotbug.firstChild.textContent = shot.type; shotbug.lastChild.textContent = names[shot.side]; shotbug.classList.remove("pop"); void shotbug.offsetWidth; shotbug.classList.add("pop"); }
      else shotbug.style.visibility = "hidden";
    }
    if (r !== curRally) {
      curRally = r; rallyChip.textContent = r ? `第 ${r.index} 回合` : "死球时间"; rallyChip.style.visibility = r || !video.paused ? "visible" : "hidden";
      segEls.forEach((s, i) => s.classList.toggle("cur", R.rallies[i] === r)); onRallyCb?.(r);
    }
    if (r) { const i = r.shots.filter((sh) => sh.t <= t).length; rallyChip.textContent = `第 ${r.index} 回合 · 第 ${Math.max(1, i)} 拍`; }
    paintScore(t); paintMini(t);
    head.style.left = (t / dur) * 100 + "%"; track.setAttribute("aria-valuenow", Math.round(t));
    time.textContent = `${fmtClock(t)} / ${fmtClock(dur)}`;
  }
  addLoop(() => {
    if (!video.paused && trim && windows.length) {
      const t = video.currentTime;
      if (!windows.some(([s, e]) => t >= s && t < e)) {
        const next = windows.find(([s]) => s > t);
        if (next) video.currentTime = next[0]; else { video.pause(); video.currentTime = windows[0][0]; }
      }
    }
    if (!video.paused || dirty) { dirty = false; draw(); }
  });
  const setPlaying = (p) => { el.dataset.playing = String(p); playBtn.replaceChildren(icon(p ? "pause" : "play")); playBtn.setAttribute("aria-label", p ? "暂停" : "播放"); };
  video.addEventListener("play", () => setPlaying(true));
  video.addEventListener("pause", () => { setPlaying(false); dirty = true; });
  video.addEventListener("seeked", () => { dirty = true; });
  video.addEventListener("loadedmetadata", () => { if (windows.length) video.currentTime = windows[0][0]; dirty = true; });
  video.addEventListener("error", () => { toast("这个视频浏览器播放不了，可以换成 mp4 再上传", { bad: true, ms: 4200 }); });
  const toggle_ = () => (video.paused ? video.play().catch(() => {}) : video.pause());
  bigplay.addEventListener("click", toggle_); playBtn.addEventListener("click", toggle_);
  video.addEventListener("click", toggle_);
  spd.addEventListener("click", () => { const i = (SPEEDS.indexOf(video.playbackRate) + 1) % SPEEDS.length; video.playbackRate = SPEEDS[i]; spd.textContent = SPEEDS[i] + "×"; spd.setAttribute("aria-pressed", String(SPEEDS[i] !== 1)); });
  // 进度条: 按下即跳转, 拖动连续跳
  const seekAt = (e) => { const rc = track.getBoundingClientRect(); video.currentTime = clamp((e.clientX - rc.left) / rc.width) * dur; dirty = true; };
  let dragging = false;
  track.addEventListener("pointerdown", (e) => { dragging = true; track.setPointerCapture(e.pointerId); seekAt(e); });
  track.addEventListener("pointermove", (e) => dragging && seekAt(e));
  track.addEventListener("pointerup", () => { dragging = false; });
  track.addEventListener("keydown", (e) => { const d = e.key === "ArrowRight" ? 5 : e.key === "ArrowLeft" ? -5 : 0; if (d) { e.preventDefault(); video.currentTime = clamp(video.currentTime + d, 0, dur); } });
  onCleanup(() => { video.pause(); video.removeAttribute("src"); video.load(); });
  requestAnimationFrame(draw);

  return {
    el, trim: trimEl,
    playRally(r) { this.playRallyFrom(r, r.start_t - 0.6); },
    playRallyFrom(r, t) { video.currentTime = Math.max(0, t - 0.3); video.play().catch(() => {}); if (innerWidth < 1024) el.scrollIntoView({ block: "center", behavior: REDUCED ? "auto" : "smooth" }); },
    onRally(cb) { onRallyCb = cb; },
    refresh() { lastScore = ""; lastMiniN = -1; dirty = true; },
  };
}

// ================================================================ 分页: 比赛数据
function duelCard(title, names, rows, opts = {}) {
  const box = h("div", { class: "duel" });
  rows.forEach(([label, l, r], i) => {
    const m = Math.max(1e-9, l, r);
    box.append(h("div", { class: "duel-row", style: `--k:${i}` },
      h("span", { class: `n ${l >= r ? "lead" : ""}` }, typeof l === "number" ? +l.toFixed(1) : l),
      h("div", { class: "bar", role: "img", "aria-label": `${label}：${names.near} ${l}，${names.far} ${r}` },
        h("i", { class: "l", style: `--w:${(l / m) * 100}` }), h("i", { class: "rr", style: `--w:${(r / m) * 100}` }), h("span", { class: "lab" }, label)),
      h("span", { class: `n r ${r >= l ? "lead" : ""}` }, typeof r === "number" ? +r.toFixed(1) : r)));
  });
  const card = h("section", { class: "card" },
    h("div", { class: "card-head" }, h("h3", {}, title), opts.acts || null),
    h("div", { class: "duel-head" }, h("div", { class: "p" }, avatar(names.near, "near", "sm"), h("span", {}, names.near)), h("span", { class: "vs" }, "对"),
      h("div", { class: "p r" }, h("span", {}, names.far), avatar(names.far, "far", "sm"))),
    box, opts.note ? h("p", { class: "group-f", style: "margin:12px 0 0" }, opts.note) : null);
  Motion.inView(card, () => card.classList.add("grow"), 0.2);
  return card;
}
function statsTab(ctx, player) {
  const { R, M, names } = ctx, S = R.summary, mv = R.movement;
  const rows = [["得分", S.points.near, S.points.far],
    ["击球", M.shotsOf("near").length, M.shotsOf("far").length],
    ["直接得分", M.winners("near"), M.winners("far")],
    ["出界", M.errs("near", "出界"), M.errs("far", "出界")],
    ["下网", M.errs("near", "下网"), M.errs("far", "下网")]];
  if (mv) rows.push(["跑动 · 米", Math.round(mv.near.distance_m), Math.round(mv.far.distance_m)]);
  for (const t of ["杀球", "吊球", "高远球", "网前球"]) {
    const a = M.shotsOf("near").filter((s) => s.type === t).length, b = M.shotsOf("far").filter((s) => s.type === t).length;
    if (a + b) rows.push([t, a, b]);
  }
  const kpi = (v, unit, label, digits = 0) => h("div", { class: "kpi" }, h("b", { class: "num" }, Motion.countUp(h("span"), v, { digits }), unit ? h("small", {}, unit) : null), h("span", {}, label));
  const best = M.longest;
  const rally = h("section", { class: "card" },
    h("div", { class: "card-head" }, h("h3", {}, "回合"), h("div", { class: "acts" },
      best ? h("button", { class: "icon-btn", "aria-label": `播放最长的第 ${best.index} 回合`, title: "播放最长的回合", onclick: () => player.playRally(best) }, icon("play")) : null)),
    h("div", { class: "kpis" },
      kpi(S.avg_shots_per_rally, "拍", "平均每回合", 1), kpi(S.longest_rally_shots, "拍", best ? `最长 · 第 ${best.index} 回合` : "最长回合"),
      kpi(S.avg_rally_duration, "秒", "平均回合时长", 1), M.inRate != null ? kpi(M.inRate, "%", "落点界内率") : kpi(S.num_rallies, "个", "回合数")));
  const tempo = M.gaps.length ? h("section", { class: "card" },
    h("div", { class: "card-head" }, h("h3", {}, "节奏")),
    h("div", { class: "kpis" },
      kpi(M.gaps.reduce((a, b) => a + b, 0) / M.gaps.length, "秒", "平均击球间隔", 2), kpi(Math.min(...M.gaps), "秒", "最快一次来回", 2)),
    h("p", { class: "group-f", style: "margin:14px 0 0" }, "击球间隔 = 一拍到下一拍的时间，越短说明对抗越快。")) : null;
  return [duelCard("总览", names, rows, { note: "击球类型由 AI 根据击球位置、飞行时间和出球速度推断，仅供参考。" }), rally, tempo];
}

// ================================================================ 分页: 回合记录
function historyTab(ctx, player) {
  const { R, M, names } = ctx, S = R.summary;
  if (!R.rallies.length) return [h("div", { class: "card" }, h("div", { class: "empty" }, h("div", { class: "art" }, icon("list")), h("h3", {}, "没有识别到完整的回合"),
    h("p", {}, "检查四个角是否标准，或者换一段机位固定、光线充足的视频。"), h("a", { class: "btn sm", href: `#/v/${ctx.id}/calib` }, "重新标定")))];
  const lead = S.points.near === S.points.far ? null : S.points.near > S.points.far ? "near" : "far";
  const headAv = lead ? avatar(names[lead], lead, "lg") : h("span", { class: "avatars" }, avatar(names.near, "near", "lg"), avatar(names.far, "far", "lg"));
  const unc = R.rallies.filter((r) => r.uncertain && !r.overridden).length;
  const list = h("div", { class: "ph" });
  let a = 0, b = 0;
  for (const r of R.rallies) {
    if (r.winner === "near") a++; else if (r.winner === "far") b++;
    const st = rallyStory(r, names);
    const ic = st.kind === "win" ? icon("flame", "win") : st.kind === "err" ? icon("ban", "err") : icon("help");
    const w = r.winner;
    list.append(h("div", { class: "ph-row", role: "group", "aria-label": `第 ${r.index} 回合` },
      h("span", { class: "sc" }, `${a} - ${b}`),
      h("span", { class: "dots" }, w ? h("span", { class: `dot ${w === "far" ? "far" : ""}` }) : null),
      w ? avatar(names[w], w, "sm") : h("span", { class: "avatar sm", style: "--c:var(--text-3)" }, "?"),
      h("div", { class: "what" }, h("b", {}, ic, h("span", { class: "tx" }, st.text),
          r.uncertain && !r.overridden ? h("span", { class: "chip review" }, "存疑") : r.overridden ? h("span", { class: "chip lime" }, "已改判") : null),
        h("small", {}, `第 ${r.index} 回合 · ${r.num_shots} 拍 · ${r.duration.toFixed(1)} 秒`),
        h("span", { class: "strip", "aria-hidden": "true" }, r.shots.slice(0, 40).map((s) => h("i", { class: s.side === "far" ? "far" : "" })))),
      h("div", { class: "acts" },
        r.landing ? h("button", { class: "icon-btn", "aria-label": `第 ${r.index} 回合鹰眼`, title: "鹰眼", onclick: () => openChallenge(ctx, r) }, icon("target")) : null,
        h("button", { class: "icon-btn", "aria-label": `播放第 ${r.index} 回合`, onclick: () => player.playRally(r) }, icon("play")))));
  }
  return [h("section", { class: "card" },
    h("div", { class: "ph-head" }, headAv,
      h("h3", {}, lead ? `${names[lead]} ${Math.max(S.points.near, S.points.far)} - ${Math.min(S.points.near, S.points.far)} 领先` : `${S.points.near} - ${S.points.far} 打平`),
      h("div", { class: "meta" }, h("span", {}, icon("clock"), fmtDur(R.rallies.reduce((x, r) => x + r.duration, 0))), h("span", {}, `${S.num_rallies} 回合`),
        unc ? h("span", { style: "color:var(--review)" }, `${unc} 个存疑`) : h("span", {}, "全部已判定"))),
    list)];
}

// ================================================================ 分页: 击球分析
function shotsTab(ctx, player) {
  const { R, M, names } = ctx;
  let who = "all";
  const body = h("div", { class: "stack" });
  const uline = h("i", { class: "uline", "aria-hidden": "true" });
  const people = h("div", { class: "people", role: "tablist", "aria-label": "选手" }, uline);
  const opts = [["all", h("span", { class: "avatars" }, avatar(names.near, "near"), avatar(names.far, "far")), "全部"], ["near", avatar(names.near, "near"), names.near], ["far", avatar(names.far, "far"), names.far]];
  const ux = Motion.spring(0, (x) => { uline.style.transform = `translateX(${x}px)`; }), uw = Motion.spring(0, (w) => { uline.style.width = w + "px"; });
  const btns = opts.map(([k, av, label]) => { const b = h("button", { role: "tab", "aria-selected": String(k === who), onclick: () => { who = k; place(true); paint(); } }, av, label); people.append(b); return [k, b]; });
  function place(anim) {
    btns.forEach(([k, b]) => b.setAttribute("aria-selected", String(k === who)));
    const b = btns.find(([k]) => k === who)[1]; if (!b.offsetWidth) return;
    const w = 28, x = b.offsetLeft + (b.offsetWidth - w) / 2;
    anim ? (ux.set(x), uw.set(w)) : (ux.jump(x), uw.jump(w));
  }
  requestAnimationFrame(() => place(false));
  function paint() {
    const side = who === "all" ? null : who;
    const shots = M.shotsOf(side);
    const types = SHOT_TYPES.map((t) => [t, M.shotsOf("near").filter((s) => s.type === t).length, M.shotsOf("far").filter((s) => s.type === t).length]).filter(([, a, b]) => (side === "near" ? a : side === "far" ? b : a + b) > 0);
    const max = Math.max(1, ...types.map(([, a, b]) => (side === "near" ? a : side === "far" ? b : a + b)));
    const bars = h("div", { class: "hbars" }, types.map(([t, a, b], i) => {
      const tot = side === "near" ? a : side === "far" ? b : a + b;
      return h("div", { class: "hbar", style: `--k:${i}` }, h("span", {}, t),
        h("div", { class: "track", role: "img", "aria-label": `${t} ${tot} 拍` },
          side !== "far" ? h("i", { class: "a", style: `--w:${(a / max) * 100}` }) : null,
          side !== "near" ? h("i", { class: "b", style: `--w:${(b / max) * 100}` }) : null),
        h("span", { class: "v" }, `${tot} · ${pct(tot, shots.length)}%`));
    }));
    const typeCard = h("section", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, "球种"), h("span", { class: "chip" }, `${shots.length} 拍`)), bars);
    Motion.inView(typeCard, () => typeCard.classList.add("grow"), 0.2);
    const kpi = (v, unit, label) => h("div", { class: "kpi" }, h("b", { class: "num" }, Motion.countUp(h("span"), v), unit ? h("small", {}, unit) : null), h("span", {}, label));
    const sides = side ? [side] : ["near", "far"];
    const cards = sides.map((sd) => {
      const mine = R.rallies.filter((r) => r.winner && M.hitterOf(r) === sd);
      const killer = {}; mine.filter((r) => r.winner === sd).forEach((r) => { const t = r.shots[r.shots.length - 1]?.type; if (t) killer[t] = (killer[t] || 0) + 1; });
      const top = Object.entries(killer).sort((x, y) => y[1] - x[1])[0];
      return h("section", { class: "card" },
        h("div", { class: "card-head" }, h("h3", { style: "display:flex;align-items:center;gap:10px" }, avatar(names[sd], sd, "sm"), names[sd])),
        h("div", { class: "kpis" },
          kpi(M.shotsOf(sd).length, "拍", "击球"), kpi(M.winners(sd), "次", "直接得分"),
          kpi(M.errs(sd), "次", "失误 (出界 / 下网)"), R.movement ? kpi(Math.round(R.movement[sd].distance_m), "米", "跑动距离") : kpi(M.shotsOf(sd).filter((s) => s.type === "杀球").length, "次", "杀球")),
        top ? h("p", { class: "group-f", style: "margin:14px 0 0" }, `最有效的一拍：${top[0]}，直接拿下 ${top[1]} 分。`) : null);
    });
    body.replaceChildren(typeCard, ...cards);
  }
  paint();
  return [h("div", {}, people), body];
}

// ================================================================ 分页: 落点
function placementTab(ctx) {
  const { R, M, names } = ctx;
  let layer = "land";
  const holder = h("div"), legend = h("div", { class: "legend" }), extra = h("div");
  function depthRow(title, side, rs) {
    const zone = (r) => { const d = Math.abs(r.landing.m[1] - Court.NET); return d < 2.2 ? 0 : d < 4.6 ? 1 : 2; };
    const own = rs.filter((r) => (r.landing.m[1] < Court.NET ? "far" : "near") === side);
    const c = [0, 0, 0]; own.forEach((r) => c[zone(r)]++);
    const lab = ["前场", "中场", "后场"];
    return h("div", {}, h("h4", {}, h("span", { class: `dot ${side === "far" ? "far" : ""}` }), `${title} · ${own.length} 个`),
      h("div", { class: "pct" }, (side === "far" ? [2, 1, 0] : [0, 1, 2]).map((i) => h("span", { class: "num" }, own.length ? pct(c[i], own.length) + "%" : "—", h("small", {}, lab[i])))));
  }
  function paint() {
    const P = Court.plot({ landscape: true });
    legend.innerHTML = ""; extra.innerHTML = "";
    if (layer === "land") {
      const rs = R.rallies.filter((r) => r.landing);
      rs.forEach((r, i) => {
        const g = Court.landingMark(P.layer, r.landing.m, { side: M.hitterOf(r), state: landingState(r), i });
        g.setAttribute("tabindex", "0"); g.setAttribute("role", "button"); g.setAttribute("aria-label", `第 ${r.index} 回合落点：${verdictOf(r).text}`);
        g.addEventListener("click", () => openChallenge(ctx, r)); g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openChallenge(ctx, r); } });
        Court.el("title", {}, g).textContent = `第 ${r.index} 回合 · ${verdictOf(r).text}`;
      });
      extra.append(h("div", { class: "halves" }, depthRow("落在左半场", "far", rs), depthRow("落在右半场", "near", rs)));
      legend.append(h("span", {}, h("i", { style: "background:var(--near)" }), `${names.near} 最后一拍`), h("span", {}, h("i", { style: "background:var(--far)" }), `${names.far} 最后一拍`),
        h("span", {}, h("b", { style: "color:var(--out);font-size:14px;line-height:1" }, "✕"), "出界 / 下网"), h("span", {}, h("i", { style: "box-shadow:inset 0 0 0 2px var(--review)" }), "存疑"));
    } else if (layer === "move" && R.movement) {
      Court.heat(P.layer, R.movement.near.positions_m, Court.C.near);
      Court.heat(P.layer, R.movement.far.positions_m, Court.C.far);
      legend.append(h("span", {}, h("i", { style: "background:var(--near)" }), `${names.near} ${R.movement.near.distance_m} 米`), h("span", {}, h("i", { style: "background:var(--far)" }), `${names.far} ${R.movement.far.distance_m} 米`));
    } else {
      let i = 0;
      for (const r of R.rallies) for (const s of r.shots) if (s.player_m) Court.el("circle", { cx: s.player_m[0], cy: s.player_m[1], r: 0.13, fill: s.side === "near" ? Court.C.near : Court.C.far, opacity: 0.85, class: "fadein", style: `--i:${i++}` }, P.layer);
      legend.append(h("span", {}, "每个点 = 一次击球时击球者脚下的位置"));
    }
    holder.replaceChildren(P.svg);
    Motion.inView(P.svg, () => P.svg.classList.add("play"), 0.25);
  }
  const seg = segmented([["land", "落点"], ["move", "跑动热图"], ["hit", "击球站位"]].filter(([k]) => k !== "move" || R.movement), layer, (v) => { layer = v; paint(); }, { size: "sm", label: "图层" });
  paint();
  return [h("section", { class: "card placement" }, h("div", { class: "card-head" }, h("h3", {}, "落点"), h("span", { class: "chip" }, "点落点看鹰眼")),
    h("div", { style: "margin-bottom:14px" }, seg), extra, holder, legend,
    h("p", { class: "group-f", style: "margin:12px 0 0" }, "只用羽毛球第一次触地的位置判定：落地后常被腿或球拍碰走，最后停下的地方不算。离线不到 8 厘米、离网不到 40 厘米的，AI 不下结论，标为存疑。"))];
}

// ================================================================ 信息与操作
function infoCard(ctx) {
  const { R, meta, id, names } = ctx;
  const rows = [["视频", `${R.video.width}×${R.video.height} · ${Math.round(R.video.fps)} 帧/秒`], ["时长", fmtDur(R.video.duration)],
    ["分析方式", R.meta.mode === "fast" ? "快速" : "精确"], ["计算设备", DEVICE[R.meta.device] || R.meta.device || "复用上次的追踪结果"],
    ["分析用时", fmtDur(R.meta.time_total_s)], ["上传时间", fmtDate(meta.created)], ["分析引擎", R.meta.engine]];
  const del = h("button", { class: "danger", onclick: async () => {
    if (!confirm(`删除「${names.near} 对 ${names.far}」的视频和分析结果？删除后无法恢复。`)) return;
    try { await api(`/api/videos/${id}`, { method: "DELETE" }); toast("已删除"); go("/"); } catch (e) { toast(e.message, { bad: true }); }
  } }, h("span", { class: "k" }, "删除这场比赛"));
  return h("div", {},
    h("h2", { class: "group-h" }, "信息"),
    h("div", { class: "card" }, h("dl", { class: "spec" }, rows.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]))),
    h("div", { class: "list", style: "margin-top:12px" },
      h("button", { onclick: () => openPoster(ctx) }, h("span", { class: "ico-tile", style: "background:var(--near)" }, icon("share")), h("span", { class: "k" }, "生成分享图"), icon("chev", "chev")),
      h("a", { href: `#/v/${id}/calib` }, h("span", { class: "ico-tile", style: "background:#5E5CE6" }, icon("court")), h("span", { class: "k" }, "重新标定、改单双打"), icon("chev", "chev")),
      del),
    h("p", { class: "group-f" }, "重新分析会复用已有的追踪结果，几秒就出。"));
}
