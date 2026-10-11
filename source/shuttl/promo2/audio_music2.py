"""Soundtrack for promo2: 120 BPM, 60 s, D phrygian. Synthesised from scratch (numpy/scipy), cues from the page on top.

Shape follows the cut: no pulse while the tape is searched, a single slam on "你只管打", a thin record pulse, rising
packets into the cloud; the rally's thirteen real hit times play against a 3+3+2 groove; total silence on the landing;
a UI groove for the scorecard; the peak on the stats with a tape-stop; a heartbeat for the correction; one chord to end.

usage: python audio_music2.py cues.json out.wav
"""
import json
import sys

import numpy as np
from scipy.io import wavfile

from audio_core import SR, Bus, lp, hp, bp, reverb, reverb_ir, kick, clap, hat, snare, tt, noise, mtof, adsr, RNG
from audio_fx import FX, SEND

DUR = 60.0
B16 = 0.125


# ── voices ────────────────────────────────────────────────────────────────────
def sub(m, dur, vel=1.0):
    t = tt(dur + 0.05)
    y = np.sin(2 * np.pi * mtof(m) * t)
    return vel * y * adsr(len(t), 0.01, 0.08, dur)


def fmbass(m, dur=0.22, vel=1.0, bright=1.0):
    f, t = mtof(m), tt(dur + 0.06)
    idx = 2.6 * bright * np.exp(-t * 14)
    y = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t))
    y += 0.6 * np.sin(np.pi * f * t)
    y = np.tanh(1.8 * y) * adsr(len(t), 0.003, 0.05, dur)
    return vel * lp(y, 2600)


def pluck(m, dur=0.5, vel=1.0):
    f, t = mtof(m), tt(dur)
    y = np.sin(2 * np.pi * f * t + 1.4 * np.exp(-t * 18) * np.sin(2 * np.pi * f * 3.01 * t))
    return vel * y * np.exp(-t * 7) * np.clip(t / 0.002, 0, 1)


def ping(f, vel=1.0):
    t = tt(0.05)
    return vel * np.sin(2 * np.pi * f * t) * np.exp(-t * 110)


def cluster(notes, dur, vel=1.0, cut=1800):
    t = tt(dur)
    y = np.zeros_like(t)
    for m in notes:
        for d in (-0.1, 0.0, 0.1):
            ph = 2 * np.pi * mtof(m) * 2 ** (d / 12) * t + RNG.uniform(0, 6.28)
            y += np.sin(ph) * 0.6 + (2 * ((ph / (2 * np.pi)) % 1) - 1) * 0.25
    return vel * lp(y, cut) * adsr(len(t), 0.4, 0.8, dur - 0.8) / len(notes)


def rim(vel=1.0):
    t = tt(0.06)
    return vel * (np.sin(2 * np.pi * 1750 * t) * np.exp(-t * 160) + bp(noise(0.06), 2000, 6000) * np.exp(-t * 220)) * 0.5


def ohat(vel=1.0):
    t = tt(0.3)
    return vel * hp(noise(0.3), 6500) * np.exp(-t * 11) * 0.45


def crash(vel=1.0):
    t = tt(2.0)
    return vel * hp(noise(2.0), 3500) * np.exp(-t * 1.8) * 0.4


# ── arrangement ───────────────────────────────────────────────────────────────
D = 38  # D2

