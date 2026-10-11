/* ============================================================
   羽析 · 球场舞台 —— canvas 2D 手写透视, 不依赖任何第三方库
   世界坐标 (米): X 左右, Y 高, Z 纵深 (近端为正), 球网在 Z = 0
   飞行弧线由真实数据重建: 每一拍的击球时刻 + 击球者站位 + 最终落点
   ============================================================ */
const Stage = (() => {
  const CW = 6.10, CL = 13.40, SM = 0.46, SS = 1.98, DL = 0.76;
  const NEAR = 0.25;
  const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const toWorld = ([x, y]) => [x - CW / 2, y - CL / 2];
  const LINES = [
    [[0, 0], [CW, 0]], [[0, CL], [CW, CL]], [[0, 0], [0, CL]], [[CW, 0], [CW, CL]],
    [[SM, 0], [SM, CL]], [[CW - SM, 0], [CW - SM, CL]],
    [[0, CL / 2 - SS], [CW, CL / 2 - SS]], [[0, CL / 2 + SS], [CW, CL / 2 + SS]],
    [[0, DL], [CW, DL]], [[0, CL - DL], [CW, CL - DL]],
    [[CW / 2, 0], [CW / 2, CL / 2 - SS]], [[CW / 2, CL / 2 + SS], [CW / 2, CL]],
  ].map((s) => s.map(toWorld));
  const HIT_H = { 发球: 1.1, 杀球: 2.7, 高远球: 2.5, 吊球: 2.4, 平抽: 1.5, 网前球: 0.9, 挑球: 0.6 };
  const COL = { ground: "#07211A", court: "rgba(29,107,79,.62)", line: "255,255,255", shuttle: "242,194,48",
                near: "255,179,64", far: "169,166,255", out: "229,69,47", grid: "160,220,196" };
  const MONO = '500 11px "IBM Plex Mono", ui-monospace, Menlo, monospace';

  // ---------------------------------------------------------------- 数据
  const DEFAULT_POS = { near: [CW / 2 + 0.6, CL - 2.4], far: [CW / 2 - 0.6, 2.4] };
  /** 从分析结果里取出一个回合, 整理成舞台需要的形状 */
  function rallyFrom(R, r) {
    return {
      names: R.names || { near: "近端", far: "远端" },
      rally: { index: r.index, start_t: r.start_t, end_t: r.end_t, winner: r.winner, reason: r.reason, num_shots: r.num_shots },
      landing: r.landing,
      shots: r.shots.map((s) => ({ t: s.t, side: s.side, type: s.type, m: s.player_m || DEFAULT_POS[s.side] })),
    };
  }
  /** 没有任何比赛时用的示意回合 (界面上会标注"示意") */
  function demoRally() {
    const seq = [["发球", [3.9, 11.7]], ["高远球", [2.1, 1.9]], ["吊球", [4.8, 12.3]], ["网前球", [1.5, 4.9]],
                 ["挑球", [3.4, 8.4]], ["杀球", [4.6, 1.6]], ["平抽", [1.8, 11.2]], ["吊球", [3.2, 3.1]]];
    const gaps = [0, 0.9, 1.25, 0.8, 0.55, 1.3, 0.5, 0.75];
    let t = 0;
    const shots = seq.map(([type, m], i) => { t += gaps[i]; return { t, type, m, side: i % 2 ? "far" : "near" }; });
    const end = t + 1.1;
    return { demo: true, names: { near: "近端", far: "远端" },
             rally: { index: 0, start_t: shots[0].t, end_t: end, winner: "far", reason: "界内得分", num_shots: shots.length },
             landing: { m: [4.7, 12.6], in: true, uncertain: false, net_dist_m: 5.9, line: "底线", margin_m: 0.04 },
             shots };
  }

  // ---------------------------------------------------------------- 飞行重建
  function buildFlight(R) {
    const legs = [];
    const L = R.landing;
    R.shots.forEach((s, i) => {
      const nx = R.shots[i + 1];
      const endM = nx ? nx.m : (L ? L.m : DEFAULT_POS[s.side === "near" ? "far" : "near"]);
      const T = Math.max(0.2, (nx ? nx.t : R.rally.end_t) - s.t);
      const h0 = HIT_H[s.type] ?? 2, h1 = nx ? (HIT_H[nx.type] ?? 2) : 0;
      const apex = Math.max(1.9, Math.min(8, Math.max(h0, h1) + 0.35 + 1.6 * T * T));
      legs.push({ t0: s.t, t1: s.t + T, a: toWorld(s.m), b: toWorld(endM), h0, h1, apex });
    });
    return legs;
  }
  function along(leg, u) {
    const hu = 1 - Math.pow(1 - u, 1.7);              // 阻力: 水平方向先快后慢
    const k = 0.42;                                   // 顶点偏后, 过顶后急降
    const top = Math.max(leg.h0, leg.h1);
    const bump = u < k ? Math.sin((u / k) * Math.PI / 2) : Math.cos(((u - k) / (1 - k)) * Math.PI / 2);
    return [leg.a[0] + (leg.b[0] - leg.a[0]) * hu,
            leg.h0 + (leg.h1 - leg.h0) * u + (leg.apex - top) * bump,
            leg.a[1] + (leg.b[1] - leg.a[1]) * hu];
  }
  function posAt(legs, t) {
    if (!legs.length) return [0, 1.5, 0];
    const leg = legs.find((l) => t <= l.t1) || legs[legs.length - 1];
    return along(leg, Math.min(1, Math.max(0, (t - leg.t0) / (leg.t1 - leg.t0))));
  }
  /** 球员位置: 在自己相邻两次击球站位之间平滑过渡 */
  function playerAt(shots, side, t) {
    const own = shots.filter((s) => s.side === side);
    if (!own.length) return toWorld(DEFAULT_POS[side]);
    let prev = own[0], next = own[0];
    for (const s of own) { if (s.t <= t) prev = s; if (s.t >= t) { next = s; break; } next = s; }
    if (prev === next || next.t <= prev.t) return toWorld(prev.m);
    const u = (t - prev.t) / (next.t - prev.t), e = u * u * (3 - 2 * u);
    const a = toWorld(prev.m), b = toWorld(next.m);
    return [a[0] + (b[0] - a[0]) * e, a[1] + (b[1] - a[1]) * e];
  }

  // ---------------------------------------------------------------- 相机
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const norm = (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
  const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);
  const smooth = (t) => { t = Math.min(1, Math.max(0, t)); return t * t * (3 - 2 * t); };
  function makeCam(pos, look, fov) {
    const fwd = norm(sub(look, pos));
    const right = norm(cross(fwd, [0, 1, 0]));
    return { pos, fwd, right, up: cross(right, fwd), f: 1 / Math.tan(fov * Math.PI / 360) };
  }

  // ---------------------------------------------------------------- 舞台
  function create(canvas, opts = {}) {
    const ctx = canvas.getContext("2d");
    const mode = opts.mode || "cover";        // cover: 自动播放 + 指针视差 / flight: 外部驱动进度 / wait: 缓慢环绕
    let W = 1, H = 1, dpr = 1, alive = true, visible = true, raf = 0, last = performance.now(), clock = 0;
    let data = opts.rally || demoRally(), legs = buildFlight(data);
    let prog = REDUCED && mode === "flight" ? 1 : 0, target = prog;
    const ptr = { x: 0, y: 0, tx: 0, ty: 0 };
    const dust = Array.from({ length: 80 }, () => ({ x: (Math.random() - 0.5) * 18, y: Math.random() * 9, z: (Math.random() - 0.5) * 28, s: 0.2 + Math.random() * 0.5 }));
    let onFrame = opts.onFrame || null;
    let C = null;

    function resize() {
      const r = canvas.getBoundingClientRect();
      W = Math.max(1, r.width); H = Math.max(1, r.height);
      dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    }
    const ro = new ResizeObserver(resize); ro.observe(canvas); resize();
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; }); io.observe(canvas);
    const onMove = (e) => { ptr.tx = (e.clientX / innerWidth) * 2 - 1; ptr.ty = (e.clientY / innerHeight) * 2 - 1; };
    if (mode === "cover") addEventListener("pointermove", onMove, { passive: true });

    // ---- 投影 (相机空间裁剪, 镜头压低时近端球场不会整块消失)
    const cx = () => W * (0.5 + (opts.offsetX || 0)), cy = () => H * (0.5 + (opts.offsetY || 0));
    const toCam = (p) => { const d = sub(p, C.pos); return [dot(d, C.right), dot(d, C.up), dot(d, C.fwd)]; };
    const scr = (c) => { const k = (C.f / c[2]) * H / 2; return [cx() + c[0] * k, cy() - c[1] * k]; };
    const cut = (a, b) => { const t = (NEAR - a[2]) / (b[2] - a[2]); return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, NEAR]; };
    function project(p) { const c = toCam(p); return c[2] < NEAR ? null : [...scr(c), c[2]]; }
    function path(pts, closed) {
      const cam = pts.map(toCam), n = cam.length, m = closed ? n : n - 1;
      let pen = false;
      for (let i = 0; i < m; i++) {
        let a = cam[i], b = cam[(i + 1) % n];
        const ain = a[2] >= NEAR, bin = b[2] >= NEAR;
        if (!ain && !bin) { pen = false; continue; }
        if (!ain) { a = cut(a, b); pen = false; }
        if (!bin) b = cut(a, b);
        const A = scr(a), B = scr(b);
        if (!pen) ctx.moveTo(A[0], A[1]);
        ctx.lineTo(B[0], B[1]); pen = bin;
      }
    }
    function fillPoly(pts) {
      let poly = pts.map(toCam), out = [];
      for (let i = 0; i < poly.length; i++) {
        const a = poly[i], b = poly[(i + 1) % poly.length], ain = a[2] >= NEAR, bin = b[2] >= NEAR;
        if (ain) out.push(a);
        if (ain !== bin) out.push(cut(a, b));
      }
      if (out.length < 3) return false;
      out.forEach((c, i) => { const s = scr(c); i ? ctx.lineTo(s[0], s[1]) : ctx.moveTo(s[0], s[1]); });
      ctx.closePath(); return true;
    }
    const ring = (x, z, r, y = 0, seg = 32) => Array.from({ length: seg }, (_, i) => { const a = (i / seg) * Math.PI * 2; return [x + Math.cos(a) * r, y, z + Math.sin(a) * r]; });

    // ---- 每种模式的镜头与时间
    function camFor(dt) {
      const R0 = data.rally.start_t, R1 = data.rally.end_t;
      if (mode === "flight") {
        prog += (target - prog) * (1 - Math.exp(-6.5 * dt));     // handfeel §7.1: 与帧率无关的跟随
        const t = R0 + (R1 + 1.1 - R0) * prog;
        const e = smooth(prog / 0.8);
        const L = data.landing ? toWorld(data.landing.m) : [0, 0];
        const endLook = [L[0], 0, L[1]];
        const q = smooth((prog - 0.8) / 0.2);
        const pos = mix(mix([0, 17, 12.5], [0, 4.8, 13.2], e), [L[0] + 1.8, 2.4, L[1] + 5.2], q);
        const look = mix(mix([0, 0, -0.5], [0, 1.1, -2.2], e), endLook, q);
        return { t, cam: makeCam(pos, look, 42) };
      }
      ptr.x += (ptr.tx - ptr.x) * (1 - Math.exp(-2.4 * dt));
      ptr.y += (ptr.ty - ptr.y) * (1 - Math.exp(-2.4 * dt));
      const span = R1 - R0 + 1.8;
      const t = REDUCED ? R0 + span * 0.55 : R0 + (clock % span);
      if (mode === "wait") {
        const yaw = clock * 0.06;
        return { t, cam: makeCam([Math.sin(yaw) * 19, 11, Math.cos(yaw) * 19], [0, 0.4, 0], 38) };
      }
      const yaw = -0.42 + ptr.x * 0.3 + (REDUCED ? 0 : Math.sin(clock * 0.05) * 0.08);
      const h = 7.2 - ptr.y * 1.6;
      return { t, cam: makeCam([Math.sin(yaw) * 17.5, h, Math.cos(yaw) * 17.5], [0, 0.7, -0.4], 38) };
    }

    // ---- 绘制
    function draw(dt) {
      const { t, cam } = camFor(dt);
      C = cam;
      const R1 = data.rally.end_t;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = COL.ground; ctx.fillRect(0, 0, W, H);
      // 地面光晕: 球场像被一盏顶灯照着
      const c0 = project([0, 0, 0]);
      if (c0) {
        const g = ctx.createRadialGradient(c0[0], c0[1], 0, c0[0], c0[1], Math.max(W, H) * 0.62);
        g.addColorStop(0, "rgba(40,120,90,.28)"); g.addColorStop(1, "rgba(40,120,90,0)");
        ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
      }
      // 技术底纹: 地面同心刻度 + 放射线 (仪器感, 不是装饰图案)
      ctx.lineWidth = 1;
      for (let r = 4; r <= 40; r += 3) {
        ctx.strokeStyle = `rgba(${COL.grid},${(r - 4) % 12 === 0 ? 0.15 : 0.06})`;
        ctx.beginPath(); path(ring(0, 0, r, 0, 96), true); ctx.stroke();
      }
      ctx.strokeStyle = `rgba(${COL.grid},.05)`;
      for (let a = 0; a < 24; a++) { const th = (a / 24) * Math.PI * 2; ctx.beginPath(); path([[Math.cos(th) * 4, 0, Math.sin(th) * 4], [Math.cos(th) * 40, 0, Math.sin(th) * 40]]); ctx.stroke(); }

      // 球场
      const corners = [[0, 0], [CW, 0], [CW, CL], [0, CL]].map(toWorld).map(([x, z]) => [x, 0, z]);
      ctx.beginPath(); if (fillPoly(corners)) { ctx.fillStyle = COL.court; ctx.fill(); }
      ctx.strokeStyle = `rgba(${COL.line},.74)`; ctx.lineWidth = 1.2;
      for (const [[x1, z1], [x2, z2]] of LINES) { ctx.beginPath(); path([[x1, 0, z1], [x2, 0, z2]]); ctx.stroke(); }

      // 尘埃: 无输入时也在缓慢上浮
      for (const d of dust) {
        if (!REDUCED) { d.y += d.s * dt * 0.35; if (d.y > 9) d.y = 0; }
        const q = project([d.x, d.y, d.z]); if (!q) continue;
        ctx.fillStyle = `rgba(${COL.shuttle},${Math.min(0.5, 3 / q[2])})`; ctx.fillRect(q[0], q[1], 1.4, 1.4);
      }

      // 已经发生的击球: 站位环 + 球种
      let nShots = 0, cur = null;
      ctx.font = MONO; ctx.textAlign = "center";
      for (const s of data.shots) {
        if (s.t > t) break;
        nShots++; cur = s;
        const [x, z] = toWorld(s.m), age = Math.min(1, (t - s.t) / 3);
        const col = s.side === "near" ? COL.near : COL.far;
        ctx.strokeStyle = `rgba(${col},${0.85 - age * 0.55})`; ctx.lineWidth = 1.2;
        ctx.beginPath(); path(ring(x, z, 0.32, 0, 24), true); ctx.stroke();
        if (t - s.t < 1.4) { const q = project([x, 0, z]); if (q) { ctx.fillStyle = `rgba(${col},.95)`; ctx.fillText(s.type, q[0], q[1] + 18); } }
      }

      // 球员: 抽象成一根竖线 + 头部圆点 (人不画, 只标站位与身高)
      for (const side of ["far", "near"]) {
        const [x, z] = playerAt(data.shots, side, Math.min(t, R1));
        const a = project([x, 0, z]), b = project([x, 1.75, z]);
        if (!a || !b) continue;
        const col = side === "near" ? COL.near : COL.far;
        ctx.strokeStyle = `rgba(${col},.8)`; ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
        ctx.fillStyle = `rgba(${col},1)`; ctx.beginPath(); ctx.arc(b[0], b[1], Math.max(2.2, 22 / b[2]), 0, 7); ctx.fill();
      }

      // 球网 (0.8 ~ 1.55 米), 画在球员之后以保证网带清晰
      const nw = CW / 2 + 0.08;
      ctx.beginPath(); if (fillPoly([[-nw, 0.8, 0], [nw, 0.8, 0], [nw, 1.55, 0], [-nw, 1.55, 0]])) { ctx.fillStyle = "rgba(255,255,255,.07)"; ctx.fill(); }
      ctx.strokeStyle = `rgba(${COL.line},.92)`; ctx.lineWidth = 1.6;
      ctx.beginPath(); path([[-nw, 1.55, 0], [nw, 1.55, 0]]); ctx.stroke();
      ctx.lineWidth = 1;
      ctx.beginPath(); path([[-nw, 0, 0], [-nw, 1.55, 0]]); ctx.stroke();
      ctx.beginPath(); path([[nw, 0, 0], [nw, 1.55, 0]]); ctx.stroke();

      // 尾迹: 最近 1.1 秒 (每帧从时间算出来, 进度倒退时会跟着收回)
      const R0 = data.rally.start_t;
      if (t > R0) {
        ctx.save(); ctx.globalCompositeOperation = "lighter"; ctx.lineCap = "round";
        let prev = null;
        for (let k = 0; k <= 56; k++) {
          const tt = t - (k * 1.1) / 56; if (tt < R0) break;
          const q = project(posAt(legs, Math.min(tt, R1)));
          if (q && prev) {
            const w = 1 - k / 56;
            ctx.strokeStyle = `rgba(${COL.shuttle},${w * 0.85})`; ctx.lineWidth = 0.6 + w * 2.6;
            ctx.beginPath(); ctx.moveTo(prev[0], prev[1]); ctx.lineTo(q[0], q[1]); ctx.stroke();
          }
          prev = q;
        }
        ctx.restore();
      }

      // 球 + 地面投影 + 垂线 (让人读出高度)
      const bp = posAt(legs, Math.min(t, R1));
      const sh = project([bp[0], 0, bp[2]]), bq = project(bp);
      if (sh) {
        ctx.fillStyle = "rgba(0,0,0,.4)"; ctx.beginPath(); ctx.ellipse(sh[0], sh[1], 7, 2.6, 0, 0, 7); ctx.fill();
        if (bq) { ctx.strokeStyle = `rgba(${COL.shuttle},.28)`; ctx.setLineDash([2, 3]); ctx.beginPath(); ctx.moveTo(sh[0], sh[1]); ctx.lineTo(bq[0], bq[1]); ctx.stroke(); ctx.setLineDash([]); }
      }
      if (bq) {
        const r = Math.max(2.8, 40 / bq[2]);
        const g = ctx.createRadialGradient(bq[0], bq[1], 0, bq[0], bq[1], r * 6);
        g.addColorStop(0, `rgba(${COL.shuttle},.45)`); g.addColorStop(1, `rgba(${COL.shuttle},0)`);
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(bq[0], bq[1], r * 6, 0, 7); ctx.fill();
        ctx.fillStyle = "#FFF4D0"; ctx.beginPath(); ctx.arc(bq[0], bq[1], r, 0, 7); ctx.fill();
      }

      // 落点判定: 三圈由内向外扩开
      const L = data.landing, done = t >= R1;
      if (done && L) {
        const a = REDUCED ? 1 : Math.min(1, (t - R1) / 0.6);
        const [lx, lz] = toWorld(L.m);
        const col = L.uncertain ? COL.shuttle : (L.in ? COL.line : COL.out);
        for (const [rad, al] of [[0.18, 1], [0.42 * a + 0.18, 0.5], [0.9 * a + 0.2, 0.18]]) {
          ctx.strokeStyle = `rgba(${col},${al * a})`; ctx.lineWidth = 1.6;
          ctx.beginPath(); path(ring(lx, lz, rad), true); ctx.stroke();
        }
        const q = project([lx, 0, lz]);
        if (q) {
          ctx.fillStyle = `rgba(${col},${a})`; ctx.font = MONO;
          const label = L.uncertain ? `存疑 · 离网 ${Math.round((L.net_dist_m ?? 0) * 100)} 厘米` : L.in ? "界内" : "出界";
          ctx.fillText(label, q[0], q[1] - 26);
        }
      }
      onFrame && onFrame({ t, prog, nShots, cur, done, total: data.shots.length, rally: data.rally, demo: !!data.demo });
    }

    function frame(now) {
      if (!alive) return;
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.05, (now - last) / 1000); last = now;
      if (!visible) return;
      if (!REDUCED) clock += dt;
      draw(dt);
    }
    raf = requestAnimationFrame(frame);

    return {
      setProgress(p) { target = Math.min(1, Math.max(0, p)); if (REDUCED) { prog = target = mode === "flight" ? 1 : target; } },
      setRally(r) { data = r || demoRally(); legs = buildFlight(data); },
      onFrame(cb) { onFrame = cb; },
      destroy() { alive = false; cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); removeEventListener("pointermove", onMove); },
    };
  }

  return { create, rallyFrom, demoRally, toWorld, CW, CL };
})();
