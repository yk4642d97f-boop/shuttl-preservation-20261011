// Boot: build every scene, wait for fonts + images, then expose seek() for the renderer.
const DURATION = 60.0;
async function boot() {
  STAGE = document.getElementById("world");
  SCENES.forEach((s, i) => {
    s.root = el("div", "scene", STAGE);
    s.root.style.zIndex = s.z ?? (10 + i);
    s._on = false;
    s.build(s.root);
  });
  await document.fonts.load('900 100px NY'); await document.fonts.load('italic 900 100px NY');
  await document.fonts.load('700 20px SFMono'); await document.fonts.load('600 100px "PingFang SC"');
  await document.fonts.ready;
  await Promise.all([...document.images].map(i => i.decode().catch(() => null)));
  CUES.sort((a, b) => a.t - b.t);
  window.READY = true;
  const q = new URLSearchParams(location.search);
  if (q.has("play")) {
    const t0 = performance.now() - (+q.get("t") || 0) * 1000;
    const loop = () => { seek(((performance.now() - t0) / 1000) % DURATION); requestAnimationFrame(loop); };
    loop();
  } else seek(+q.get("t") || 0);
}
window.seek = seek;
window.getCues = () => CUES;
window.DURATION = DURATION;
boot();
