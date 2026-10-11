"""Arrangement + mix: 120 BPM, D major, 38 bars (76 s). Cues from the page are layered on top.

usage: python audio_music.py cues.json out.wav
"""
import json
import sys

import numpy as np
from scipy.io import wavfile

from audio_core import SR, Bus, lp, hp, reverb, reverb_ir, kalimba, marimba, bass, pad, whistle, kick, clap, hat, shaker, snare
from audio_sfx import FX, SEND

DUR, BEAT = 76.0, 0.5
CH = {"D": (38, [62, 66, 69, 73]), "Bm": (35, [62, 66, 69, 71]), "G": (43, [62, 66, 67, 71]), "A7s": (45, [62, 64, 67, 69]),
      "A7": (45, [61, 64, 67, 69]), "A": (45, [61, 64, 69, 71]), "F#m": (42, [61, 64, 66, 69]), "Gm6": (43, [62, 64, 67, 70]),
      "Em7": (40, [62, 64, 67, 71])}
BARS = ("D Bm A7s D Bm G A7s D Bm G A7s D Bm G A F#m Bm Gm6 A7 D Bm G A F#m Bm G A F#m Bm G A F#m Bm Em7 Gm6 A7 D D").split()
GROOVE = set(range(3, 19)) | set(range(19, 34))
CHORUS = set(range(19, 34))
MUTE = [(31.72, 34.1), (37.0, 38.0), (68.0, 70.0), (70.5, 99)]
FILLS = [11.5, 19.5, 41.5, 47.5, 53.5, 59.5, 63.5, 67.5]
PH = {
    "A": [(0, 74, .5), (.5, 76, .5), (1, 78, 1), (2, 76, .5), (2.5, 74, .5), (3, 81, 1.25), (4.5, 78, .5), (5, 76, .5), (5.5, 74, .5), (6, 73, 1), (7, 71, .75)],
    "B": [(0, 74, .5), (.5, 76, .5), (1, 78, .5), (1.5, 79, 1), (2.5, 78, .5), (3, 76, 1), (4, 74, .5), (4.5, 76, .5), (5, 79, .5), (5.5, 81, 1.5), (7, 79, .5), (7.5, 76, .5)],
    "C": [(0, 83, .75), (.75, 81, .25), (1, 79, .5), (1.5, 81, .5), (2, 83, 1), (3, 86, 1), (4, 85, .75), (4.75, 83, .25), (5, 81, .5), (5.5, 78, .5), (6, 76, 1.5), (7.5, 78, .5)],
    "D": [(0, 81, .5), (.5, 78, .5), (1, 76, .5), (1.5, 78, 1), (2.5, 81, .5), (3, 85, 1), (4, 83, 1.5), (5.5, 81, .5), (6, 78, .5), (6.5, 74, .5), (7, 71, 1)],
    "E": [(.5, 78, .5), (1, 81, .5), (1.5, 86, 2.5)],
}
MEL = {3: "A", 5: "B", 7: "A", 9: "B", 13: "C", 19: "A", 21: "C", 23: "D", 25: "C", 27: "D", 29: "C", 31: "D", 36: "E"}
KALI = {0: 1, 1: 1, 2: 2, 10: 2, 11: 2, 12: 2, 16: 1, 34: 2, 35: 1, 36: 3, 37: 1}


def muted(t):
    return any(a <= t < b for a, b in MUTE)


