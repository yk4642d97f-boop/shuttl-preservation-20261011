/* ============================================================
   羽析 · 鹰眼挑战 (对标 SwingVision Line Challenge) + 分享图
   ============================================================ */
function openChallenge(ctx, r) {
  const { R, id, names } = ctx, S = R.summary, L = r.landing;
  if (!L) return;
  const fps = R.video.fps, T = R.trajectory;
  const f0 = Math.max(0, L.frame - 26), f1 = Math.min(R.video.num_frames - 1, L.frame + 8);
  const video = h("video", { src: `${API}/api/videos/${id}/file`, muted: true, playsinline: true, preload: "auto" });
  const cv = h("canvas", { "aria-label": `第 ${r.index} 回合落地瞬间的放大画面` });
  const callTxt = h("span", {}, "");
  const call = h("div", { class: "call", "aria-live": "polite" }, h("span", { class: "ball" }, icon("shuttle")), callTxt);
  const zoomChip = h("span", { class: "chip glass num" }, "");
  const range = h("input", { type: "range", min: f0, max: f1, step: 1, value: f0, "aria-label": "逐帧查看" });
  const view = h("div", { class: "lc-view" }, cv, h("div", { class: "zoom" }, zoomChip), call);

  // 放大区域: 以落点为中心, 3 倍, 保持 16:10
  const Z = 3, sw = R.video.width / Z, sh = sw / 1.6;
  const sx = clamp(L.px[0] - sw / 2, 0, R.video.width - sw), sy = clamp(L.px[1] - sh * 0.62, 0, R.video.height - sh);
  let want = f0, seeking = false, ready = false, called = false;
  const sc = Motion.spring(0, (s) => { call.style.transform = `translateX(-50%) scale(${Math.max(0, s)})`; }, "bouncy");

  function verdict() {
    const v = verdictOf(r);
    return { ...v, text: v.cls === "out" ? `${v.text}!` : v.text };
  }
  function draw() {
    const cw = cv.clientWidth, ch = cv.clientHeight; if (!cw) return;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    if (cv.width !== Math.round(cw * dpr)) { cv.width = Math.round(cw * dpr); cv.height = Math.round(ch * dpr); }
    const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.imageSmoothingQuality = "high";
    if (ready) c.drawImage(video, sx, sy, sw, sh, 0, 0, cw, ch); else { c.fillStyle = "#000"; c.fillRect(0, 0, cw, ch); }
    const f = +range.value, k = cw / sw;
    const P = (x, y) => [(x - sx) * k, (y - sy) * k];
    // 飞行轨迹: 从 f0 画到当前帧, 越接近当前越亮
    for (let j = f0; j <= f && j < T.vis.length; j++) {
      if (!T.vis[j] || j > L.frame) continue;
      const a = 0.25 + 0.75 * ((j - f0) / Math.max(1, f - f0));
      const [x, y] = P(T.x[j], T.y[j]);
      c.beginPath(); c.arc(x, y, 3.2 + a * 2.2, 0, 7); c.fillStyle = `rgba(201,232,60,${a * 0.9})`; c.fill();
    }
    const cur = Math.min(f, L.frame);
    if (T.vis[cur]) { const [x, y] = P(T.x[cur], T.y[cur]); c.beginPath(); c.arc(x, y, 8, 0, 7); c.fillStyle = "#C9E83C"; c.fill(); c.lineWidth = 2; c.strokeStyle = "rgba(0,0,0,.6)"; c.stroke(); }
    if (f >= L.frame) {
      const [x, y] = P(L.px[0], L.px[1]), v = verdict();
      const col = v.cls === "review" ? "#FFCC00" : v.cls === "in" ? "#30D158" : "#FF453A";
      c.lineWidth = 3; c.strokeStyle = col; c.beginPath(); c.ellipse(x, y, 26, 10, 0, 0, 7); c.stroke();
      c.globalAlpha = 0.25; c.fillStyle = col; c.fill(); c.globalAlpha = 1;
    }
    zoomChip.textContent = `放大 ${Z}× · ${f >= L.frame ? "落地" : `落地前 ${L.frame - f} 帧`}`;
    range.style.setProperty("--v", ((f - f0) / Math.max(1, f1 - f0)) * 100);
    const hit = f >= L.frame;
    if (hit !== called) { called = hit; if (hit) { const v = verdict(); call.className = `call ${v.cls}`; callTxt.textContent = v.text; sc.set(1); } else sc.set(0); }
  }
  function seek() {
    if (seeking || !video.readyState) return;
    seeking = true; video.currentTime = (want + 0.5) / fps;
  }
  video.addEventListener("seeked", () => { seeking = false; ready = true; draw(); if (Math.abs(video.currentTime * fps - 0.5 - want) > 0.6) seek(); });
  video.addEventListener("loadeddata", () => { seek(); autoplay(); });
  range.addEventListener("input", () => { want = +range.value; draw(); seek(); });
  let auto = true;
  range.addEventListener("pointerdown", () => { auto = false; });
  function autoplay() {
    if (REDUCED) { range.value = want = L.frame; seek(); draw(); return; }
    Motion.tween(2400, (u) => { if (!auto) return; const f = Math.round(f0 + (L.frame + 3 - f0) * u); if (f !== +range.value) { range.value = want = Math.min(f1, f); draw(); seek(); } }, Motion.ease.inOut);
  }

  // 俯视特写 + 距离
  const hawkBox = h("div");
  function paintHawk() {
    const v = verdictOf(r);
    const nearNet = L.net_dist_m != null && L.net_dist_m < 0.4;
    let cm = Math.round(Math.abs(L.margin_m) * 100), txt;
    if (nearNet) { cm = Math.round(L.net_dist_m * 100); txt = "距球网"; }
    else if (r.reason === "下网") txt = "落在击球方一侧";
    else txt = L.in ? `距${L.line}` : `超出${L.line}`;
    hawkBox.replaceChildren(h("section", { class: "card hawk" }, Court.hawkEye(L, R.match_type),
      h("div", {}, h("span", { class: "chip" }, "鹰眼判定"), h("div", { class: `verdict ${v.cls}`, style: "margin-top:8px" }, v.text),
        h("div", { class: "dist" }, (nearNet || r.reason !== "下网") ? h("b", { class: "num" }, cm >= 100 ? `${(cm / 100).toFixed(2)} 米` : `${cm} 厘米`) : null, txt),
        r.winner ? h("div", { class: "dist", style: "margin-top:10px" }, `${names[r.winner]} 得分`) : null)));
  }
  paintHawk();

  // 存疑: 由人来判
  let reviewBox = null;
  if (r.uncertain) {
    const why = L.net_dist_m < 0.4 ? "球落在球网附近，分不清落在哪一侧" : L.confidence === "low" ? "落地前球出了画面" : "落点离边线太近，超出了测量精度";
    const btn = (side) => h("button", { class: "btn gray", "aria-pressed": String(!!(r.overridden && r.winner === side)), onclick: async (e) => {
      const b = e.currentTarget; b.classList.add("busy");
      try {
        const res = await api(`/api/videos/${id}/rallies/${r.index}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ winner: side }) });
        r.winner = side; r.overridden = true; S.points = res.points;
        reviewBox.querySelectorAll(".btn").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        paintHawk(); called = false; draw(); ctx.refresh();
        toast(`已改判：${names[side]} 得分`);
      } catch (err) { toast(err.message, { bad: true }); }
      b.classList.remove("busy");
    } }, avatar(names[side], side, "sm"), `判${names[side]}得分`);
    reviewBox = h("div", { class: "review-box" }, h("p", {}, h("b", {}, "AI 不确定。"), `${why}。看完慢放，由你来判。`), h("div", { class: "btns" }, btn("near"), btn("far")));
  }

  // 这一回合的每一拍
  const shots = h("div", { class: "shots" }, r.shots.map((s, i) => h("button", { onclick: () => { sh_.close(); ctx.player?.playRallyFrom?.(r, s.t); } },
    h("span", { class: "i" }, pad(i + 1)), avatar(names[s.side], s.side, "sm"), h("span", {}, `${names[s.side]} · ${s.type}`), h("span", { class: "t" }, `+${(s.t - r.start_t).toFixed(1)}s`))));

  const sh_ = sheet({ title: `鹰眼 · 第 ${r.index} 回合`, onClose: () => { video.removeAttribute("src"); video.load(); },
    body: h("div", { class: "lc" }, view,
      h("div", { class: "scrubber" }, range, h("p", {}, "拖动滑块逐帧看落地瞬间")),
      hawkBox, reviewBox,
      h("h3", { class: "section-h", style: "margin:8px 2px 0" }, `这一回合的 ${r.num_shots} 拍`, h("small", {}, "点一拍从那里播放")), shots) });
  const ro = new ResizeObserver(draw); ro.observe(cv);
  sh_.dlg.addEventListener("close", () => ro.disconnect());
}

// ================================================================ 分享图 (1080×1350, SwingVision 高光卡的构成)
function openPoster(ctx) {
  const { R, M, names, meta } = ctx, S = R.summary;
  const W = 1080, H = 1350, cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  const c = cv.getContext("2d");
  const F = '-apple-system, "SF Pro Display", "PingFang SC", "Microsoft YaHei", sans-serif';
  const rr = (x, y, w, hh, r) => { c.beginPath(); c.roundRect ? c.roundRect(x, y, w, hh, r) : c.rect(x, y, w, hh); };
  c.fillStyle = "#131316"; c.fillRect(0, 0, W, H);
  const g = c.createRadialGradient(W * 0.85, 0, 0, W * 0.85, 0, 700); g.addColorStop(0, "rgba(201,232,60,.14)"); g.addColorStop(1, "rgba(201,232,60,0)");
  c.fillStyle = g; c.fillRect(0, 0, W, H);
  // 品牌
  c.fillStyle = "#C9E83C"; c.beginPath(); c.arc(92, 92, 18, 0, 7); c.fill();
  c.fillStyle = "#fff"; c.font = `700 40px ${F}`; c.fillText("羽析", 124, 106);
  c.fillStyle = "rgba(235,235,245,.5)"; c.font = `500 26px ${F}`; c.textAlign = "right"; c.fillText(fmtDate(meta.created), W - 72, 104); c.textAlign = "left";
  // 记分卡
  rr(60, 150, W - 120, 290, 36); c.fillStyle = "#26262A"; c.fill();
  [["near", 238], ["far", 368]].forEach(([side, y]) => {
    const col = side === "near" ? "#2BB255" : "#FF9500", win = S.points[side] > S.points[other(side)];
    c.fillStyle = side === "near" ? "rgba(43,178,85,.22)" : "rgba(255,149,0,.22)"; c.beginPath(); c.arc(140, y - 14, 40, 0, 7); c.fill();
    c.fillStyle = col; c.font = `600 36px ${F}`; c.textAlign = "center"; c.fillText(initial(names[side]), 140, y);
    c.textAlign = "left"; c.fillStyle = "#fff"; c.font = `600 42px ${F}`; c.fillText(names[side], 204, y);
    c.textAlign = "right"; c.fillStyle = win ? "#fff" : "rgba(235,235,245,.4)"; c.font = `500 84px ${F}`; c.fillText(String(S.points[side]), W - 110, y + 14);
    if (win) { c.strokeStyle = "#fff"; c.lineWidth = 6; c.lineCap = "round"; c.beginPath(); c.moveTo(W - 230, y - 18); c.lineTo(W - 214, y - 2); c.lineTo(W - 186, y - 34); c.stroke(); }
    c.textAlign = "left";
  });
  // 球场落点
  const cx = 60, cy = 480, cw = W - 120, chh = cw * (6.1 / 13.4) + 0;
  rr(cx, cy, cw, chh + 60, 36); c.fillStyle = "#26262A"; c.fill();
  const k = (cw - 80) / 13.4, ox = cx + 40, oy = cy + 30;
  const P = (x, y) => [ox + y * k, oy + x * k];
  c.fillStyle = "#35353B"; c.fillRect(ox, oy, 13.4 * k, 6.1 * k);
  c.strokeStyle = "rgba(255,255,255,.6)"; c.lineWidth = 3;
  for (const [[x1, y1], [x2, y2]] of Court.segments()) { const a = P(x1, y1), b = P(x2, y2); c.beginPath(); c.moveTo(...a); c.lineTo(...b); c.stroke(); }
  c.strokeStyle = "#E9E9EE"; c.lineWidth = 6; c.beginPath(); c.moveTo(...P(-0.2, 6.7)); c.lineTo(...P(6.3, 6.7)); c.stroke();
  for (const r of R.rallies) if (r.landing) {
    const [x, y] = P(r.landing.m[0], r.landing.m[1]), st = landingState(r), col = M.hitterOf(r) === "far" ? "#FF9500" : "#2BB255";
    if (st === "out") { c.strokeStyle = "#FF453A"; c.lineWidth = 8; c.lineCap = "round"; c.beginPath(); c.moveTo(x - 12, y - 12); c.lineTo(x + 12, y + 12); c.moveTo(x + 12, y - 12); c.lineTo(x - 12, y + 12); c.stroke(); }
    else if (st === "review") { c.strokeStyle = "#FFCC00"; c.lineWidth = 6; c.beginPath(); c.arc(x, y, 14, 0, 7); c.stroke(); }
    else { c.fillStyle = col; c.beginPath(); c.arc(x, y, 14, 0, 7); c.fill(); }
  }
  // 数据块
  const tiles = [[S.num_rallies, "回合"], [S.total_shots, "总拍数"], [S.longest_rally_shots, "最长回合 · 拍"], M.inRate != null ? [M.inRate + "%", "落点界内率"] : [S.avg_shots_per_rally, "平均每回合 · 拍"]];
  const ty = cy + chh + 90, tw = (W - 120 - 24) / 2, th = 150;
  tiles.forEach(([v, lab], i) => {
    const x = 60 + (i % 2) * (tw + 24), y = ty + Math.floor(i / 2) * (th + 24);
    rr(x, y, tw, th, 30); c.fillStyle = "#26262A"; c.fill();
    c.fillStyle = "#fff"; c.font = `500 64px ${F}`; c.fillText(String(v), x + 34, y + 84);
    c.fillStyle = "rgba(235,235,245,.6)"; c.font = `500 26px ${F}`; c.fillText(lab, x + 34, y + 124);
  });
  c.fillStyle = "rgba(235,235,245,.4)"; c.font = `500 24px ${F}`; c.fillText("由羽析从比赛视频自动生成 · 击球类型为 AI 推断", 60, H - 48);
  const url = cv.toDataURL("image/png");
  sheet({ title: "分享图", body: h("div", { class: "stack" },
    h("img", { class: "poster-img", src: url, alt: `${names.near} 对 ${names.far} 的比赛分享图` }),
    h("a", { class: "btn block", href: url, download: `羽析-${names.near}对${names.far}.png` }, icon("upload"), "保存图片"),
    h("p", { class: "group-f", style: "text-align:center" }, "手机上可以长按图片保存到相册。")) });
}
