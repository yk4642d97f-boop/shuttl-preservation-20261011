// ── S2 · 6–14 s · "你只管打。" / "手机只管录。" / "云端，来算。"
(() => {
  // ── 2a · 6.0–8.0 · tomato. A smash comes down onto the last character.
  const IMP = 7.5, FL0 = 7.2;
  const FS = 250, TX = 96, TY = 640;
  const P = { a: [2080, -180], c: [1480, 120], b: [TX + 3 * FS * 0.955 + 128, TY + 30] };
  const bez = u => [(1 - u) ** 2 * P.a[0] + 2 * u * (1 - u) * P.c[0] + u * u * P.b[0], (1 - u) ** 2 * P.a[1] + 2 * u * (1 - u) * P.c[1] + u * u * P.b[1]];
  S({
    t0: 6.0, t1: 8.0,
    build(root) {
      const c = this;
      css(root, { background: C.tomato });
      c.h = headline(root, "你只管打。", "zh", { fontSize: FS + "px", color: C.ink });
      c.cv = canvas(root); c.g = c.cv.getContext("2d");
      c.fol = el("div", "abs mono", root, "PLAY"); css(c.fol, { fontSize: "18px", color: C.ink });
      cue(6.0, "slam", { gain: 1.1 });
      for (let i = 1; i < 5; i++) cue(6.0 + i * 0.125, "key", { pitch: 1 + i * .4, gain: .8 });
      cue(FL0 - 0.05, "whoosh", { dur: 0.36 }); cue(IMP, "thwack", { pitch: 1.2, gain: 1.2 }); cue(IMP, "boom", { gain: .9 });
    },
    update(lt, t) {
      const c = this, g = c.g;
      putTL(c.h.el, TX, TY);
      typeIn(c.h, t, 6.0, 0.125, "cut");
      // the struck character reels and settles
      const d = c.h.chars[3], dt = t - IMP;
      if (dt > 0) d.style.transform = `translateY(${wob(dt, 3, 6) * -8 + Math.exp(-dt * 9) * 6}%) rotate(${wob(dt, 2.6, 5) * 9}deg)`;
      putTL(c.fol, 100, 80);
      shake(t, IMP, 30, 0.45);
      g.clearRect(0, 0, W, H);
      const uh = E.inSine(prog(t, FL0, IMP));
      const ut = t < IMP ? Math.max(0, uh - 0.55) : lerp(0.45, 1, E.outCubic(prog(t, IMP, IMP + 0.3)));
      if (t > FL0 && ut < uh - 0.002) {
        g.lineCap = "round"; g.strokeStyle = C.ink;
        const n = 36;
        for (let i = 0; i < n; i++) {
          const k0 = i / n, k1 = (i + 1) / n, a = bez(lerp(ut, uh, k0)), b = bez(lerp(ut, uh, k1));
          g.lineWidth = 3 + 46 * Math.pow(k1, 1.4);
          g.beginPath(); g.moveTo(...a); g.lineTo(...b); g.stroke();
        }
      }
      if (t > IMP && t < IMP + 0.28) {   // ink burst
        const u = E.outExpo(prog(t, IMP, IMP + 0.28)), [x, y] = P.b;
        g.strokeStyle = C.ink; g.lineWidth = 12 * (1 - u) + 2;
        for (let k = 0; k < 9; k++) {
          const a = -Math.PI * (0.05 + 0.9 * k / 8), r0 = 70 + 60 * u, r1 = r0 + 90 * (1 - u * .6);
          g.beginPath(); g.moveTo(x + Math.cos(a) * r0, y + Math.sin(a) * r0); g.lineTo(x + Math.cos(a) * r1, y + Math.sin(a) * r1); g.stroke();
        }
      }
    },
  });

  // ── 2b + 2c · 8.0–14.0 · the phone records; its picture breaks into packets that rise into the cloud.
  const PW = 980, PH = 470, PX = 1250, PY = 480, BEZ = 22;
  const SW = PW - 2 * BEZ, SH = PH - 2 * BEZ;
  const SX = PX - SW / 2, SY = PY - SH / 2;
  const LIFT = 10.5, NIGHT0 = 10.55, NIGHT1 = 11.2;
  const GC = 36, GR = 8, CELL = 30, GAP = 10, GX = (W - (GC * (CELL + GAP) - GAP)) / 2, GY = 150;
  const COLS = 24, ROWS = 12, TW = SW / COLS, TH = SH / ROWS;
  const STAGES = ["TRACK", "COURT", "PLAYERS", "HITS", "STROKES", "RALLIES", "SCORE"];
  const COLLAPSE = 13.62;
  const tiles = [];
  for (let j = 0; j < ROWS; j++) for (let i = 0; i < COLS; i++) {
    const k = j * COLS + i;
    tiles.push({ i, j, k, go: LIFT + 0.12 + (i / COLS) * 0.42 + hash(k * 1.3) * 0.18, gi: k % GC, gj: Math.floor(k / GC) });
  }
  const cellPos = (gi, gj) => [GX + gi * (CELL + GAP), GY + gj * (CELL + GAP)];
  const SPOT = [C.lilac, C.pistachio, C.butter, C.tomato, C.paper, C.cobalt, C.flamingo];
  S({
    t0: 8.0, t1: 14.0,
    build(root) {
      const c = this;
      css(root, { background: C.paper });
      c.scr = document.createElement("canvas"); c.scr.width = SW; c.scr.height = SH; c.sg = c.scr.getContext("2d");
      c.svg = sv("svg", { width: W, height: H, class: "abs" }, root);
      c.tri = sv("g", {}, c.svg);
      const legs = [[PX, PY + PH / 2 + 30, PX - 190, 1040], [PX, PY + PH / 2 + 30, PX + 190, 1040], [PX, PY + PH / 2 + 30, PX + 10, 1060]];
      c.legs = legs.map(l => sv("line", { x1: l[0], y1: l[1], x2: l[2], y2: l[3], stroke: C.ink, "stroke-width": 12, "stroke-linecap": "round" }, c.tri));
      c.head = sv("rect", { x: PX - 60, y: PY + PH / 2 - 4, width: 120, height: 40, rx: 10, fill: C.ink }, c.tri);
      c.body = sv("rect", { x: PX - PW / 2, y: PY - PH / 2, width: PW, height: PH, rx: 78, fill: "none", stroke: C.ink, "stroke-width": 14 }, c.svg);
      c.bodyLen = 2 * (PW + PH);
      c.cvScr = el("canvas", "abs", root); c.cvScr.width = SW; c.cvScr.height = SH;
      c.isl = el("div", "abs", root); css(c.isl, { width: "40px", height: "140px", borderRadius: "20px", background: C.paper });
      c.fx = canvas(root); c.g = c.fx.getContext("2d");
      c.h1 = headline(root, "手机只管录。", "zh", { fontSize: "120px", color: C.ink });
      c.h2 = headline(root, "云端，来算。", "zh", { fontSize: "150px", color: C.paper });
      c.lab = el("div", "abs mono", root, ""); css(c.lab, { fontSize: "18px", color: C.paper });
      c.st = STAGES.map(s => { const e = el("div", "abs mono", root, s); css(e, { fontSize: "20px", color: C.paper }); return e; });
      cue(8.0, "pen", { dur: 0.45 }); cue(8.0, "kick", { gain: .9 });
      [8.25, 8.33, 8.41, 8.49, 8.57, 8.65].forEach((t, i) => cue(t, "key", { pitch: .3 + i * .15, gain: .55 }));
      cue(8.5, "rec");
      cue(LIFT, "drop"); cue(LIFT + 0.1, "packets", { dur: 1.05 });
      [11.5, 11.625, 11.75, 12.0, 12.125, 12.25].forEach((t, i) => cue(t, "key", { pitch: 2 + (i % 3) * .5, gain: .9 }));
      STAGES.forEach((s, i) => cue(12.25 + i * 0.25, "ok", { pitch: i }));
      cue(COLLAPSE - 0.05, "suck", { dur: 0.36 }); cue(13.97, "pop", { pitch: .9 });
    },
    drawScreen(t) {
      const g = this.sg;
      g.fillStyle = C.night; g.fillRect(0, 0, SW, SH);
      const cam = makeCam({ az: 0, el: 17, dist: 17.5, target: [0.6, 0, 0], focal: 760, cx: SW / 2, cy: SH * 0.56 });
      drawCourt(g, cam, { line: "rgba(244,238,227,.85)", width: 1.6, surface: C.courtNight });
      const tau = 2.1 + ((t - 8.2) % 6);                 // a few real shots play on the viewfinder
      g.lineCap = "round";
      for (let k = 0; k < 14; k++) {
        const p = shuttleAt(tau - k / 30); if (!p) continue;
        const q = cam.p(...p);
        g.fillStyle = k === 0 ? C.butter : `rgba(242,84,45,${1 - k / 14})`;
        g.beginPath(); g.arc(q.x, q.y, k === 0 ? 4 : 2.6, 0, Math.PI * 2); g.fill();
      }
      for (const s of ["near", "far"]) {
        const [x, y] = playerAt(s, tau), a = cam.p(x, y, 0), b = cam.p(x, y, 1.7);
        g.strokeStyle = s === "near" ? C.cobalt : C.flamingo; g.lineWidth = Math.max(4, a.k * 0.032);
        g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke();
      }
      const on = Math.floor((t - 8.5) * 2) % 2 === 0;
      if (t > 8.5 && on) { g.fillStyle = C.tomato; g.beginPath(); g.arc(38, 36, 11, 0, Math.PI * 2); g.fill(); }
      g.fillStyle = C.paper; g.font = "700 17px SFMono"; g.textBaseline = "middle";
      const s = Math.max(0, t - 8.5);
      g.fillText("REC  00:00:" + String(Math.floor(s)).padStart(2, "0") + ":" + String(Math.floor((s % 1) * 60)).padStart(2, "0"), 60, 37);
      g.fillText("1080P · 60", SW - 150, 37);
    },
    update(lt, t) {
      const c = this, g = c.g;
      const draw = E.ioCubic(prog(t, 8.0, 8.45));
      const fall = E.inCubic(prog(t, LIFT, LIFT + 0.45)) * 900;
      c.body.setAttribute("stroke-dasharray", `${c.bodyLen * draw} ${c.bodyLen}`);
      c.body.setAttribute("transform", `translate(0 ${fall})`);
      c.tri.setAttribute("transform", `translate(0 ${fall})`);
      c.legs.forEach((l, i) => { const u = E.outExpo(prog(t, 8.15 + i * .06, 8.6 + i * .06)); l.setAttribute("stroke-dasharray", `${600 * u} 700`); });
      c.head.style.opacity = t > 8.2 ? 1 : 0;
      vis(c.svg, t < LIFT + 0.5);
      // live viewfinder until the lift, then frozen as the picture that gets sent
      if (t < LIFT) c.drawScreen(t);
      else if (!c._frozen) { c.drawScreen(LIFT); c._frozen = true; }
      if (t < LIFT) c._frozen = false;
      const scrOn = prog(t, 8.3, 8.5);
      c.cvScr.getContext("2d").drawImage(c.scr, 0, 0);
      putTL(c.cvScr, SX, SY, 1, 0, t < LIFT ? scrOn : 0);
      putTL(c.isl, PX + PW / 2 - BEZ - 6, PY - 70, 1, 0, 0);
      putTL(c.h1.el, 108, 92, 1, 0, t < LIFT ? 1 : 0);
      typeIn(c.h1, t, 8.25, 0.08, "rise", [LIFT - 0.3, "fall", 0.02]);

      // ── cloud
      g.clearRect(0, 0, W, H);
      const nb = H * E.ioExpo(prog(t, NIGHT0, NIGHT1));
      if (t >= NIGHT0) { g.fillStyle = C.night; g.fillRect(0, 0, W, nb); }
      if (t >= LIFT) {
        const col = (t - COLLAPSE) >= 0 ? E.inExpo(prog(t, COLLAPSE, 13.95)) : 0;
        for (const tl of tiles) {
          const u = E.outExpo(prog(t, tl.go, tl.go + 0.62));
          const [cx0, cy0] = [SX + tl.i * TW, SY + tl.j * TH];
          let [gx, gy] = cellPos(tl.gi, tl.gj);
          let x = lerp(cx0, gx, u), y = lerp(cy0, gy, u) - Math.sin(u * Math.PI) * 120;
          let w = lerp(TW, CELL, u), h = lerp(TH, CELL, u);
          if (col > 0) { x = lerp(x, W / 2 - 2, col); y = lerp(y, 540 - 2, col); w = h = lerp(CELL, 4, col); }
          if (u < 0.85) g.drawImage(c.scr, tl.i * TW, tl.j * TH, TW, TH, x, y, w, h);
          if (u >= 0.6) {
            // arrived: the packet becomes a compute cell, flickering as the job runs
            const fr = Math.floor(t * 15), busy = clamp((t - 11.3) / 1.2) * (1 - prog(t, 13.3, COLLAPSE));
            const scan = Math.abs(tl.gi - ((t - 11.3) * 30) % GC) < 1.5;
            const lit = hash(tl.k * 7.1 + fr * 1.37) < 0.18 + 0.5 * busy || scan;
            g.globalAlpha = clamp((u - 0.6) / 0.25);
            g.fillStyle = col > 0 ? C.paper : lit && t > 11.3 ? SPOT[Math.floor(hash(tl.k + fr * 3.3) * SPOT.length)] : C.nightRaised;
            g.fillRect(x, y, w, h);
            g.globalAlpha = 1;
          }
        }
        // upload → analysis bar
        const barY = GY + GR * (CELL + GAP) + 26, bw = GC * (CELL + GAP) - GAP;
        const up = E.ioCubic(prog(t, 10.8, 12.15));
        if (t < COLLAPSE && t > 10.75) {
          g.fillStyle = "rgba(244,238,227,.18)"; g.fillRect(GX, barY, bw, 6);
          g.fillStyle = C.paper; g.fillRect(GX, barY, bw * up, 6);
          if (t > 12.15) { g.fillStyle = C.pistachio; g.fillRect(GX, barY, bw * clamp((t - 12.15) / 1.5), 6); }
        }
        c.lab.textContent = t < 12.15 ? `↑ UPLOAD  ${String(Math.round(up * 100)).padStart(3, " ")}%` : "GPU · ANALYSIS";
        putTL(c.lab, GX, barY + 22, 1, 0, t > 10.8 && t < COLLAPSE ? 1 : 0);
        c.st.forEach((e, i) => {
          const tk = 12.25 + i * 0.25;
          e.innerHTML = (t >= tk ? `<span style="color:${C.pistachio}">●</span> ` : `<span style="opacity:.35">○</span> `) + STAGES[i];
          putTL(e, 1420, 640 + i * 44, 1, 0, t > 12.05 && t < COLLAPSE ? 1 : 0);
        });
        if (t > 13.95) { g.fillStyle = C.paper; g.beginPath(); g.arc(W / 2, 540, 5, 0, Math.PI * 2); g.fill(); }
      }
      putTL(c.h2.el, 108, 700, 1, 0, t < 13.5 ? 1 : 0);
      typeIn(c.h2, t, 11.5, 0.125, "cut");
      c.h2.chars.forEach((ch, i) => { if (i >= 3) ch.style.opacity = t >= 12.0 + (i - 3) * 0.125 ? 1 : 0; });
    },
  });
})();