def build():
    mus, drm, snd = Bus(DUR), Bus(DUR), Bus(DUR)
    kicks = []
    for b, name in enumerate(BARS):
        t0, (root, vo) = b * 2.0, CH[name]
        if b < 36:
            mus.add(pad(vo, 2.6, 1.0), t0, 0, 0.2)
            snd.add(pad(vo, 2.6, 1.0), t0, 0, 0.2 * 0.35)
        if b == 36:
            p = pad(CH["D"][1] + [74], 4.2, 1.0); mus.add(p, t0, 0, 0.26); snd.add(p, t0, 0, 0.12)
        if b in GROOVE and not (31.7 < t0 + 1 < 34.1):
            for bt, n, L, v in [(0, root, .4, 1), (.75, root, .2, .7), (1.5, root + 12, .3, .8), (2, root, .4, 1), (3, root + 7, .35, .8), (3.5, root + 12, .3, .7)]:
                mus.add(bass(n, L, v), t0 + bt * BEAT, 0, 0.5)
            top = [m + 12 for m in vo[-2:]]
            for bt in (.5, 1.5, 2.25, 3.0, 3.5):
                for m in top:
                    mus.add(marimba(m, .6, .8), t0 + bt * BEAT, 0.35, 0.26)
                    snd.add(marimba(m, .6, .8), t0 + bt * BEAT, 0.35, 0.03)
        elif b in (0, 1, 2, 16, 34, 35, 36):
            L = 3.6 if b == 36 else 1.9
            mus.add(bass(root, L, .9), t0, 0, 0.45)
        if b in KALI:
            mode, notes = KALI[b], [m + 12 for m in vo]
            steps = [(i * 1.0, notes[i % 4]) for i in range(4)] if mode == 1 else \
                    [(i * .5, notes[[0, 1, 2, 3, 2, 1, 2, 3][i]]) for i in range(8)] if mode == 2 else \
                    [(i * .125, notes[i % 4] + 12 * (i // 4)) for i in range(12)]
            for bt, m in steps:
                k = kalimba(m, 1.6, .8)
                mus.add(k, t0 + bt * BEAT, -0.35, 0.22); snd.add(k, t0 + bt * BEAT, -0.35, 0.1)
        if b in MEL:
            w = whistle([(s * BEAT, m, L * BEAT) for s, m, L in PH[MEL[b]]], 4.6)
            mus.add(w, t0, 0, 0.2); mus.add(w, t0 + 0.1875, -0.7, 0.05); mus.add(w, t0 + 0.375, 0.7, 0.03)
            snd.add(w, t0, 0, 0.07)
        if b in GROOVE:
            ks = [0, 1.5, 2] + ([3.75] if b in CHORUS else [])
            for bt in ks:
                t = t0 + bt * BEAT
                if not muted(t): drm.add(kick(), t, 0, 0.8); kicks.append(t)
            for bt in (1, 3):
                t = t0 + bt * BEAT
                if not muted(t): drm.add(clap(), t, 0.05, 1.0); snd.add(clap(), t, 0, 0.2)
            for i in range(8):
                t = t0 + i * 0.25
                if not muted(t): drm.add(hat(1 if i % 2 else .5, 55 if i % 2 else 80), t, 0.2, 0.16)
            if b in CHORUS:
                for i in range(16):
                    t = t0 + i * 0.125
                    if not muted(t): drm.add(shaker(.6 + .4 * (i % 2)), t, -0.3, 0.1)
    for f in FILLS:
        for i in range(4):
            if not muted(f + i * 0.125): drm.add(snare(.5 + .15 * i), f + i * 0.125, 0, 0.42)
    for i in range(8):
        drm.add(snare(.35 + .08 * i), 70.0 + i * 0.0625, 0, 0.45)
    return mus, drm, snd, kicks


def sidechain(n, kicks, depth=0.55, rel=0.22):
    g = np.ones(n)
    for k in kicks:
        i = int(k * SR); L = min(n - i, int(0.4 * SR))
        if L > 0:
            t = np.arange(L) / SR
            g[i:i + L] = np.minimum(g[i:i + L], 1 - depth * np.exp(-t / rel * 3))
    return g


def window_filter(x, a, b, f, fade=0.08):
    """Crossfade to a low-passed copy between a and b."""
    wet = np.stack([lp(x[c], f, 4) for c in range(2)])
    t = np.arange(x.shape[1]) / SR
    m = np.clip(np.minimum((t - a) / fade, (b - t) / fade), 0, 1)
    return x * (1 - m) + wet * m


def main(cues_path, out):
    mus, drm, snd, kicks = build()
    n = mus.x.shape[1]
    sc = sidechain(n, kicks)
    music = mus.x * sc
    drums = window_filter(drm.x, 20.4, 26.0, 700)
    music = window_filter(music + drums, 31.8, 34.05, 900, 0.15)
    sfx, sfxr = Bus(DUR), Bus(DUR)
    for c in json.load(open(cues_path)):
        fn = FX.get(c["name"])
        if fn is None:
            print("missing sfx", c["name"]); continue
        kw = {k: v for k, v in c.items() if k in ("pitch", "dur", "rev")}
        y = fn(**kw)
        g = c.get("gain", 1.0) * (0.42 if c["name"] == "blip" else 0.6)
        pan = 0.0 if c["name"] != "blip" else 0.1
        sfx.add(y, c["t"], pan, g)
        if c["name"] in SEND: sfxr.add(y, c["t"], pan, g * SEND[c["name"]])
    wet = reverb(snd.x + sfxr.x, reverb_ir())
    mix = music / (np.sqrt(np.mean(music ** 2)) + 1e-9) * 0.085 + sfx.x * 0.9 + wet * 0.5
    mix = np.stack([lp(hp(mix[c], 30), 16000, 4) for c in range(2)])
    lvl = np.sqrt(np.convolve(np.mean(mix ** 2, 0), np.ones(2400) / 2400, "same")) + 1e-9
    gain = np.minimum(1, (0.25 / lvl) ** 0.35)
    mix = mix * gain
    mix = mix / np.sqrt(np.mean(mix ** 2)) * 0.15
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    N = int(DUR * SR); mix = mix[:, :N]
    t = np.arange(N) / SR
    mix *= np.clip(t / 0.01, 0, 1) * np.clip((DUR - t) / 1.2, 0, 1)
    mix = mix / np.max(np.abs(mix)) * 0.79
    print(f"rms {20 * np.log10(np.sqrt(np.mean(mix ** 2))):.1f} dBFS  peak {20 * np.log10(np.max(np.abs(mix))):.1f} dBFS  nan {np.isnan(mix).any()}")
    wavfile.write(out, SR, (mix.T * 32767).astype(np.int16))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
