"""Sound effects, one function per cue name emitted by the page (window.getCues())."""
import numpy as np
from audio_core import SR, tt, noise, lp, hp, bp, env, kick, clap, snare, RNG


def _mix(*xs):
    n = max(len(x) for x in xs)
    return sum(np.pad(x, (0, n - len(x))) for x in xs)


def _sweep(dur, a, b):
    t = tt(dur)
    f = a * (b / a) ** (t / dur)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def whoosh(dur=0.5, rev=0, **_):
    t = tt(dur); u = t / dur
    n = noise(dur)
    y = lp(n, 900) * (1 - u) + bp(n, 1500, 7000) * u
    e = np.sin(np.pi * np.clip(u, 0, 1)) ** 2
    y = y * e * 0.6
    return y[::-1] if rev else y


def swish(**k): return whoosh(0.28, **k) * 0.8
def slide(**k): return whoosh(0.35) * 0.5
def sheet(rev=0, **_): return whoosh(0.32, rev) * 0.45
def iris(rev=0, **_): return whoosh(0.45, rev) * 0.7
def swing(**_): return lp(whoosh(0.42), 3000) * 1.4


def thwack(pitch=1.0, **_):
    t = tt(0.35)
    snap = hp(noise(0.35), 3000) * np.exp(-t * 90)
    tone = np.sin(2 * np.pi * np.cumsum(900 + 600 * pitch - 400 * t / 0.35) / SR) * np.exp(-t * 38)
    body = np.sin(2 * np.pi * 170 * t) * np.exp(-t * 25)
    return np.tanh(1.5 * (snap * 0.9 + tone * 0.6 + body * 0.5))


def tock(**_):
    t = tt(0.2)
    return (np.sin(2 * np.pi * 1050 * t) * np.exp(-t * 45) + 0.5 * hp(noise(0.2), 2500) * np.exp(-t * 120)) * 0.6


def boom(**_):
    t = tt(1.4)
    sub = _sweep(1.4, 75, 38) * np.exp(-t * 2.4)
    rum = lp(noise(1.4), 180) * np.exp(-t * 3) * 0.8
    return np.tanh(1.3 * (sub + rum)) * 0.9


def bump(**_):
    t = tt(0.25)
    return np.sin(2 * np.pi * np.cumsum(90 + 90 * np.exp(-t * 30)) / SR) * np.exp(-t * 16) * 0.8


def thud(**_): return np.tanh(1.5 * bump()) + 0.3 * lp(noise(0.25), 500) * np.exp(-tt(0.25) * 20)


def pop(pitch=0.5, **_):
    t = tt(0.16)
    f0 = 520 * 2 ** (pitch * 1.3)
    return np.sin(2 * np.pi * np.cumsum(f0 * (1 + 1.6 * np.exp(-t * 60))) / SR) * np.exp(-t * 28) * 0.7


def boop(**_): return pop(0.1) * 0.8


def boing(**_):
    t = tt(0.55)
    f = 260 * (1 + 0.9 * t / 0.55) * (1 + 0.18 * np.sin(2 * np.pi * 14 * t) * np.exp(-t * 3))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6) * 0.5


def tick(pitch=0.5, **_):
    t = tt(0.07)
    return (np.sin(2 * np.pi * 1600 * 2 ** pitch * t) * np.exp(-t * 90) + 0.4 * hp(noise(0.07), 5000) * np.exp(-t * 300)) * 0.55


def click(**_):
    t = tt(0.05)
    return hp(noise(0.05), 3000) * np.exp(-t * 260) * 0.7 + np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 200) * 0.3


def tap(**_): return _mix(click() * 0.8, bump() * 0.3)


def stamp(pitch=0.5, **_):
    t = tt(0.3)
    low = np.sin(2 * np.pi * np.cumsum(140 + 90 * pitch + 120 * np.exp(-t * 50)) / SR) * np.exp(-t * 22)
    pap = bp(noise(0.3), 700, 3500) * np.exp(-t * 45)
    return np.tanh(1.4 * (low * 0.9 + pap * 0.6)) * 0.8


