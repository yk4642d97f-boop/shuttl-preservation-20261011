import sys, numpy as np, collections
from scipy import signal
sys.path.insert(0, '.')
import data
N_FFT, HOP = 512, 64
rng = np.random.default_rng(0)
per = collections.defaultdict(lambda: {'off': [], 'h': [], 'b': []})
for c in data.all_clips():
    x, sr = data.read_wav(c.wav)
    for a, b in c.windows:
        s0 = max(0, int((a - c.audio_start) * sr)); s1 = min(len(x), int((b - c.audio_start) * sr))
        if s1 - s0 < N_FFT * 4: continue
        f, t, Z = signal.stft(x[s0:s1], sr, nperseg=N_FFT, noverlap=N_FFT - HOP, boundary=None, padded=False)
        L = np.log1p(1000 * np.abs(Z)).astype(np.float32)
        t = t + s0 / sr + c.audio_start
        flux = np.maximum(0, np.diff(L, axis=1)); tf = t[1:]
        hb = flux[(f > 6000) & (f < 16000)].mean(0)
        g = per[c.group]
        for th in c.hits_t[(c.hits_t >= a) & (c.hits_t <= b)]:
            m = (tf > th - 0.2) & (tf < th + 0.2)
            if m.sum() < 5: continue
            i = np.flatnonzero(m)[np.argmax(hb[m])]
            g['off'].append(tf[i] - th); g['h'].append(hb[i])
        for _ in range(int((b - a) * 2)):
            lo, hi = max(a, tf[0] + .21), min(b, tf[-1] - .21)
            if hi <= lo: break
            u = rng.uniform(lo, hi)
            if len(c.hits_t) and np.min(np.abs(c.hits_t - u)) < 0.25: continue
            m = (tf > u - 0.2) & (tf < u + 0.2)
            g['b'].append(hb[np.flatnonzero(m)[np.argmax(hb[m])]])
for k, g in per.items():
    o = np.array(g['off']) * 1e3; h, b = np.array(g['h']), np.array(g['b'])
    d = (h.mean() - b.mean()) / np.sqrt((h.var() + b.var()) / 2 + 1e-12)
    hist = np.histogram(o, bins=np.arange(-200, 201, 40))[0]
    print(f"{k:18s} n={len(o):4d} d6-16k={d:5.2f} off_med={np.median(o):6.1f}ms  hist(-200..200 step40)={hist.tolist()}")
