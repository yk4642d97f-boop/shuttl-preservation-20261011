// ── S4 · 30–40 s · "第七分——" / "一点就到。"
// The product, as evidence: the rally scorecard spins to rally 07, a tap opens it, "回放这一分" plays it back
// with the shots labelled. Every screen is rebuilt from the app's own components (ShuttlDesign / ShuttlResultsUI).
(() => {
  const SC = 1.28, VW = 393, VH = 852, BZ = 16;
  const PHW = VW * SC + 2 * BZ, PHH = VH * SC + 2 * BZ;
  const PCX = 1340, PCY = 600, PROT = -4;
  const ROWH = 58, LISTY = 292, LISTH = 470;
  const TAP1 = 32.15, SHEET = 32.4, TAP2 = 33.45, REPLAY = 33.75, ZOOM0 = 38.55, ZOOM1 = 39.97;
  const INKS = [C.tomato, C.cobalt, C.lilac, C.pistachio, C.butter, C.flamingo];
  const ENDS = ["界内", "出界", "下网"];
  const RALLIES = Array.from({ length: 24 }, (_, i) => {
    const n = i === 6 ? 9 : 3 + Math.floor(hash(i * 5.3) * 11);
    return {
      n, beads: Array.from({ length: n }, (_, k) => INKS[Math.floor(hash(i * 31 + k * 7.7) * INKS.length)]),
      end: i === 6 ? "界内" : ENDS[Math.floor(hash(i * 2.9) * 3)], near: i === 6 ? true : hash(i * 9.1) > 0.48, unsure: i === 4,
    };
  });
  const TARGET = -(6 * ROWH - (LISTH / 2 - ROWH / 2));
  const scrollY = t => {
    if (t < 30.25) return 0;
    if (t < 31.15) return lerp(0, -980, E.ioCubic(prog(t, 30.25, 31.15)));
    return lerp(-980, TARGET, E.outBack(prog(t, 31.15, 31.85), 1.2));
  };
  const SHOTS7 = ["serve", "clear", "drop", "lift", "drop", "net", "lift", "smash", "net"];

  const rowHTML = (r, i) => {
    const near = r.near, st = near ? `background:${C.cobalt};color:${C.card}` : `background:${C.flamingo};color:${C.ink}`;
    const beads = r.beads.slice(0, 9).map(b => `<span class="bead" style="background:${b}"></span>`).join("") +
      (r.n > 9 ? `<span class="lab" style="font-size:9px;margin-left:2px">+${r.n - 9}</span>` : "");
    return `<div class="row" style="position:absolute;left:0;right:0;top:${i * ROWH}px;height:${ROWH}px;display:flex;align-items:center;gap:10px;padding:0 14px;box-sizing:border-box;border-bottom:1px solid var(--rule)">` +
      `<div class="ny" style="font-size:24px;width:34px">${String(i + 1).padStart(2, "0")}</div>` +
      `<div style="flex:1;min-width:0"><div style="white-space:nowrap;height:13px">${beads}</div><div style="font:500 12px 'PingFang SC';color:${C.inkSoft};margin-top:3px">${r.n} 拍 · ${r.end}</div></div>` +
      (r.unsure ? `<span class="chipS" style="background:${C.butter}">不确定</span>` : "") +
      `<span class="sticker" style="${st};transform:rotate(2deg)">${near ? "近端" : "远端"}得分</span>` +
      `<span style="font:700 12px SFMono;color:${C.inkFaint}">›</span></div>`;
  };
  const statusBar = dark => `<div style="position:absolute;left:0;right:0;top:0;height:54px;display:flex;align-items:center;justify-content:space-between;padding:6px 34px 0;box-sizing:border-box;font:600 16px -apple-system,'PingFang SC';color:${dark ? C.paper : C.ink}"><span>9:41</span><span style="display:flex;gap:6px;align-items:center"><span style="width:18px;height:11px;border-radius:2px;background:currentColor;opacity:.9"></span><span style="width:26px;height:12px;border-radius:4px;border:1.5px solid currentColor;box-sizing:border-box;padding:1.5px"><span style="display:block;width:70%;height:100%;background:currentColor;border-radius:1.5px"></span></span></span></div>`;
  const tabBar = `<div style="position:absolute;left:26px;right:26px;bottom:24px;height:62px;border-radius:31px;background:${C.ink};display:flex;align-items:center;justify-content:space-around;padding:0 8px">` +
    `<span style="width:16px;height:16px;border-radius:50%;border:4px solid ${C.paper};opacity:.6;box-sizing:border-box"></span>` +
    `<span style="background:${C.cobalt};color:${C.card};font:600 16px 'PingFang SC';padding:11px 26px;border-radius:24px">比赛</span>` +
    `<span style="width:18px;height:18px;border-radius:50%;background:conic-gradient(${C.paper} 0 70%,transparent 0);opacity:.6"></span></div>`;

  S({
    t0: 30.0, t1: 40.0,
    build(root) {
      const c = this;
      css(root, { background: C.paper });
      c.h1 = headline(root, "第七分——", "zh", { fontSize: "128px", color: C.ink });
      c.h2 = headline(root, "一点就到。", "zh", { fontSize: "128px", color: C.ink });
      c.crumb = el("div", "abs mono", root, ""); css(c.crumb, { fontSize: "19px", color: C.inkSoft, letterSpacing: ".12em" });
      // phone
      c.ph = el("div", "phone", root); css(c.ph, { width: PHW + "px", height: PHH + "px" });
      el("div", "body", c.ph);
      c.scr = el("div", "scr", c.ph); css(c.scr, { inset: BZ + "px", borderRadius: "84px" });
      el("div", "island", c.ph);
      c.vp = el("div", "vp", c.scr); c.vp.style.transform = `scale(${SC})`;
      // view A · results › 回合
      const A = el("div", "fill", c.vp); c.A = A;
      css(A, { background: C.paper });
      A.innerHTML = statusBar(false) +
        `<div style="position:absolute;left:22px;top:62px;font:500 17px 'PingFang SC';color:${C.cobalt}">‹ 比赛</div>` +
        `<div class="lab" style="position:absolute;left:22px;top:100px">2026年 星期四 下午7:06</div>` +
        `<div class="ttl" style="position:absolute;left:22px;top:118px;font-size:36px">10月8日</div>` +
        `<div style="position:absolute;left:22px;right:22px;top:172px;height:44px;border-radius:22px;background:${C.ink};display:flex;padding:3px;gap:2px;box-sizing:border-box">` +
        ["概览", "落点", "回合", "移动"].map(s => `<div style="flex:1;display:flex;align-items:center;justify-content:center;border-radius:20px;font:900 15px NY,'PingFang SC';${s === "回合" ? `background:${C.cobalt};color:${C.card}` : `color:rgba(244,238,227,.7)`}">${s}</div>`).join("") + `</div>` +
        `<div style="position:absolute;left:22px;right:22px;top:232px;display:flex;align-items:center;gap:8px"><span style="font:700 11px SFMono;color:${C.tomatoText}">01</span><span style="font:600 19px 'PingFang SC'">回合记分卡</span><span style="flex:1;height:2px;background:${C.ink};margin-left:6px"></span></div>` +
        `<div style="position:absolute;left:22px;top:262px;font:400 13px 'PingFang SC';color:${C.inkSoft}">✋ 有 1 分 AI 不太确定 · 长按任一行改判</div>` +
        `<div class="card" style="position:absolute;left:16px;right:16px;top:${LISTY}px;height:${LISTH}px;overflow:hidden;border-radius:20px"><div class="rows" style="position:absolute;left:0;right:0;top:0"></div></div>` +
        tabBar;
      c.rows = A.querySelector(".rows");
      c.rows.innerHTML = RALLIES.map(rowHTML).join("");
      c.row7 = c.rows.children[6];
      c.ripple = el("div", "abs", A); css(c.ripple, { width: "60px", height: "60px", borderRadius: "50%", border: `3px solid ${C.ink}`, boxSizing: "border-box" });
      // view B · rally sheet
      c.dim = el("div", "fill", c.vp); css(c.dim, { background: "rgba(34,27,46,.32)" });
      const B = el("div", "abs", c.vp); c.B = B;
      css(B, { left: 0, top: 0, width: VW + "px", height: VH + "px", background: C.paper, borderRadius: "30px 30px 0 0", boxShadow: `0 -2px 0 ${C.ink}` });
      B.innerHTML = `<div style="position:absolute;left:50%;top:8px;width:40px;height:5px;margin-left:-20px;border-radius:3px;background:${C.inkFaint}"></div>` +
        `<div class="lab" style="position:absolute;left:24px;top:34px">回合 07 · 近端发球</div>` +
        `<div style="position:absolute;left:24px;top:56px;display:flex;align-items:baseline;gap:14px"><span class="ny" style="font-size:46px">9 拍</span>` +
        `<span class="sticker" style="background:${C.cobalt};color:${C.card};transform:rotate(-3deg)">界内 · 近端得分</span></div>` +
        `<div style="position:absolute;left:24px;right:24px;top:132px;display:flex;align-items:center;gap:8px"><span style="font:700 11px SFMono;color:${C.tomatoText}">01</span><span style="font:600 18px 'PingFang SC'">击球时间线</span><span style="flex:1;height:2px;background:${C.ink};margin-left:6px"></span></div>` +
        `<div class="chips" style="position:absolute;left:24px;right:24px;top:170px;display:flex;flex-wrap:wrap;gap:9px 8px"></div>` +
        `<div class="pill" style="position:absolute;left:46px;right:46px;top:300px;height:54px;border-radius:27px;background:${C.card};border:2.5px solid ${C.ink};box-shadow:0 4px 0 ${C.ink};display:flex;align-items:center;justify-content:center;gap:10px;font:900 19px NY,'PingFang SC'">` +
        `<span style="width:24px;height:24px;border-radius:50%;background:${C.cobalt};display:inline-flex;align-items:center;justify-content:center"><span style="width:0;height:0;border-left:9px solid ${C.card};border-top:6px solid transparent;border-bottom:6px solid transparent;margin-left:3px"></span></span>回放这一分</div>`;
      const chips = B.querySelector(".chips");
      chips.innerHTML = SHOTS7.map((k, i) => `<div style="display:flex;flex-direction:column;align-items:center;gap:4px">${chipHTML(k, 32)}<span class="lab" style="font-size:9px">${String(i + 1).padStart(2, "0")}</span></div>`).join("");
      c.pill = B.querySelector(".pill");
      // view C · replay
      const R = el("div", "fill", c.scr); c.R = R; css(R, { background: C.night, zIndex: 5 });
      c.rc = el("canvas", "abs", R); c.rc.width = Math.round(VW * SC); c.rc.height = Math.round(VH * SC);
      c.rg = c.rc.getContext("2d");
      const ov = el("div", "vp", R); ov.style.transform = `scale(${SC})`;
      ov.innerHTML = statusBar(true) +
        `<div style="position:absolute;left:20px;top:64px;width:40px;height:40px;border-radius:50%;background:${C.card};border:2px solid ${C.ink};display:flex;align-items:center;justify-content:center;font:700 18px SFMono">‹</div>` +
        `<div class="lab" style="position:absolute;left:74px;top:68px;color:${C.paper}">回放 · 回合 07</div><div class="lab rt" style="position:absolute;left:74px;top:86px;color:${C.inkFaint}"></div>` +
        `<div style="position:absolute;left:24px;right:24px;bottom:120px;height:4px;border-radius:2px;background:rgba(244,238,227,.25)"><div class="ph" style="position:absolute;top:-9px;width:5px;height:22px;border-radius:2px;background:${C.tomato}"></div><div class="tk"></div></div>` +
        `<div style="position:absolute;left:24px;right:24px;bottom:44px;height:46px;border-radius:23px;background:${C.card};border:2px solid ${C.ink};display:flex;align-items:center;justify-content:space-around;padding:0 4px;font:700 13px SFMono">` +
        ["0.25×", "0.5×", "1×", "2×"].map(s => `<span style="padding:7px 14px;border-radius:16px;${s === "1×" ? `background:${C.ink};color:${C.paper}` : ""}">${s}</span>`).join("") + `</div>`;
      c.rt = ov.querySelector(".rt"); c.rph = ov.querySelector(".ph");
      c.rlab = el("div", "abs", R);
      // replay plays the real rally from just before shot 3
      c.RTAU0 = RALLY.hits[2].t - 0.35;
      const tk = ov.querySelector(".tk");
      const span = 6.6;
      RALLY.hits.forEach(h => { const u = (h.t - c.RTAU0) / span; if (u >= 0 && u <= 1) el("div", "", tk).style.cssText = `position:absolute;left:${u * 100}%;top:-6px;width:3px;height:16px;background:${C.paper};opacity:.8`; });
      c.SPAN = span;
      // sound
      [30.25, 30.33, 30.41, 30.49, 30.57].forEach((t, i) => cue(t, "key", { pitch: .8 + i * .2, gain: .7 }));
      let last = 0, prev = 0;
      for (let f = 30.25 * 60; f <= 31.85 * 60; f++) {
        const t = f / 60, k = Math.floor(-scrollY(t) / ROWH);
        if (k !== prev && t - last > 0.028) { cue(t, "tick", { pitch: .6 + .3 * hash(f) }); last = t; }
        prev = k;
      }
      cue(31.85, "lock", { pitch: .4 }); cue(TAP1, "tap"); cue(SHEET, "sheet"); cue(TAP2, "tap"); cue(REPLAY, "swish");
      [33.9, 34.025, 34.15, 34.275, 34.4].forEach((t, i) => cue(t, "key", { pitch: 2 + i * .3, gain: .8 }));
      RALLY.hits.forEach(h => { const t = REPLAY + 0.15 + (h.t - c.RTAU0); if (t > REPLAY && t < ZOOM0) { cue(t, "thwack", { pitch: .8, gain: .45 }); if (h.ok) cue(t + 0.02, "blip", { pitch: .7 }); } });
      cue(ZOOM0, "rise", { dur: ZOOM1 - ZOOM0 });
    },
    update(lt, t) {
      const c = this;
      // phone placement; the final zoom flies into the replay screen
      const z = E.inExpo(prog(t, ZOOM0, ZOOM1));
      const sc = lerp(1, 4.2, z), rot = lerp(PROT, 0, E.ioCubic(prog(t, ZOOM0 - 0.3, ZOOM0 + 0.5)));
      const enter = E.outExpo(prog(t, 30.0, 30.55));
      const cx = lerp(PCX, W / 2, E.ioCubic(prog(t, ZOOM0 - 0.3, ZOOM0 + 0.6))), cy = lerp(PCY, H / 2 + 120 * z, z) + (1 - enter) * 700;
      put(c.ph, cx, cy, sc, rot);
      // view A
      c.rows.style.transform = `translateY(${scrollY(t)}px)`;
      const press = t > TAP1 - 0.05 && t < TAP1 + 0.2 ? 0.97 : 1;
      c.row7.style.transform = `scale(${press})`; c.row7.style.background = t > TAP1 - 0.05 && t < SHEET + 0.2 ? C.paperDeep : "transparent";
      const ru = prog(t, TAP1, TAP1 + 0.45);
      const ry = LISTY + scrollY(t) + 6 * ROWH + ROWH / 2;
      put(c.ripple, 250, ry, 0.3 + 2.6 * E.outExpo(ru), 0, ru > 0 && ru < 1 ? 1 - ru : 0);
      // view B
      const sh = E.outExpo(prog(t, SHEET, SHEET + 0.45));
      c.B.style.transform = `translateY(${lerp(VH, 300, sh)}px)`;
      vis(c.B, t >= SHEET && t < REPLAY + 0.3);
      c.dim.style.opacity = sh; vis(c.dim, t >= SHEET);
      const pd = t > TAP2 - 0.04 && t < TAP2 + 0.16;
      c.pill.style.transform = pd ? "translateY(3px)" : ""; c.pill.style.boxShadow = pd ? `0 1px 0 ${C.ink}` : `0 4px 0 ${C.ink}`;
      // view C
      const rOn = t >= REPLAY;
      const iris = E.outExpo(prog(t, REPLAY, REPLAY + 0.4));
      c.R.style.clipPath = `circle(${iris * 110}% at 50% 40%)`;
      vis(c.R, rOn);
      if (rOn) this.drawReplay(t);
      // type
      putTL(c.h1.el, 108, 280, 1, 0, t < ZOOM0 - 0.1 ? 1 : 0);
      typeIn(c.h1, t, 30.25, 0.08, "rise");
      putTL(c.h2.el, 108, 440, 1, 0, t > 33.85 && t < ZOOM0 - 0.1 ? 1 : 0);
      typeIn(c.h2, t, 33.9, 0.125, "cut");
      const crumbs = t < TAP1 ? "比赛 / 10月8日 / 回合" : t < REPLAY ? "比赛 / 10月8日 / 回合 / 07" : "比赛 / 10月8日 / 回合 / 07 / ▶ 回放";
      c.crumb.textContent = crumbs; putTL(c.crumb, 112, 980, 1, 0, enter * (t < ZOOM0 ? 1 : 0));
    },
    drawReplay(t) {
      const c = this, g = c.rg, w = c.rc.width, h = c.rc.height;
      const tau = c.RTAU0 + Math.max(0, t - REPLAY - 0.15);
      g.fillStyle = C.night; g.fillRect(0, 0, w, h);
      // dark vignette lane, as the replay surround
      const cam = makeCam({ az: 0, el: 30, dist: 15.5, target: [0.8, 0, 0], focal: 1180, cx: w / 2, cy: h * 0.47 });
      drawCourt(g, cam, { line: "rgba(244,238,227,.85)", width: 1.8, surface: C.courtNight });
      const n = 22;
      g.lineCap = "round";
      for (let k = n; k >= 0; k--) {
        const a = shuttleAt(tau - (k + 1) / 30), b = shuttleAt(tau - k / 30); if (!a || !b) continue;
        const pa = cam.p(...a), pb = cam.p(...b), u = 1 - k / n;
        g.strokeStyle = u > .85 ? C.butter : u > .35 ? C.tomato : C.lilac; g.globalAlpha = Math.min(1, u * 1.6);
        g.lineWidth = 2 + 9 * u; g.beginPath(); g.moveTo(pa.x, pa.y); g.lineTo(pb.x, pb.y); g.stroke();
      }
      g.globalAlpha = 1;
      for (const s of ["far", "near"]) {
        const [x, y] = playerAt(s, tau), a = cam.p(x, y, 0), b = cam.p(x, y, 1.6), hd = cam.p(x, y, 1.82);
        g.strokeStyle = g.fillStyle = s === "near" ? C.cobalt : C.flamingo; g.lineWidth = 0.36 * a.k;
        g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke();
        g.beginPath(); g.arc(hd.x, hd.y, 0.19 * hd.k, 0, Math.PI * 2); g.fill();
      }
      const hp = shuttleAt(tau);
      if (hp) { const q = cam.p(...hp); g.fillStyle = C.butter; g.beginPath(); g.arc(q.x, q.y, 7, 0, Math.PI * 2); g.fill(); }
      // the replay's own shot label next to the most recent hit
      const last = [...RALLY.hits].reverse().find(hh => hh.t <= tau && tau - hh.t < 0.9);
      if (last && last.ok) {
        if (c._lk !== last.f) {
          const G = GLYPH[last.glyph];
          c.rlab.innerHTML = `<div style="display:flex;align-items:center;gap:6px;padding:5px 12px 5px 8px;background:${G.ink};border:2px solid ${C.ink};border-radius:99px;font:900 20px NY,'PingFang SC';color:${onInk(last.glyph)};white-space:nowrap">${glyphSVG(last.glyph, onInk(last.glyph), 22, false)}${G.zh}</div>`;
          c._lk = last.f;
        }
        const q = cam.p(...(shuttleAt(last.t + 1e-4) || [0, 0, 1]));
        put(c.rlab, q.x, Math.max(150, q.y - 46), spring(tau - last.t, 3, .45));
      } else vis(c.rlab, false);
      const shotNo = RALLY.hits.filter(hh => hh.t <= tau).length;
      c.rt.textContent = `第 ${Math.max(1, shotNo - 2)} 拍 · ${(Math.max(0, tau - c.RTAU0)).toFixed(1)} s`;
      c.rph.style.left = `${clamp((tau - c.RTAU0) / c.SPAN) * 100}%`;
    },
  });
})();
