// ── S3 · 02 分析 (19.95 – 26.45 s): everything on this phone — no network, no upload, no login.
const S3M = { x: 200, y: 1745 };
const SLASH = c => `<svg width="40" height="40" viewBox="0 0 40 40"><circle cx="20" cy="20" r="16" fill="none" stroke="${c}" stroke-width="5"/><path d="M9 31 L31 9" stroke="${c}" stroke-width="5" stroke-linecap="round"/></svg>`;
S({
  t0: 19.95, t1: 26.45, z: 26,
  build(root) {
    const c = this;
    c.chap = el("div", "chap abs", root, "<b>02</b>分析");
    c.h = headline(root, "全在这台手机上算。"); c.h.el.style.fontSize = "100px";
    c.nos = css(el("div", "abs", root), { display: "flex", gap: "20px" });
    c.noEls = ["不联网", "不上传", "不用登录"].map(s => css(el("div", "sticker", c.nos, SLASH("#BE3417") + s), { background: "var(--card)", fontSize: "42px" }));
    c.card = css(el("div", "card abs", root), { width: "920px", padding: "44px 48px 40px", boxSizing: "border-box", background: "var(--lilac)" });
    const hd = el("div", "", c.card); hd.style.cssText = "display:flex;gap:30px;align-items:flex-start";
    c.seal = el("div", "", hd, `<svg width="120" height="120" viewBox="0 0 100 100"><path d="${scallop(50, 50, 44, 38, 14)}" fill="#FFFBF4" stroke="#221B2E" stroke-width="3.5"/><path d="M50 26 C52 42 58 48 74 50 C58 52 52 58 50 74 C48 58 42 52 26 50 C42 48 48 42 50 26Z" fill="#8C8397"/></svg>`);
    const tx = el("div", "", hd);
    el("div", "", tx, "正在这台手机上分析").style.cssText = "font:600 52px 'PingFang SC';-webkit-text-stroke:1.4px var(--ink);margin-top:4px";
    el("div", "body", tx, "识别羽毛球、分割回合、计算球速，全程不联网。").style.cssText = "font-size:36px;line-height:1.45;margin-top:10px;color:var(--ink)";
    c.lbl = el("div", "", c.card); c.lbl.style.cssText = "font:700 30px SFMono;letter-spacing:3px;margin:30px 0 12px";
    const bar = el("div", "", c.card); bar.style.cssText = "height:34px;border:4px solid var(--ink);border-radius:20px;background:var(--card);overflow:hidden";
    c.fill = el("div", "", bar); c.fill.style.cssText = "height:100%;background:var(--ink);border-radius:16px;width:0";
    c.steps = ["找羽毛球", "认球场", "看人", "判每一拍", "记分"].map(s => {
      const r = el("div", "", c.card); r.style.cssText = "display:flex;align-items:center;gap:28px;margin-top:26px";
      const dot = el("div", "", r); dot.style.cssText = "width:58px;height:58px;border-radius:50%;box-sizing:border-box;display:flex;align-items:center;justify-content:center";
      const tt = el("div", "", r, s); tt.style.cssText = "font:600 46px 'PingFang SC'";
      return { dot, tt };
    });
    c.stamp = css(el("div", "sticker abs", root, `<svg width="26" height="40" viewBox="0 0 26 40"><rect x="3" y="3" width="20" height="34" rx="5" fill="none" stroke="#221B2E" stroke-width="4"/><rect x="9" y="7" width="8" height="3" rx="1.5" fill="#221B2E"/></svg>手机端分析`), { background: "var(--pistachio)", fontSize: "44px" });
    [20.95, 21.1, 21.25].forEach((x, i) => cue(x, "stamp", { gain: .55, pitch: .3 + i * .2 }));
    [22.0, 22.45, 22.9, 23.35, 23.8].forEach((x, i) => cue(x, "tick", { pitch: .2 + i * .18, gain: .8 }));
    cue(24.05, "chime", { gain: .6 }); cue(24.15, "stamp", { gain: 1 }); cue(26.0, "iris", { gain: .7 });
    BUBBLES.add(24.45, 25.95, "麦克风压根没开——\n骂球，它也听不见。", "r");
  },
  update(lt, t) {
    const c = this, oy = H * (1 - E.ioCubic(prog(t, 19.95, 20.45)));
    this.root.style.transform = oy ? `translateY(${oy}px)` : "";
    putTL(c.chap, 80, 150, 1, 0, clamp((t - 20.4) * 5));
    putTL(c.h.el, 80, 200); popChars(c.h, t, 20.45, 0.045);
    putTL(c.nos, 80, 360, 1, 0, 1);
    c.noEls.forEach((e, i) => { const s = spring(t - 20.95 - i * 0.15, 3, 0.36); e.style.transform = `scale(${lerp(1.7, 1, s)}) rotate(${[-4, 3, -2][i]}deg)`; e.style.opacity = clamp(s * 4); });
    const cs = spring(t - 21.35, 1.8, 0.5);
    putTL(c.card, 80, 510 + (1 - cs) * 300, 1, 0, clamp(cs * 2));
    const pr = clamp(ease(t, 21.8, 24.0, E.ioSine));
    c.fill.style.width = (pr * 100).toFixed(2) + "%";
    const TS = [22.0, 22.45, 22.9, 23.35, 23.8], cur = TS.findIndex(x => t < x);
    const verb = ["找羽毛球", "认球场", "追踪球员", "判每一拍", "记分"][cur < 0 ? 4 : cur];
    c.lbl.textContent = pr >= 1 ? "分析完成 100%" : `手机分析中 ${Math.round(pr * 100)}% · ${verb}`;
    c.steps.forEach((s, i) => {
      const done = t >= TS[i], now = !done && (i === 0 ? t > 21.6 : t >= TS[i - 1]);
      const st = done ? "d" : now ? "n" : "p";
      if (s._st !== st) {
        s._st = st;
        s.dot.style.background = st === "d" ? "var(--pistachio)" : st === "n" ? "var(--card)" : "transparent";
        s.dot.style.border = st === "p" ? "4px dashed var(--inkFaint)" : "4px solid var(--ink)";
        s.dot.innerHTML = st === "d" ? '<svg width="30" height="30" viewBox="0 0 30 30"><path d="M6 16 L12 22 L24 8" fill="none" stroke="#221B2E" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>' : st === "n" ? '<div style="width:26px;height:26px;border-radius:50%;background:var(--tomato)"></div>' : "";
        s.tt.style.color = st === "p" ? "var(--inkFaint)" : "var(--ink)";
      }
      const k = done ? wob(t - TS[i], 3, 6) : 0;
      s.dot.style.transform = `scale(${1 + k * 0.35 + (now ? 0.06 * Math.sin(t * 12) : 0)})`;
    });
    const ss = spring(t - 24.15, 3, 0.35);
    put(c.stamp, 800, 540, lerp(1.9, 1, ss), 7, clamp(ss * 4));
  },
  pose(lt, t) {
    const I = idle(t, 3.3);
    const h = hop(t, 19.98, 20.5, { x: S2B.x, y: S2B.y - H * 0.4 }, S3M, 300);
    if (t < 20.5) return Object.assign(h, { mood: "happy", s: 0.95 });
    const hush = t > 24.4 && t < 26;
    return Object.assign(I, { x: S3M.x, y: S3M.y, s: 0.95, sq: I.sq + h.sq, mood: hush ? "smug" : t > 23.8 ? "happy" : "normal", lx: 0.6, ly: -0.7 });
  },
});
function scallop(cx, cy, R, r, n) {
  let d = "";
  for (let i = 0; i <= n * 8; i++) {
    const a = i / (n * 8) * 2 * Math.PI, rr = r + (R - r) * (0.5 + 0.5 * Math.cos(a * n));
    d += (i ? "L" : "M") + (cx + Math.cos(a) * rr).toFixed(2) + " " + (cy + Math.sin(a) * rr).toFixed(2);
  }
  return d + "Z";
}