def chime(pitch=0.5, **_):
    t = tt(1.2)
    f = 1318.5 * 2 ** (pitch * 0.5)
    y = np.sin(2 * np.pi * f * t + 1.6 * np.exp(-t * 6) * np.sin(2 * np.pi * f * 3.5 * t))
    y += 0.4 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 5)
    return y * np.exp(-t * 3.2) * 0.35


def ding(**_):
    t = tt(2.6)
    y = 0.0
    for m, a, d in ((1, 1, 1.4), (2.01, .5, 2.5), (3.0, .25, 3.5), (4.17, .15, 5)):
        y = y + a * np.sin(2 * np.pi * 1174.7 * m * t) * np.exp(-t * d)
    return y * 0.4


def zip(**_):
    t = tt(0.4)
    return (_sweep(0.4, 300, 2400) * 0.4 + bp(noise(0.4), 2000, 8000) * 0.5) * np.sin(np.pi * t / 0.4) * 0.6


def rise(dur=0.5, **_):
    t = tt(dur); u = t / dur
    n = noise(dur)
    y = (lp(n, 600) * (1 - u) + bp(n, 1200, 9000) * u) * u ** 2 * 0.5
    return y + _sweep(dur, 300, 1400) * u ** 2 * 0.15


def scribble(**_):
    t = tt(0.45)
    am = np.clip(np.sin(2 * np.pi * 13 * t), 0, 1) ** 2
    return bp(noise(0.45), 2500, 7500) * am * np.sin(np.pi * t / 0.45) * 0.45


def shutter(**_):
    y = np.zeros(int(0.2 * SR)); c = click() * 1.3
    y[:len(c)] += c; i = int(0.07 * SR); y[i:i + len(c)] += c * 0.8
    return y + lp(noise(0.2), 1500) * np.exp(-tt(0.2) * 30) * 0.3


def hit(**_): return np.tanh(1.5 * (kick() * 0.9 + np.pad(clap(), (0, int(0.1 * SR)))[: int(0.4 * SR)] * 0.8))


def ratchet(dur=1.0, **_):
    y = np.zeros(int(dur * SR)); tc = 0.0
    c = tick(0.8) * 0.6
    while tc < dur - 0.05:
        u = tc / dur
        i = int(tc * SR); y[i:i + len(c)] += c[: max(0, len(y) - i)]
        tc += 0.018 + 0.09 * u ** 2
    return y


def lock(pitch=0.0, **_):
    t = tt(0.25)
    y = np.sin(2 * np.pi * (620 + 200 * pitch) * t) * np.exp(-t * 30) + np.sin(2 * np.pi * (1480 + 300 * pitch) * t) * np.exp(-t * 55) * 0.5
    return (y + hp(noise(0.25), 3000) * np.exp(-t * 140) * 0.6) * 0.7


def slam(**_):
    k = kick(); s = np.pad(snare(), (0, len(k) - len(snare()))) if len(snare()) < len(k) else snare()[: len(k)]
    return np.tanh(1.8 * (k + 0.8 * s + 0.5 * lp(noise(0.4), 3000) * np.exp(-tt(0.4) * 10)))


def slowdown(**_):
    t = tt(1.2)
    return (_sweep(1.2, 900, 120) * 0.35 + lp(noise(1.2), 1200) * 0.3) * np.exp(-t * 1.5) * np.clip(t / 0.05, 0, 1)


def speedup(**_): return rise(0.35) * 0.8


def blip(pitch=0.5, **_):
    d = 0.065 + 0.02 * pitch
    t = tt(d)
    f = 620 * 2 ** (pitch * 0.9) * (1 + 0.12 * t / d)
    tri = 2 / np.pi * np.arcsin(np.sin(2 * np.pi * np.cumsum(f) / SR))
    return bp(tri, 400, 4000) * np.sin(np.pi * t / d) ** 0.7 * 0.4


FX = {k: v for k, v in globals().items() if callable(v) and not k.startswith("_") and k not in
      ("tt", "noise", "lp", "hp", "bp", "env", "kick", "clap", "snare", "RNG", "SR")}
SEND = {"ding": .5, "chime": .45, "boom": .25, "pop": .15, "boing": .2, "thwack": .2, "slam": .25, "whoosh": .1, "blip": .08}
