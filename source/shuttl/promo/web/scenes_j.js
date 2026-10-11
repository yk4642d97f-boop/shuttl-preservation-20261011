// ── S9 · 07 统计 (59.0 – 64.35 s) and S10 · 08 细节 (63.95 – 68.4 s)
const S9M = { x: 890, y: 1800 }, S10M = { x: 890, y: 1800 };
const HIST = [8, 54, 66, 34, 35, 35, 28, 24, 12, 11, 14, 10, 5, 11];
S({
  t0: 59.0, t1: 64.35, z: 33,
  build(root) {
    const c = this;
    c.chap = el("div", "chap abs", root, "<b>07</b>统计");
    c.h = headline(root, "每一场，都算数。");
    c.hero = css(el("div", "card abs", root), { width: "920px", height: "500px", background: "var(--pistachio)", overflow: "hidden" });
    css(el("div", "abs", c.hero), { width: "920px", height: "500px", backgroundImage: "radial-gradient(rgba(34,27,46,.16) 2.4px, transparent 3px)", backgroundSize: "20px 20px", webkitMaskImage: "linear-gradient(200deg, #000 5%, transparent 45%)" });
    css(el("div", "abs body", c.hero, "生涯最高球速"), { left: "56px", top: "50px", fontSize: "42px", fontWeight: 600 });
    c.big = css(el("div", "num abs", c.hero), { left: "50px", top: "100px", fontSize: "280px" });
    c.u = css(el("div", "unit abs", c.hero, "km/h"), { left: "560px", top: "262px", fontSize: "92px" });
    c.cmp = css(el("div", "abs body", c.hero, "比一辆高铁出站还快一点"), { left: "56px", top: "400px", fontSize: "44px", fontWeight: 600 });
    c.seal = el("div", "abs", root, `<svg width="180" height="180" viewBox="0 0 100 100"><path d="${scallop(50, 50, 47, 42, 16)}" fill="#F7D95C" stroke="#221B2E" stroke-width="3"/><circle cx="50" cy="50" r="33" fill="none" stroke="#221B2E" stroke-opacity=".35" stroke-dasharray="2 2.5"/><text x="50" y="40" text-anchor="middle" font-family="PingFang SC" font-weight="600" font-size="16" fill="#221B2E">扣杀</text><text x="50" y="72" text-anchor="middle" font-family="NY" font-weight="900" font-size="32" fill="#221B2E">72</text></svg>`);
    c.trio = css(el("div", "card abs", root), { width: "920px", height: "200px", display: "flex", alignItems: "center", boxShadow: "none", border: "3px solid rgba(34,27,46,.2)" });
    c.tn = [[3, "场比赛"], [43, "回合"], [344, "击球"]].map(([v, l], i) => {
      const b = el("div", "", c.trio); b.style.cssText = `flex:1;padding-left:50px;${i ? "border-left:3px solid rgba(34,27,46,.14)" : ""}`;
      const n = el("div", "num", b); n.style.fontSize = "92px";
      el("div", "", b, l).style.cssText = "font:600 32px 'PingFang SC';color:var(--inkSoft)";
      return { n, v };
    });
    c.hist = css(el("div", "card abs", root), { width: "920px", height: "340px", boxShadow: "none", border: "3px solid rgba(34,27,46,.2)" });
    css(el("div", "abs", c.hist, "<b style='color:#BE3417;font:700 28px SFMono;margin-right:16px'>01</b>球速分布"), { left: "44px", top: "30px", font: "600 44px 'PingFang SC'" });
    c.bars = HIST.map((v, i) => css(el("div", "abs", c.hist), { left: 60 + i * 57 + "px", top: "auto", bottom: "56px", width: "46px", height: v * 2.8 + "px", borderRadius: "8px 8px 0 0", background: i < 4 ? "var(--lilac)" : i < 8 ? "var(--ink)" : "var(--tomato)", transformOrigin: "50% 100%" }));
    css(el("div", "abs", c.hist), { left: "44px", right: "44px", top: "auto", bottom: "54px", height: "3px", background: "var(--ink)" });
    c.avg = css(el("div", "abs", c.hist), { left: "318px", top: "auto", bottom: "56px", width: "0", height: "196px", borderLeft: "4px dashed var(--ink)" });
    c.avgP = css(el("div", "pill abs", c.hist, "平均 126"), { left: "262px", top: "70px", background: "var(--butter)", fontSize: "30px", padding: "4px 18px" });
    ["0", "100", "200", "300"].forEach((s, i) => css(el("div", "abs mono", c.hist, s), { left: 50 + i * 228 + "px", top: "auto", bottom: "12px", fontSize: "24px", letterSpacing: "1px", color: "var(--inkSoft)" }));
    cue(59.9, "rise", { gain: .4, dur: .35 }); cue(60.1, "ratchet", { dur: .6, gain: .5 }); cue(60.7, "pop", { pitch: .8 }); cue(60.9, "stamp", { gain: .9 });
    cue(61.2, "ratchet", { dur: .45, gain: .3 }); HIST.forEach((_, i) => i % 2 || cue(61.7 + i * 0.045, "tick", { pitch: .2 + i * .05, gain: .45 }));
    cue(62.5, "pop", { pitch: .6 }); cue(62.65, "boing", { gain: .45 }); cue(63.95, "whoosh", { gain: .6, dur: .45 });
    BUBBLES.add(62.85, 63.95, "350？被这么打，\n我可太疼了。", "l");
  },
  update(lt, t) {
    const c = this, ox = W * (1 - E.ioCubic(prog(t, 59.0, 59.4))), oy = -H * E.ioCubic(prog(t, 63.95, 64.35));
    this.root.style.transform = `translate(${ox}px,${oy}px)`;
    putTL(c.chap, 80, 150, 1, 0, clamp((t - 59.35) * 5));
    putTL(c.h.el, 80, 200); popChars(c.h, t, 59.45, 0.045);
    const hs = spring(t - 59.85, 1.9, 0.5); putTL(c.hero, 80, 390 + (1 - hs) * 300, 1, 0, clamp(hs * 2));
    c.big.textContent = Math.round(350 * E.outCubic(prog(t, 60.1, 60.7)));
    const us = spring(t - 60.7, 2.8, 0.4); c.u.style.transform = `scale(${us})`; c.u.style.opacity = clamp(us * 3);
    c.cmp.style.opacity = clamp((t - 60.8) * 4);
    const ss = spring(t - 60.9, 3, 0.35); put(c.seal, 890, 450, lerp(1.9, 1, ss), 10, clamp(ss * 4));
    const ts = spring(t - 61.1, 2, 0.5); putTL(c.trio, 80, 910 + (1 - ts) * 200, 1, 0, clamp(ts * 2));
    c.tn.forEach(({ n, v }, i) => n.textContent = Math.round(v * E.outCubic(prog(t, 61.2 + i * 0.05, 61.65 + i * 0.05))));
    const hi = spring(t - 61.5, 2, 0.5); putTL(c.hist, 80, 1130 + (1 - hi) * 200, 1, 0, clamp(hi * 2));
    c.bars.forEach((b, i) => b.style.transform = `scaleY(${clamp(spring(t - 61.7 - i * 0.045, 2.4, 0.45), 0, 1.3)})`);
    c.avg.style.opacity = clamp((t - 62.4) * 5); c.avg.style.transform = `scaleY(${E.outCubic(prog(t, 62.4, 62.7))})`; c.avg.style.transformOrigin = "0 100%";
    const ap = spring(t - 62.5, 3, 0.4); c.avgP.style.transform = `scale(${ap}) rotate(-3deg)`; c.avgP.style.opacity = clamp(ap * 3);
  },
  pose(lt, t) {
    if (t < 62.6) return { hidden: true };
    const I = idle(t, 9.4), h = hop(t, 62.6, 62.95, { x: 1250, y: 1650 }, S9M, 180);
    if (t < 62.95) return Object.assign(h, { s: 0.9, mood: "wow" });
    return Object.assign(I, { x: S9M.x, y: S9M.y, s: 0.9, sq: I.sq + h.sq, mood: "wow", lx: -0.8, ly: -0.8 });
  },
});

