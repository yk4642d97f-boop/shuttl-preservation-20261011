/* ============================================================
   羽析 · 动效工具 (原生 JS, 无依赖)
   - 一个全局 rAF 时钟, 所有动画共用, dt 以秒计并限幅
   - 物理弹簧: 质量-刚度-阻尼, 固定子步长积分, 手感与帧率无关
   - 进入视野触发 / 数字滚动 / 缓动曲线
   ============================================================ */
const Motion = (() => {
  const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const loops = new Set();
  let last = performance.now();
  (function tick(now) {
    const dt = Math.min(1 / 20, (now - last) / 1000); last = now;
    for (const fn of [...loops]) { if (fn(dt, now) === false) loops.delete(fn); }
    requestAnimationFrame(tick);
  })(last);
  const loop = (fn) => { loops.add(fn); return () => loops.delete(fn); };

  const ease = {
    outExpo: (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
    outCubic: (t) => 1 - Math.pow(1 - t, 3),
    inOut: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
    outBack: (t) => { const c = 1.56; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); },
  };

  /** 时长动画; 返回 Promise。减少动效时直接跳到终点。 */
  function tween(ms, onUpdate, curve = ease.outExpo) {
    return new Promise((res) => {
      if (REDUCED || ms <= 0) { onUpdate(1); res(); return; }
      let t = 0;
      loop((dt) => { t += (dt * 1000) / ms; const u = Math.min(1, t); onUpdate(curve(u)); if (u >= 1) { res(); return false; } });
    });
  }

  /**
   * 物理弹簧。preset 取自 motion-tokens: snappy 350/28 (按钮与滑块), default 200/22 (面板), bouncy 260/16 (判定弹出)。
   * 子步长 1/240 s 积分, 所以 30/60/120 Hz 下轨迹一致。
   */
  const PRESET = { snappy: [350, 28], default: [200, 22], bouncy: [260, 15], sheet: [300, 32] };
  function spring(value, onUpdate, preset = "snappy") {
    const [k, c] = PRESET[preset] || preset;
    let x = value, v = 0, target = value, running = false, onRest = null;
    const step = (dt) => {
      let left = dt;
      while (left > 1e-6) {
        const h = Math.min(1 / 240, left); left -= h;
        v += (-k * (x - target) - c * v) * h;
        x += v * h;
      }
      if (Math.abs(v) < 0.01 && Math.abs(x - target) < 0.01) { x = target; v = 0; onUpdate(x, v); running = false; onRest?.(); onRest = null; return false; }
      onUpdate(x, v);
    };
    return {
      get value() { return x; }, get velocity() { return v; },
      set(t, { velocity, done } = {}) {
        target = t; if (velocity != null) v = velocity; onRest = done || null;
        if (REDUCED) { x = t; v = 0; onUpdate(x, 0); done?.(); return; }
        if (!running) { running = true; loop(step); }
      },
      jump(t) { x = target = t; v = 0; onUpdate(x, 0); },
    };
  }

  /** 与帧率无关的指数跟随 (handfeel §7.1) */
  const follow = (cur, target, k, dt) => cur + (target - cur) * (1 - Math.exp(-k * dt));

  /** 第一次进入视野时触发一次 */
  function inView(el, cb, threshold = 0.3) {
    if (REDUCED || !("IntersectionObserver" in window)) { cb(); return; }
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { io.disconnect(); cb(); } }, { threshold });
    io.observe(el);
  }

  /** 数字滚动: 进入视野才开始, 最后一帧一定写入真实值 */
  function countUp(el, value, { digits = 0, ms = 1100, delay = 0 } = {}) {
    const fmt = (v) => (digits ? v.toFixed(digits) : Math.round(v).toLocaleString("zh-CN"));
    if (REDUCED) { el.textContent = fmt(value); return el; }
    el.textContent = fmt(0);
    inView(el, () => setTimeout(() => tween(ms, (u) => { el.textContent = fmt(value * u); }).then(() => { el.textContent = fmt(value); }), delay));
    return el;
  }

  return { REDUCED, loop, ease, tween, spring, follow, inView, countUp };
})();
