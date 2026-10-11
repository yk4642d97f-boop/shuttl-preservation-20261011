"""Synth building blocks for the Shuttl promo soundtrack (numpy/scipy only, 48 kHz stereo)."""
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
RNG = np.random.default_rng(20260930)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tt(dur):
    return np.arange(int(dur * SR)) / SR


def noise(dur):
    return RNG.standard_normal(int(dur * SR))


def lp(x, f, o=2):
    return sosfilt(butter(o, min(f, SR * 0.45), "low", fs=SR, output="sos"), x)


def hp(x, f, o=2):
    return sosfilt(butter(o, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, o=2):
    return sosfilt(butter(o, [lo, min(hi, SR * 0.45)], "band", fs=SR, output="sos"), x)


def env(n, a=0.002, d=0.3, curve=6.0):
    t = np.arange(n) / SR
    atk = np.clip(t / max(a, 1e-4), 0, 1)
    return atk * np.exp(-curve * np.maximum(t - a, 0) / max(d, 1e-4))


def adsr(n, a, r, hold):
    t = np.arange(n) / SR
    e = np.clip(t / a, 0, 1)
    rel = np.clip(1 - (t - hold) / r, 0, 1)
    return e * np.where(t > hold, rel, 1.0)


class Bus:
    """Stereo accumulation buffer."""

    def __init__(self, dur):
        self.x = np.zeros((2, int(dur * SR) + SR))

    def add(self, sig, t, pan=0.0, gain=1.0):
        i = int(round(t * SR))
        if i >= self.x.shape[1] or i < 0 and -i >= (sig.shape[-1]):
            return
        if sig.ndim == 1:
            a = (pan + 1) * np.pi / 4
            sig = np.stack([sig * np.cos(a), sig * np.sin(a)]) * np.sqrt(2)
        if i < 0:
            sig, i = sig[:, -i:], 0
        n = min(sig.shape[1], self.x.shape[1] - i)
        self.x[:, i:i + n] += gain * sig[:, :n]


def reverb_ir(dur=1.8, decay=3.2, pre=0.018, damp=5200):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = []
    for ch in range(2):
        r = RNG.standard_normal(n) * np.exp(-decay * t)
        r = lp(r, damp) * (t > pre)
        out.append(r / np.sqrt(np.sum(r ** 2)))
    return np.array(out)


def reverb(x, ir):
    return np.stack([fftconvolve(x[c], ir[c])[: x.shape[1]] for c in range(2)])


# ── Voices ───────────────────────────────────────────────────────────────────
def kalimba(m, dur=1.4, vel=1.0):
    f, t = mtof(m), tt(dur)
    y = np.sin(2 * np.pi * f * t) * np.exp(-t * 4.2)
    y += 0.35 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 26)
    y += 0.12 * np.sin(2 * np.pi * f * 8.9 * t) * np.exp(-t * 50)
    y *= np.clip(t / 0.0015, 0, 1)
    return vel * y


def marimba(m, dur=0.7, vel=1.0):
    f, t = mtof(m), tt(dur)
    y = np.sin(2 * np.pi * f * t) * np.exp(-t * 7)
    y += 0.25 * np.sin(2 * np.pi * f * 3.93 * t) * np.exp(-t * 30)
    y += 0.08 * np.sin(2 * np.pi * f * 9.2 * t) * np.exp(-t * 70)
    y *= np.clip(t / 0.001, 0, 1)
    return vel * y


def bass(m, dur=0.45, vel=1.0):
    f, t = mtof(m), tt(dur + 0.08)
    y = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) + 0.1 * np.sin(6 * np.pi * f * t)
    y = np.tanh(1.6 * y) * adsr(len(t), 0.004, 0.07, dur) * np.exp(-t * 1.6)
    return vel * lp(y, 1400)


def pad(notes, dur, vel=1.0):
    t = tt(dur)
    y = np.zeros_like(t)
    for m in notes:
        f = mtof(m)
        for dt in (-0.07, 0.0, 0.07):
            ph = 2 * np.pi * f * 2 ** (dt / 12) * t + RNG.uniform(0, 6.28)
            y += (2 * ((ph / (2 * np.pi)) % 1) - 1) * 0.33
    y = lp(y, 2200, 2) * adsr(len(t), 0.35, 0.6, dur - 0.6)
    return vel * y / max(1, len(notes))


def whistle(notes, dur):
    """notes: [(start_s, midi, len_s)] — one continuous breathy tone with glides + vibrato."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    fr = np.full(n, mtof(notes[0][1]))
    amp = np.zeros(n)
    prev = mtof(notes[0][1])
    for (s, m, L) in notes:
        i0, i1 = int(s * SR), min(n, int((s + L) * SR))
        f = mtof(m)
        g = np.clip((t[i0:i1] - s) / 0.035, 0, 1)
        fr[i0:i1] = prev + (f - prev) * g
        fr[i1:] = f
        tl = t[i0:i1] - s
        amp[i0:i1] = np.maximum(amp[i0:i1], np.clip(tl / 0.02, 0, 1) * np.clip((L - tl) / 0.05, 0, 1))
        prev = f
    vib = 1 + 0.006 * np.sin(2 * np.pi * 5.6 * t) * np.clip((t % 1.0) / 0.3, 0, 1)
    ph = 2 * np.pi * np.cumsum(fr * vib) / SR
    y = np.sin(ph) + 0.06 * np.sin(3 * ph)
    breath = bp(noise(dur), 1500, 5000) * 0.05
    return lp((y + breath) * amp, 7000)


def kick(vel=1.0):
    t = tt(0.4)
    f = 45 + 110 * np.exp(-t * 32)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 8)
    y += 0.3 * hp(noise(0.4), 2000) * np.exp(-t * 160)
    return vel * np.tanh(1.4 * y)


def clap(vel=1.0):
    n = noise(0.3)
    t = tt(0.3)
    e = sum(np.exp(-np.maximum(t - d, 0) * 150) * (t >= d) for d in (0, 0.009, 0.018)) + 0.6 * np.exp(-np.maximum(t - 0.026, 0) * 16) * (t >= 0.026)
    return vel * bp(n, 900, 4800) * e * 0.8


def hat(vel=1.0, dec=45):
    t = tt(0.12)
    return vel * hp(noise(0.12), 7000) * np.exp(-t * dec) * 0.5


def shaker(vel=1.0):
    t = tt(0.1)
    return vel * bp(noise(0.1), 3500, 9000) * np.clip(t / 0.01, 0, 1) * np.exp(-t * 40) * 0.5


def snare(vel=1.0):
    t = tt(0.25)
    y = 0.6 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30) + bp(noise(0.25), 1200, 8000) * np.exp(-t * 18)
    return vel * y * 0.7
