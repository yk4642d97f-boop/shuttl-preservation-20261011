"""Sound effects for promo2, one function per cue name the page emits (window.getCues()).

Builds on the first film's palette (audio_sfx.py) and adds the colder, more synthetic sounds this one needs:
tape scrub, data keys, packets, plate thunks, chord stabs, impacts.
"""
import numpy as np

from audio_core import SR, tt, noise, lp, hp, bp, kick as _kick, RNG
import audio_sfx as base


def _st(y, pan):
    a = (pan + 1) * np.pi / 4
    return np.stack([y * np.cos(a), y * np.sin(a)]) * np.sqrt(2)


def _sweep(dur, a, b):
    t = tt(dur)
    f = a * (b / a) ** (t / dur)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def scrub(rate=60, v=(), **_):
    """Tape being dragged: noise and a buzzing tone whose pitch and level follow the playhead speed."""
    v = np.abs(np.asarray(v, float))
    n = int(len(v) / rate * SR)
    sp = np.interp(np.arange(n) / SR * rate, np.arange(len(v)), v)
    sp = lp(sp, 40, 1)
    amp = np.clip(sp / 2.0, 0, 1) ** 0.6
    f = 70 + 520 * np.clip(sp, 0, 4)
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = (2 * ((ph / (2 * np.pi)) % 1) - 1) * 0.5 + np.sin(ph * 2.01) * 0.3
    nz = noise(n / SR)
    # crude time-varying filter: crossfade two bands by speed
    lo, hi = bp(nz, 300, 1500), bp(nz, 1500, 7000)
    m = np.clip(sp / 2.5, 0, 1)
    y = (lo * (1 - m) + hi * m) * 0.9 + lp(tone, 2500) * 0.55
    y = y * amp
    # small sprocket clicks every ~10 tape-frames
    pos = np.cumsum(sp) / SR * 40
    clicks = np.diff(np.floor(pos), prepend=0) > 0
    y += hp(clicks.astype(float), 2000) * 0.8 * amp
    return np.tanh(y * 1.4) * 0.55


def key(pitch=0.0, gain=None, **_):
    """A data key: short sine + click. pitch in steps of a whole tone."""
    t = tt(0.06)
    f = 880 * 2 ** (pitch / 6)
    y = np.sin(2 * np.pi * f * t) * np.exp(-t * 70) + 0.5 * hp(noise(0.06), 4000) * np.exp(-t * 400)
    return y * 0.55


def stretch(dur=0.6, **_):
    t = tt(dur); u = t / dur
    f = 160 * (5 ** (np.sin(u * np.pi / 2)))
    y = np.sin(2 * np.pi * np.cumsum(f * (1 + 0.04 * np.sin(2 * np.pi * 22 * t))) / SR)
    return y * np.sin(np.pi * u) ** 0.6 * 0.32


def pen(dur=0.45, **_):
    t = tt(dur)
    am = 0.5 + 0.5 * np.sin(2 * np.pi * 17 * t) ** 2
    return bp(noise(dur), 2500, 7000) * am * np.sin(np.pi * t / dur) * 0.4


def rec(**_):
    y = np.zeros(int(0.32 * SR)); t = tt(0.07)
    b = np.sin(2 * np.pi * 1320 * t) * np.clip(t / 0.003, 0, 1) * np.clip((0.07 - t) / 0.01, 0, 1) * 0.4
    y[:len(b)] += b; i = int(0.12 * SR); y[i:i + len(b)] += b * 1.1
    return y


def drop(**_):
    t = tt(0.6)
    return (lp(noise(0.6), 900) * np.sin(np.pi * t / 0.6) * 0.5 + _sweep(0.6, 400, 70) * 0.25 * np.exp(-t * 2)) * 0.8


