// ── S8 · 06 记分 (53.4 – 59.4 s): the scorecard, one unsure point, a tap to fix it.
const SPARK = `<svg width="30" height="30" viewBox="0 0 30 30"><path d="M15 2 C16 11 19 14 28 15 C19 16 16 19 15 28 C14 19 11 16 2 15 C11 14 14 11 15 2Z" fill="#221B2E"/></svg>`;
const CHECK = `<svg width="34" height="34" viewBox="0 0 30 30"><path d="M6 16 L12 22 L24 8" fill="none" stroke="#F7D95C" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
S({
  t0: 53.4, t1: 59.4, z: 32,
  build(root) {
    const c = this;
    c.chap = el("div", "chap abs", root, "<b>06</b>记分");
    c.h = headline(root, "自动记分，\n点一下就能改。");
    c.card = css(el("div", "card abs", root), { width: "920px", padding: "38px 44px 18px", boxSizing: "border-box" });
    el("div", "", c.card, "回合记分卡").style.cssText = "font:600 50px 'PingFang SC';-webkit-text-stroke:1.2px var(--ink)";
    el("div", "body", c.card, "有 1 分 AI 不太确定 · 点一下就能改").style.cssText = "font-size:32px;color:var(--inkSoft);margin:6px 0 10px";
    const R = [["01", "smash clear drop net lift smash", "6 拍 · 出界", ["近端得分", "cobalt", "card"]],
      ["02", "serve net lift smash block", "5 拍 · 界内", ["不确定", "butter", "ink"]],
      ["03", "serve clear clear drop net lift smash kill", "8 拍 · 界内", ["远端得分", "flamingo", "ink"]]];
    c.rows = R.map(([n, dots, sub, [pl, bg, fg]]) => {
      const r = el("div", "", c.card); r.style.cssText = "display:flex;align-items:center;gap:28px;height:128px;border-top:3px solid rgba(34,27,46,.12)";
      el("div", "", r, n).style.cssText = "font:900 64px NY;width:92px";
      const mid = el("div", "", r); mid.style.cssText = "flex:1";
      const dr = el("div", "", mid); dr.style.cssText = "display:flex;gap:8px";
      for (const k of dots.split(" ")) el("div", "", dr).style.cssText = `width:26px;height:26px;border-radius:50%;border:3px solid #221B2E;background:${SHOT[k][1]}`;
      el("div", "chap", mid, sub).style.cssText = "font:700 26px SFMono;letter-spacing:2px;color:var(--inkSoft);margin-top:8px";
      const pw = el("div", "", r); pw.style.cssText = "position:relative;width:250px;height:70px";
      const p = css(el("div", "pill abs", pw, pl), { background: `var(--${bg})`, color: `var(--${fg})`, left: "50%", top: "50%", transform: "translate(-50%,-50%)" });
      return { r, pw, p };
    });
    const p2 = c.rows[1];
    p2.fix = css(el("div", "pill abs", p2.pw, "远端得分<span style='margin-left:10px;font-size:24px;background:#221B2E;color:#FFFBF4;border-radius:10px;padding:2px 10px'>已改</span>"), { background: "var(--flamingo)", left: "50%", top: "50%" });
    p2.ring = css(el("div", "abs", p2.pw), { width: "120px", height: "120px", borderRadius: "50%", border: "6px solid var(--ink)", left: "65px", top: "-25px", boxSizing: "border-box" });
    c.seal = el("div", "abs", root, `<svg width="170" height="170" viewBox="0 0 100 100"><path d="${scallop(50, 50, 47, 42, 16)}" fill="#F7D95C" stroke="#221B2E" stroke-width="3"/><circle cx="50" cy="50" r="33" fill="none" stroke="#221B2E" stroke-opacity=".35" stroke-dasharray="2 2.5"/><text x="50" y="40" text-anchor="middle" font-family="PingFang SC" font-weight="600" font-size="16" fill="#221B2E">已改</text><text x="50" y="72" text-anchor="middle" font-family="NY" font-weight="900" font-size="34" fill="#221B2E">1</text></svg>`);
    c.dim = css(el("div", "abs", root), { width: W + "px", height: H + "px", background: "rgba(34,27,46,.3)" });
    c.sheet = css(el("div", "abs", root), { width: W + "px", height: "900px", background: "var(--card)", borderRadius: "64px 64px 0 0", border: "5px solid var(--ink)", boxSizing: "border-box", padding: "34px 70px" });
    el("div", "", c.sheet).style.cssText = "width:110px;height:12px;border-radius:6px;background:var(--paperDeep);margin:0 auto 44px";
    el("div", "chap", c.sheet, "回合 02 · 5 拍").style.fontSize = "30px";
    el("div", "", c.sheet, "这一分是谁的？").style.cssText = "font:600 80px 'PingFang SC';-webkit-text-stroke:2px var(--ink);margin:10px 0 46px";
    css(el("div", "sticker abs", c.sheet, SPARK + "AI 判近端 · 52%"), { background: "var(--lilac)", fontSize: "34px", right: "70px", left: "auto", top: "100px", transform: "rotate(4deg)" });
    const bw = el("div", "", c.sheet); bw.style.cssText = "position:relative;display:flex;gap:30px";
    const btn = (txt, sub, bg, fg) => { const b = el("div", "", bw, `<div>${txt}</div>${sub ? `<div style="font:500 30px 'PingFang SC';-webkit-text-stroke:0;opacity:.85">${sub}</div>` : ""}`); b.style.cssText = `position:relative;overflow:hidden;flex:1;height:190px;border-radius:44px;border:5px solid #221B2E;box-shadow:0 10px 0 #221B2E;background:${bg};color:${fg};display:flex;flex-direction:column;align-items:center;justify-content:center;font:600 60px 'PingFang SC';-webkit-text-stroke:1.5px ${fg}`; return b; };
    c.bNear = btn("近端得分", "AI 的判断", "#2F4BDE", "#FFFBF4"); c.bFar = btn("远端得分", "", "#FF7AB6", "#221B2E");
    c.rip = css(el("div", "abs", c.bFar), { width: "600px", height: "600px", borderRadius: "50%", background: "rgba(34,27,46,.22)", left: "-50px", top: "-200px" });
    c.badge = css(el("div", "abs", bw, CHECK), { width: "76px", height: "76px", borderRadius: "50%", background: "var(--ink)", border: "4px solid var(--card)", display: "flex", alignItems: "center", justifyContent: "center", top: "-26px" });
    el("div", "", c.sheet, "⃠ 这不算一分").style.cssText = "margin-top:44px;height:120px;border-radius:60px;border:5px solid #221B2E;display:flex;align-items:center;justify-content:center;font:600 46px 'PingFang SC';box-shadow:0 8px 0 #221B2E";
    cue(54.2, "rise", { gain: .4, dur: .35 }); [54.4, 54.55, 54.7].forEach((x, i) => cue(x, "tick", { pitch: .3 + i * .2 }));
    cue(54.85, "tap", { gain: .8 }); cue(55.0, "sheet", { gain: .6 }); cue(56.1, "tap", { gain: 1 }); cue(56.15, "pop", { pitch: .7 });
    cue(56.7, "sheet", { gain: .45, rev: 1 }); cue(57.0, "pop", { pitch: .9 }); cue(57.2, "stamp", { gain: 1 });
    cue(57.4, "boing", { gain: .45 }); cue(59.0, "whoosh", { gain: .6, dur: .45 });
    BUBBLES.add(57.6, 58.95, "它认错，\n比你搭档还快。", "l");
  },
  update(lt, t) {
    const c = this, ox = W * (1 - E.ioCubic(prog(t, 53.4, 53.8))) - W * E.ioCubic(prog(t, 59.0, 59.4));
    this.root.style.transform = ox ? `translateX(${ox}px)` : "";
    putTL(c.chap, 80, 150, 1, 0, clamp((t - 53.75) * 5));
    putTL(c.h.el, 80, 200); popChars(c.h, t, 53.85, 0.045);
    const cs = spring(t - 54.2, 1.9, 0.5); putTL(c.card, 80, 520 + (1 - cs) * 300, 1, 0, clamp(cs * 2));
    c.rows.forEach(({ r }, i) => { const s = spring(t - 54.4 - i * 0.15, 2.6, 0.45); r.style.opacity = clamp(s * 3); r.style.transform = `translateX(${(1 - s) * 50}px)`; });
    const p2 = c.rows[1], fx = t >= 57.0;
    p2.p.style.transform = `translate(-50%,-50%) scale(${1 + (t > 54.75 && t < 55.1 ? 0.08 * Math.sin((t - 54.75) * 30) : 0)})`;
    p2.p.style.opacity = fx ? 0 : 1;
    p2.fix.style.opacity = fx ? 1 : 0; p2.fix.style.transform = `translate(-50%,-50%) scale(${1 + (fx ? wob(t - 57.0, 3, 6) * 0.25 : 0)})`;
    const ru = prog(t, 54.85, 55.25); p2.ring.style.opacity = ru > 0 && ru < 1 ? 1 - ru : 0; p2.ring.style.transform = `scale(${0.3 + ru})`;
    const ss = spring(t - 57.2, 3, 0.35); put(c.seal, 930, 540, lerp(1.9, 1, ss), 12, clamp(ss * 4));
    const open = spring(t - 55.0, 1.8, 0.55) - spring(t - 56.7, 1.6, 0.8);
    c.sheet.style.transform = `translateY(${lerp(1940, 1100, clamp(open))}px)`;
    c.sheet.style.visibility = open < 0.005 ? "hidden" : "visible";
    c.dim.style.opacity = clamp(open) * 1; c.dim.style.visibility = open < 0.005 ? "hidden" : "visible";
    const bx = lerp(386, 861, spring(t - 56.15, 2.6, 0.45));
    c.badge.style.transform = `translateX(${bx}px) scale(${1 + wob(t - 56.15, 3, 6) * 0.3})`;
    c.bFar.style.transform = `scale(${1 - 0.05 * Math.sin(Math.PI * clamp((t - 56.1) / 0.18))})`;
    const rp = prog(t, 56.1, 56.5); c.rip.style.opacity = rp > 0 && rp < 1 ? 1 - rp : 0; c.rip.style.transform = `scale(${0.1 + rp})`;
  },
  pose(lt, t) {
    if (t < 57.35) return { hidden: true };
    const I = idle(t, 8.3), h = hop(t, 57.35, 57.75, { x: 1250, y: 1500 }, S8M, 200);
    if (t < 57.75) return Object.assign(h, { s: 0.95, mood: "happy" });
    return Object.assign(I, { x: S8M.x, y: S8M.y, s: 0.95, sq: I.sq + h.sq, mood: "smug", lx: -0.8, ly: -0.8 });
  },
});
