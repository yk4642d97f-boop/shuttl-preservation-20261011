// ── S6 · 50–56 s · "拿不准的，" / "你来定。"
// An uncertain rally, a long press (0.45 s, as in the app), the correction slip, the user's call, the stamp.
(() => {
  const PRESS = 51.0, HOLD = 0.45, SLIP = 51.5, PICK = 52.5, AWAY = 52.75, STAMP = 53.5;
  const RS = 2.2, RW = 640, RH = 64;
  const RX = W / 2 - RW * RS / 2, RY = 470;
  const beads = [C.flamingo, C.cobalt, C.lilac, C.cobalt, C.butter, C.tomato, C.pistachio];
  const SS = 2.05, SW = 393, SHh = 262;
  S({
    t0: 50.0, t1: 56.0,
    build(root) {
      const c = this;
      css(root, { background: C.paper });
      c.row = el("div", "abs card", root);
      css(c.row, { width: RW + "px", height: RH + "px", borderRadius: "18px", display: "flex", alignItems: "center", gap: "12px", padding: "0 16px", boxSizing: "border-box", transformOrigin: "0 0" });
      c.row.innerHTML = `<div class="ny" style="font-size:26px;width:38px">05</div>` +
        `<div style="flex:1"><div style="height:13px">${beads.map(b => `<span class="bead" style="background:${b}"></span>`).join("")}</div>` +
        `<div style="font:500 12px 'PingFang SC';color:${C.inkSoft};margin-top:3px">7 拍 · 出界</div></div>` +
        `<span class="chipS st"></span><span class="sticker win"></span><span style="font:700 13px SFMono;color:${C.inkFaint}">›</span>`;
      c.chip = c.row.querySelector(".st"); c.win = c.row.querySelector(".win");
      c.ring = el("div", "abs", root);
      c.ring.innerHTML = `<svg width="140" height="140" viewBox="0 0 140 140" style="overflow:visible"><circle cx="70" cy="70" r="26" fill="${C.ink}" fill-opacity=".14"/>` +
        `<circle class="arc" cx="70" cy="70" r="52" fill="none" stroke="${C.tomato}" stroke-width="10" stroke-linecap="round" transform="rotate(-90 70 70)" stroke-dasharray="0 400"/></svg>`;
      c.arc = c.ring.querySelector(".arc");
      c.dim = el("div", "fill", root); css(c.dim, { background: C.ink });
      c.slip = el("div", "abs", root);
      css(c.slip, { width: SW + "px", height: SHh + "px", background: C.paper, border: `2.5px solid ${C.ink}`, borderRadius: "28px", boxSizing: "border-box", padding: "22px", transformOrigin: "50% 0" });
      const choice = (title, near, cur) => `<div class="ch ${near ? "n" : "f"}" style="position:relative;flex:1;height:76px;border-radius:16px;background:${near ? C.cobalt : C.flamingo};color:${near ? C.card : C.ink};` +
        `border:${cur ? 3 : 2}px solid ${C.ink};box-shadow:0 3px 0 ${C.ink};display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px">` +
        `<span style="font:900 20px NY,'PingFang SC'">${title}</span><span class="cap" style="font:700 11px 'PingFang SC';opacity:.8">${cur ? "AI 的判断" : ""}</span>` +
        `<span class="ok" style="position:absolute;right:-8px;top:-8px;width:22px;height:22px;border-radius:50%;background:${C.butter};border:2px solid ${C.ink};box-sizing:border-box;font:900 12px -apple-system;display:flex;align-items:center;justify-content:center;color:${C.ink};visibility:${cur ? "visible" : "hidden"}">✓</span></div>`;
      c.slip.innerHTML = `<div style="display:flex;align-items:flex-start;justify-content:space-between"><div><div class="lab" style="font-size:10px">回合 05 · 7 拍</div>` +
        `<div class="ttl" style="font-size:27px;margin-top:4px">这一分是谁的？</div></div>` +
        `<span class="sticker" style="background:${C.lilac};transform:rotate(4deg)">✦ AI 判远端 · 54%</span></div>` +
        `<div style="display:flex;gap:12px;margin-top:20px">${choice("近端得分", true, false)}${choice("远端得分", false, true)}</div>` +
        `<div style="margin-top:16px;height:50px;border-radius:25px;background:${C.card};border:2px solid ${C.ink};box-shadow:0 3px 0 ${C.ink};display:flex;align-items:center;justify-content:center;font:900 17px NY,'PingFang SC'">⊘ 这不算一分</div>`;
      c.nearBtn = c.slip.querySelector(".ch.n"); c.farBtn = c.slip.querySelector(".ch.f");
      c.seal = el("div", "abs", root, sealSVG(200, C.butter,
        `<text x="100" y="118" text-anchor="middle" font-family="PingFang SC" font-weight="600" font-size="50" fill="${C.ink}" stroke="${C.ink}" stroke-width="1.6">已改</text>`));
      c.h1 = headline(root, "拿不准的，", "zh", { fontSize: "128px", color: C.ink });
      c.h2 = headline(root, "你来定。", "zh", { fontSize: "270px", color: C.ink });
      [50.25, 50.375, 50.5, 50.625, 50.75].forEach((t, i) => cue(t, "key", { pitch: .5 + i * .25, gain: .8 }));
      cue(PRESS, "press", { dur: HOLD }); cue(PRESS + HOLD, "tick", { pitch: 1.2 });
      cue(SLIP, "sheet"); cue(PICK, "tap"); cue(AWAY, "sheet", { rev: 1 });
      cue(STAMP, "slam", { gain: 1.25 }); cue(STAMP, "stamp", { pitch: 0 }); cue(STAMP, "boom", { gain: .8 });
      [STAMP, STAMP + .125, STAMP + .25, STAMP + .375].forEach((t, i) => cue(t + 0.02, "key", { pitch: 1 + i * .2, gain: .7 }));
    },
    update(lt, t) {
      const c = this;
      const enter = spring(t - 50.0, 2.2, 0.55);
      const pressed = t > PRESS && t < PRESS + HOLD + 0.1;
      c.row.style.transform = `translate(${RX}px,${RY + (1 - enter) * 600}px) scale(${RS * (pressed ? 0.985 : 1)})`;
      c.row.style.background = pressed ? C.paperDeep : C.card;
      const fixed = t >= PICK + 0.05;
      if (fixed !== c._fixed) {
        c._fixed = fixed;
        c.chip.textContent = fixed ? "已改" : "不确定";
        css(c.chip, fixed ? { background: C.ink, color: C.paper } : { background: C.butter, color: C.ink });
        c.win.textContent = fixed ? "近端得分" : "远端得分";
        css(c.win, fixed ? { background: C.cobalt, color: C.card, transform: "rotate(2deg)" } : { background: C.flamingo, color: C.ink, transform: "rotate(2deg)" });
      }
      // long press ring
      const pu = prog(t, PRESS, PRESS + HOLD);
      c.arc.setAttribute("stroke-dasharray", `${327 * E.ioCubic(pu)} 400`);
      put(c.ring, RX + 300 * RS, RY + RH * RS / 2, 1 + 0.12 * E.outExpo(prog(t, PRESS + HOLD, PRESS + HOLD + .2)), 0, t > PRESS - 0.05 && t < SLIP + 0.1 ? 1 : 0);
      // slip
      const up = E.outExpo(prog(t, SLIP, SLIP + 0.45)), down = E.inExpo(prog(t, AWAY, AWAY + 0.35));
      const sy = lerp(H + 40, H - SHh * SS - 30, up * (1 - down));
      c.slip.style.transform = `translate(${W / 2 - SW / 2}px,${sy}px) scale(${SS})`;
      vis(c.slip, t > SLIP && t < AWAY + 0.4);
      c.dim.style.opacity = 0.16 * up * (1 - down); vis(c.dim, t > SLIP && t < AWAY + 0.4);
      const pk = t > PICK - 0.04 && t < PICK + 0.14;
      c.nearBtn.style.transform = pk ? "translateY(3px)" : ""; c.nearBtn.style.boxShadow = pk ? `0 0 0 ${C.ink}` : `0 3px 0 ${C.ink}`;
      const picked = t >= PICK;
      c.nearBtn.querySelector(".ok").style.visibility = picked ? "visible" : "hidden";
      c.farBtn.querySelector(".ok").style.visibility = picked ? "hidden" : "visible";
      c.nearBtn.querySelector(".cap").textContent = picked ? "你改的" : "";
      c.farBtn.querySelector(".cap").textContent = picked ? "" : "AI 的判断";
      // stamp
      const ds = t - STAMP;
      if (ds >= 0) {
        const s = ds < 0.07 ? lerp(2.3, 1, ds / 0.07) : 1 + wob(ds - .07, 4, 9) * 0.05;
        put(c.seal, RX + RW * RS + 20, RY - 30, s, 14);
      } else vis(c.seal, false);
      shake(t, STAMP, 34, 0.45);
      putTL(c.h1.el, 108, 92, 1, 0, 1);
      typeIn(c.h1, t, 50.25, 0.125, "cut");
      putTL(c.h2.el, 830, 690, 1, 0, t >= STAMP ? 1 : 0);
      typeIn(c.h2, t, STAMP, 0.125, "cut");
    },
  });
})();