def build(cues):
    mus, drm, wet = Bus(DUR), Bus(DUR), Bus(DUR)
    kicks = []

    def K(t, g=0.9, side=True):
        drm.add(kick(), t, 0, g)
        if side: kicks.append(t)

    # 0–6 · tape: low drone + Ikeda pings, no pulse
    drone = sub(D, 5.6, 0.45)
    mus.add(drone * np.linspace(0, 1, len(drone)) ** 0.7, 0.2, 0, 0.6)
    for i in range(46):
        t = 0.1 + RNG.random() * 5.5
        mus.add(ping(2000 + 6000 * RNG.random(), 0.5), t, RNG.uniform(-.8, .8), 0.25)
    mus.add(cluster([D + 24, D + 27, D + 31], 5.8, 1.0, 1200), 0.0, 0, 0.12)

    # 6–8 · PLAY: slam + one long sub, silence around it
    K(6.0, 1.1); mus.add(sub(D, 1.4, 1.0), 6.0, 0, 0.7)
    mus.add(fmbass(D, 0.4, 1.0, 1.5), 7.5, 0, 0.6); K(7.5, 1.0)

    # 8–10.5 · record: soft pulse, euclidean rims
    euclid5 = [0, 3, 6, 10, 13]
    for b in range(5):
        t0 = 8.0 + b * 0.5
        K(t0, 0.55)
    for bar in range(2):
        for s in euclid5:
            t = 8.0 + bar * 2 + s * B16
            if t < 10.5: drm.add(rim(.7), t, 0.3, 0.5)
    mus.add(fmbass(D, 1.8, 0.7, 0.5), 8.0, 0, 0.45); mus.add(fmbass(D + 1, 0.4, 0.6, 0.6), 9.75, 0, 0.35)

    # 10.5–14 · upload: rising arpeggio, hats thicken, reese enters on GPU
    arp = [0, 3, 7, 10, 12, 15, 19, 22]
    for i in range(int((12.2 - 10.6) / (B16 / 2))):
        t = 10.6 + i * B16 / 2
        m = D + 36 + arp[i % len(arp)] + 12 * (i // 16)
        mus.add(pluck(min(m, D + 72), 0.25, 0.5 + 0.5 * i / 26), t, (i % 2) * .6 - .3, 0.2)
    for i in range(int((13.6 - 10.5) / B16)):
        t = 10.5 + i * B16
        drm.add(hat(0.4 + 0.6 * (i % 2), 70), t, 0.25, 0.1 + 0.12 * (t - 10.5) / 3)
    for b in range(4):
        K(12.0 + b * 0.5, 0.7)
    for t, m in ((12.2, D), (12.7, D), (13.2, D + 1)):
        y = fmbass(m, 0.45, 0.9, 1.2) + fmbass(m + 12, 0.45, 0.35, 0.6) * 0.5
        mus.add(y, t, 0, 0.5)

    # 14–28.63 · rally. Plate 1 sparse, plate 2 bass + clap, plate 3/4 full 3+3+2.
    LAND = None
    for c in cues:
        if c["name"] == "slam" and 28 < c["t"] < 29: LAND = c["t"]
    LAND = LAND or 28.63
    pat332 = [0, 3, 6, 8, 11, 14]
    bassline = [0, 0, 12, 0, 1, 0, 10, 12, 0, 0, 12, 0, 3, 1, 0, 10]
    t = 14.0
    while t < LAND - 1e-6:
        bar = int((t - 14.0) / 2)
        for s in range(16):
            ts = t + s * B16
            if ts >= LAND: break
            if ts < 18.0:
                if s in (0, 11): K(ts, 0.75)
                if s % 4 == 2: drm.add(rim(.5), ts, -0.3, 0.35)
            elif ts < 20.4:
                if s in (0, 6, 11): K(ts, 0.85)
                if s == 8: drm.add(clap(), ts, 0.05, 0.75)
                if s % 2 == 0: mus.add(fmbass(D + bassline[s], 0.2, 0.9, 0.8), ts, 0, 0.42)
                drm.add(hat(0.5 + 0.5 * (s % 2), 80), ts, 0.2, 0.08)
            else:
                if s in pat332: K(ts, 1.0)
                if s in (4, 12): drm.add(snare(0.9), ts, 0, 0.55); drm.add(clap(), ts, 0.05, 0.6)
                drm.add(hat(0.35 + 0.65 * (s % 2), 60 if s % 4 == 2 else 85), ts, 0.22, 0.12)
                mus.add(fmbass(D + bassline[s], 0.13, 1.0, 1.0 + 0.6 * (s % 3 == 0)), ts, 0, 0.45)
        if t >= 20.4:
            mus.add(cluster([D + 12, D + 15, D + 19, D + 22], 2.1, 1.0, 900 + 300 * (bar % 2)), t, 0, 0.09)
        t += 2.0

    # 30–38.55 · scorecard groove
    motif = [D + 31, D + 34, D + 36, D + 39, D + 41]
    t = 30.0
    while t < 38.55 - 1e-6:
        for s in range(16):
            ts = t + s * B16
            if ts >= 38.55: break
            if s in (0, 8): K(ts, 0.9)
            if s in (4, 12): drm.add(clap(), ts, 0.05, 0.55)
            if s % 2 == 1: drm.add(rim(0.6), ts, 0.35, 0.35)
            if s % 2 == 0: mus.add(pluck(motif[(s // 2 + int(t)) % 5], 0.35, 0.7), ts, -0.3, 0.16)
            if s in (0, 3, 6, 10, 12): mus.add(fmbass(D + (0 if s < 8 else 5 if t < 34 else 3), 0.22, 0.8, 0.7), ts, 0, 0.4)
        t += 2.0
    # 38.55–40 · roll + riser
    n = 0; ts = 38.55
    while ts < 39.95:
        u = (ts - 38.55) / 1.4
        drm.add(snare(0.3 + 0.6 * u), ts, 0, 0.5); ts += B16 * (1 - 0.7 * u); n += 1

    # 40–49.5 · stats: the peak, four-on-floor
    chords = {40: [D + 12, D + 15, D + 19, D + 22], 43: [D + 15, D + 19, D + 22, D + 26], 46: [D + 10, D + 14, D + 17, D + 21]}
    roots = {40: 0, 43: 3, 46: -2}
    for sec in (40, 43, 46):
        end = sec + 3 if sec < 46 else 49.5
        mus.add(crash(1.0), sec, 0.1, 0.55)
        ts = float(sec)
        k = 0
        while ts < end - 1e-6:
            s = k % 16
            if s % 4 == 0: K(ts, 1.0)
            if s in (4, 12): drm.add(clap(), ts, 0.05, 0.8)
            if s % 4 == 2: drm.add(ohat(0.8), ts, 0.25, 0.35)
            drm.add(hat(0.4 + 0.6 * (s % 2), 90), ts, -0.2, 0.09)
            mus.add(fmbass(D + roots[sec] + (12 if s % 4 == 2 else 0), 0.12, 1.0, 1.2), ts, 0, 0.45)
            if s % 4 == 0: mus.add(cluster(chords[sec], 0.42, 1.0, 2600), ts, 0, 0.13)
            ts += B16; k += 1

    # 50–56 · correction: heartbeat + clock, half-time after the stamp
    for i in range(int((53.5 - 50.0) / 0.5)):
        ts = 50.0 + i * 0.5
        K(ts, 0.55 if i % 2 == 0 else 0.35, side=False)
        drm.add(rim(0.5), ts + 0.25, 0.4, 0.3)
    mus.add(cluster([D + 12, D + 14, D + 19], 3.5, 1.0, 900), 50.0, 0, 0.1)
    for i in range(4):
        ts = 53.5 + i * 0.5
        if i % 2 == 0: K(ts, 0.95)
        else: drm.add(snare(0.8), ts, 0, 0.5)
        mus.add(fmbass(D + (0 if i < 2 else 3), 0.4, 0.9, 0.8), ts, 0, 0.42)
    mus.add(cluster([D + 15, D + 19, D + 22, D + 26], 2.4, 1.0, 1400), 53.5, 0, 0.12)

    # 56.5–60 · final chord: open D5 with a high E, held
    end = cluster([D, D + 7, D + 12, D + 19, D + 26, D + 31], 3.6, 1.0, 2400)
    mus.add(end, 56.5, 0, 0.32); wet.add(end, 56.5, 0, 0.25)
    mus.add(sub(D, 3.2, 1.0), 56.5, 0, 0.55)
    for i, m in enumerate([D + 43, D + 50, D + 55]):
        mus.add(pluck(m, 2.4, 0.6), 56.5 + 0.75 + i * 0.25, (i - 1) * .5, 0.18); wet.add(pluck(m, 2.4, 0.6), 56.5 + 0.75 + i * 0.25, 0, 0.12)
    return mus, drm, wet, kicks, LAND


def sidechain(n, kicks, depth=0.5, rel=0.18):
    g = np.ones(n)
    for k in kicks:
        i = int(k * SR); L = min(n - i, int(0.35 * SR))
        if L > 0:
            t = np.arange(L) / SR
            g[i:i + L] = np.minimum(g[i:i + L], 1 - depth * np.exp(-t / rel * 3))
    return g


def stutter(x, t, slice_len=B16 / 2, reps=4):
    """Repeat the slice just before t, `reps` times — a buffer glitch."""
    i, L = int(t * SR), int(slice_len * SR)
    seg = x[:, i - L:i].copy()
    fade = np.minimum(1, np.minimum(np.arange(L), L - np.arange(L)) / 64)
    for r in range(reps):
        a = i + r * L
        if a + L <= x.shape[1]:
            x[:, a:a + L] = seg * fade * (1 - 0.12 * r)
    return x


def tapestop(x, a, b):
    """Playback speed falls 1 → 0 between a and b; silence after b until the next section takes over."""
    ia, ib = int(a * SR), int(b * SR)
    n = ib - ia
    u = np.arange(n) / n
    pos = ia + np.cumsum((1 - u) ** 1.6)
    for c in range(2):
        x[c, ia:ib] = np.interp(pos, np.arange(x.shape[1]), x[c]) * (1 - u ** 3)
    return x


def gate(x, a, b, fade=0.004):
    t = np.arange(x.shape[1]) / SR
    m = np.clip(np.maximum((a - t) / fade, (t - b) / fade), 0, 1)
    return x * m


def main(cues_path, out):
    cues = json.load(open(cues_path))
    mus, drm, wet, kicks, LAND = build(cues)
    n = mus.x.shape[1]
    sc = sidechain(n, kicks)
    music = mus.x * sc + drm.x
    for t in (21.95, 23.95, 25.95, 27.95, 35.95, 42.75, 45.75):
        music = stutter(music, t, B16 / 2, 4)
    music = tapestop(music, 49.45, 50.0)
    # silences: the landing freeze, the gap before "你只管打", before the logo
    music = gate(music, LAND + 0.02, 29.98)
    music = gate(music, 5.82, 5.99)
    music = gate(music, 55.88, 56.48)
    sfx, sfxr = Bus(DUR), Bus(DUR)
    for c in cues:
        fn = FX.get(c["name"])
        if fn is None:
            print("missing sfx", c["name"]); continue
        kw = {k: v for k, v in c.items() if k not in ("t", "name", "gain")}
        y = fn(**kw)
        g = c.get("gain", 1.0) * 0.6
        sfx.add(y, c["t"], 0.0, g)
        if c["name"] in SEND: sfxr.add(y, c["t"], 0.0, g * SEND[c["name"]])
    rv = reverb(wet.x + sfxr.x + mus.x * 0.12, reverb_ir(2.4, 2.6))
    mm = music / (np.sqrt(np.mean(music ** 2)) + 1e-9) * 0.1
    mix = mm + sfx.x * 0.85 + rv * 0.45
    mix = np.stack([lp(hp(mix[c], 28), 17000, 4) for c in range(2)])
    lvl = np.sqrt(np.convolve(np.mean(mix ** 2, 0), np.ones(2400) / 2400, "same")) + 1e-9
    mix = mix * np.minimum(1, (0.24 / lvl) ** 0.4)
    mix = mix / np.sqrt(np.mean(mix ** 2)) * 0.16
    mix = np.tanh(mix * 1.15) / np.tanh(1.15)
    N = int(DUR * SR); mix = mix[:, :N]
    t = np.arange(N) / SR
    mix *= np.clip(t / 0.005, 0, 1) * np.clip((DUR - t) / 1.6, 0, 1)
    mix = mix / np.max(np.abs(mix)) * 0.84
    print(f"rms {20 * np.log10(np.sqrt(np.mean(mix ** 2))):.1f} dBFS  peak {20 * np.log10(np.max(np.abs(mix))):.1f} dBFS  nan {np.isnan(mix).any()}")
    wavfile.write(out, SR, (mix.T * 32767).astype(np.int16))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
