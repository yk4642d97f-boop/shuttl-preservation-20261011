"""Which frequencies carry the racket–shuttle impact, and how is it timed vs the label?"""
import sys, numpy as np
from scipy import signal
sys.path.insert(0, '.')
import data

N_FFT, HOP = 512, 64            # 16 ms window, 2 ms hop at 32 kHz

def spec(x, sr):
    f, t, Z = signal.stft(x, sr, nperseg=N_FFT, noverlap=N_FFT - HOP, boundary=None, padded=False)
    return f, t + (N_FFT / 2) / sr * 0, np.log1p(1000 * np.abs(Z))   # t = window start + centre via stft

rng = np.random.default_rng(0)
res = {}
for kind in ('amateur', 'broadcast'):
    hit_flux, bg_flux, offsets = [], [], []
    for c in data.all_clips():
        if c.kind != kind:
            continue
        x, sr = data.read_wav(c.wav)
        for a, b in c.windows:
            s0 = max(0, int((a - c.audio_start) * sr)); s1 = min(len(x), int((b - c.audio_start) * sr))
            if s1 - s0 < N_FFT * 4:
                continue
            f, t, L = spec(x[s0:s1], sr)
            t = t + s0 / sr + c.audio_start              # audio clock -> video clock
            flux = np.maximum(0, np.diff(L, axis=1)).astype(np.float32)
            tf = t[1:]
            broad = flux[(f > 1000) & (f < 12000)].sum(0)
            for th in c.hits_t[(c.hits_t >= a) & (c.hits_t <= b)]:
                m = (tf > th - 0.12) & (tf < th + 0.12)
                if m.sum() < 5:
                    continue
                i = np.flatnonzero(m)[np.argmax(broad[m])]
                offsets.append(tf[i] - th)
                hit_flux.append(flux[:, i])
            # background: random instants inside evaluated windows, >=150 ms from any hit
            for _ in range(int((b - a) * 2)):
                u = rng.uniform(max(a, tf[0] + .13), min(b, tf[-1] - .13))
                if len(c.hits_t) and np.min(np.abs(c.hits_t - u)) < 0.15:
                    continue
                m = (tf > u - 0.12) & (tf < u + 0.12)
                if m.sum() < 5:
                    continue
                i = np.flatnonzero(m)[np.argmax(broad[m])]   # same "best peak in window" rule
                bg_flux.append(flux[:, i])
    H, B = np.array(hit_flux), np.array(bg_flux)
    off = np.array(offsets)
    print(f"== {kind}: hits={len(H)} bg={len(B)}")
    print("  peak offset vs label (ms): median %.1f  IQR %.1f..%.1f  |off|<40ms %.2f" % (
        1e3 * np.median(off), 1e3 * np.percentile(off, 25), 1e3 * np.percentile(off, 75), np.mean(np.abs(off - np.median(off)) < .04)))
    # per-band discriminability (Cohen's d of mean flux in band, best-peak hit vs bg)
    edges = [250, 500, 1000, 2000, 3000, 4000, 5000, 6000, 8000, 10000, 12000, 14000, 16000]
    for lo, hi in zip(edges[:-1], edges[1:]):
        bm = (f >= lo) & (f < hi)
        h, b = H[:, bm].mean(1), B[:, bm].mean(1)
        d = (h.mean() - b.mean()) / np.sqrt((h.var() + b.var()) / 2 + 1e-9)
        print(f"  band {lo:5d}-{hi:5d} Hz  d={d:5.2f}  hit={h.mean():.3f} bg={b.mean():.3f}")