def packets(dur=1.0, **_):
    n = int(dur * SR)
    out = np.zeros((2, n + SR // 4))
    tc = 0.0; k = 0
    while tc < dur:
        u = tc / dur
        f = 1200 * 2 ** (RNG.integers(0, 24) / 12 + u)
        d = 0.03
        t = tt(d)
        y = np.sin(2 * np.pi * f * t) * np.exp(-t * 120) * 0.3
        i = int(tc * SR)
        out[:, i:i + len(y)] += _st(y, RNG.uniform(-0.8, 0.8))
        tc += 0.045 * (1 - 0.75 * u) + 0.01 * RNG.random(); k += 1
    return out


def ok(pitch=0, **_):
    notes = [62, 65, 67, 69, 72, 74, 77]
    m = notes[int(pitch) % len(notes)] + 12
    f = 440 * 2 ** ((m - 69) / 12)
    t = tt(0.25)
    y = np.sin(2 * np.pi * f * t + 0.8 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 20)) * np.exp(-t * 14)
    return y * 0.35


def suck(dur=0.36, **_):
    return base.whoosh(dur, rev=1) * 0.9 + _sweep(dur, 120, 900)[: int(dur * SR)] * np.linspace(0, 1, int(dur * SR)) ** 3 * 0.15


def plate(pitch=0, **_):
    """Printing-press thunk: a dead low hit and an inharmonic metal clank."""
    t = tt(0.6)
    thud = np.sin(2 * np.pi * np.cumsum(70 + 90 * np.exp(-t * 40)) / SR) * np.exp(-t * 12)
    f0 = 310 * 2 ** (pitch * 0.25)
    clank = sum(a * np.sin(2 * np.pi * f0 * r * t) * np.exp(-t * d) for r, a, d in ((1, 1, 9), (2.76, .6, 14), (5.4, .4, 22), (8.93, .25, 30)))
    return np.tanh(1.5 * (thud * 0.9 + clank * 0.35 + hp(noise(0.6), 3000) * np.exp(-t * 80) * 0.4)) * 0.8


# D phrygian-ish cluster voicings for the shot strobes
_STAB = [(50, 53, 57, 60), (48, 55, 58, 62), (51, 55, 58, 62), (53, 57, 60, 64), (46, 53, 57, 60), (50, 55, 57, 62),
         (48, 52, 55, 59), (51, 58, 62, 65), (53, 56, 60, 63), (45, 52, 57, 59)]


def stab(pitch=0, **_):
    t = tt(0.45)
    y = np.zeros_like(t)
    for m in _STAB[int(pitch) % len(_STAB)]:
        f = 440 * 2 ** ((m + 12 - 69) / 12)
        for dt in (-0.08, 0.08):
            ph = 2 * np.pi * f * 2 ** (dt / 12) * t
            y += (2 * ((ph / (2 * np.pi)) % 1) - 1)
    env = np.exp(-t * 9)
    y = lp(y * env, 3800) / 8
    return np.tanh(2 * y) * 0.7 + hp(noise(0.45), 5000) * np.exp(-t * 60) * 0.25


def impact(pitch=0, **_):
    t = tt(2.2)
    crash = hp(noise(2.2), 4000) * np.exp(-t * 2.2) * 0.45
    sub = np.sin(2 * np.pi * np.cumsum(55 * 2 ** (pitch / 12) + 60 * np.exp(-t * 18)) / SR) * np.exp(-t * 3.5)
    s = base.slam()
    hit = np.pad(s, (0, max(0, len(t) - len(s))))[: len(t)]
    return np.tanh(1.3 * (crash + sub * 0.9 + hit * 0.7)) * 0.85


def shimmer(dur=3.0, **_):
    n = int(dur * SR)
    out = np.zeros((2, n + SR // 2))
    tc = 0.0
    scale = [74, 77, 79, 81, 84, 86, 89, 91, 93]
    while tc < dur:
        m = scale[RNG.integers(0, len(scale))]
        f = 440 * 2 ** ((m - 69) / 12)
        t = tt(0.4)
        y = np.sin(2 * np.pi * f * t) * np.exp(-t * 9) * 0.12 * np.sin(np.pi * min(1, tc / dur)) ** 0.5
        i = int(tc * SR)
        out[:, i:i + len(y)] += _st(y, RNG.uniform(-0.9, 0.9))
        tc += 0.035 + 0.03 * RNG.random()
    return out


def press(dur=0.45, **_):
    t = tt(dur)
    f = 330 * 2 ** (1.6 * t / dur)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * (0.6 + 0.4 * np.sin(2 * np.pi * 24 * t))
    return y * np.clip(t / 0.02, 0, 1) * 0.3


def kick(gain=None, **_):
    return _kick()


FX = dict(base.FX)
FX.update({k: v for k, v in dict(scrub=scrub, key=key, stretch=stretch, pen=pen, rec=rec, drop=drop, packets=packets, ok=ok,
                                      suck=suck, plate=plate, stab=stab, impact=impact, shimmer=shimmer, press=press, kick=kick).items()})
SEND = dict(base.SEND)
SEND.update({"stab": .3, "impact": .35, "plate": .25, "ok": .2, "key": .06, "shimmer": .5, "press": .2, "stamp": .2})