const DETAIL = [["手机发烫了？它会先歇一歇", "butter", -3, 0], ["空间快满了，开拍前就提醒你", "card", 2, 40], ["锁屏不丢进度，回来接着算", "lilac", -2, 10],
  ["认不出球场？手标四个角就行", "pistachio", 3, 60], ["单打双打，都会记分", "flamingo", -3, 20], ["拿不准的分，会先问你", "card", 2, 50]];
S({
  t0: 63.95, t1: 68.4, z: 34,
  build(root) {
    const c = this;
    c.chap = el("div", "chap abs", root, "<b>08</b>细节");
    c.h = headline(root, "这些小事，\n它也替你想了。");
    c.st = DETAIL.map(([s, bg]) => css(el("div", "sticker abs", root, `<span style="width:22px;height:22px;border-radius:50%;background:var(--ink);display:inline-block"></span>${s}`), { background: `var(--${bg})`, fontSize: "44px", padding: "18px 34px" }));
    DETAIL.forEach((_, i) => cue(64.55 + i * 0.3, "stamp", { gain: .6, pitch: .2 + i * .12 }));
    cue(67.95, "whoosh", { gain: .8, dur: .5 });
  },
  update(lt, t) {
    const c = this, oy = H * (1 - E.ioCubic(prog(t, 63.95, 64.35)));
    this.root.style.transform = oy ? `translateY(${oy}px)` : "";
    const bl = prog(t, 67.95, 68.35), out = E.inCubic(bl);
    putTL(c.chap, 80, 150 - out * 300, 1, 0, clamp((t - 64.3) * 5) * (1 - bl));
    putTL(c.h.el, 80 - out * 200, 200 - out * 300, 1, -out * 12, 1 - bl); popChars(c.h, t, 64.35, 0.045);
    c.st.forEach((e, i) => {
      const p = 64.55 + i * 0.3, s = spring(t - p, 3, 0.36), [, , r, dx] = DETAIL[i], a = hash(i * 3) * 2 * Math.PI;
      putTL(e, 80 + dx + Math.cos(a) * out * 1500, 540 + i * 190 + Math.sin(a) * out * 1500 - out * 400, lerp(1.6, 1, s), r + out * (hash(i) - 0.5) * 300, clamp((t - p) * 8));
    });
  },
  pose(lt, t) {
    const I = idle(t, 10.5);
    if (t < 64.55) return Object.assign(hop(t, 63.97, 64.4, { x: S9M.x, y: S9M.y - H * 0.4 }, S10M, 240), { s: 0.9, mood: "happy" });
    const k = Math.floor((t - 64.55) / 0.3), b = t - 64.55 - k * 0.3, bounce = k < 6 ? Math.sin(Math.PI * clamp(b / 0.22)) * 40 : 0;
    return Object.assign(I, { x: S10M.x, y: S10M.y - bounce, s: 0.9, sq: I.sq + (k < 6 && b > 0.22 ? wob(b - 0.22, 4, 9) * 0.2 : 0), mood: "happy", lx: -0.7, ly: -1 });
  },
});
