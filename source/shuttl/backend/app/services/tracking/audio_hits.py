"""Racket–shuttle impact evidence from the soundtrack (cloud worker; numpy/scipy + FFmpeg).

Why this exists
    A phone at the court records a short broadband "crack" at contact. On the public
    amateur rallies of kwyoke/Badminton-hit-detection the positive spectral flux in
    6–16 kHz separates labelled contacts from other in-rally instants (Cohen's d 0.88–1.10
    per venue). Broadcast soundtracks (FineBadminton-20K) showed no separation (d≈0:
    commentary, crowd, re-encoding), so this is evidence for phone recordings only and is
    gated per recording by `assess` — never assumed. See research/audio/REPORT.md.

Clocks
    Audio and video disagree by a per-recording constant (+14 / +100 / +110 ms on the three
    venues studied), larger than the ±2-frame scoring tolerance. The lag is therefore
    estimated against confident visual hits (`estimate_lag`) instead of trusting container
    timestamps. All times returned here are on the video clock *before* that correction;
    callers pass the estimated lag explicitly.

Cost
    Streaming: FFmpeg decodes mono 32 kHz PCM into a pipe and only 161 rFFT bins per 2 ms
    hop are kept. A 90-minute recording yields ~2.7 M floats (~11 MB); no full-length
    waveform or spectrogram is ever held in memory.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy import ndimage

SR = 32000
N_FFT = 512                    # 16 ms analysis window
HOP = 64                       # 2 ms hop
BAND_HZ = (6000.0, 16000.0)    # where contacts separate from rally noise (REPORT.md)
BLOCK_S = 0.1                  # robust normalisation is computed on 100 ms blocks …
NORM_BLOCKS = 15               # … over a running 1.5 s span
PEAK_HALF_S = 0.03             # an onset is the largest value within ±30 ms
CHUNK_S = 30.0                 # streaming chunk length


@dataclass
class ImpactCurve:
    """Robust z-score of 6–16 kHz onset strength, uniformly sampled every HOP samples."""
    t0: float                  # time of z[0] on the video clock (uncorrected for lag)
    dt: float                  # sample spacing (s)
    z: np.ndarray              # float32
    diagnostics: dict = field(default_factory=dict)

    @property
    def t(self) -> np.ndarray:
        return self.t0 + self.dt * np.arange(len(self.z))

    def index(self, times) -> np.ndarray:
        """Nearest sample index for each time (clipped to the curve)."""
        i = np.rint((np.asarray(times, np.float64) - self.t0) / self.dt).astype(np.int64)
        return np.clip(i, 0, max(len(self.z) - 1, 0))


# ── decoding ────────────────────────────────────────────────────────────────────────────

def stream_starts(path: str) -> tuple[float | None, float | None]:
    """(video start_time, first audio stream start_time) from the container, or None."""
    if shutil.which("ffprobe") is None:
        return None, None
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,start_time", "-of", "json", path],
        capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None, None
    video = audio = None
    for stream in json.loads(proc.stdout or "{}").get("streams", []):
        try:
            start = float(stream.get("start_time", 0.0))
        except (TypeError, ValueError):
            start = 0.0
        if stream.get("codec_type") == "video" and video is None:
            video = start
        elif stream.get("codec_type") == "audio" and audio is None:
            audio = start
    return video, audio


def _pcm_chunks(path: str, sr: int, chunk_s: float):
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-map", "0:a:0", "-vn",
           "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        need = int(chunk_s * sr) * 2
        while True:
            buf = proc.stdout.read(need)
            if not buf:
                break
            usable = len(buf) - (len(buf) % 2)
            yield np.frombuffer(buf[:usable], np.int16).astype(np.float32) / 32768.0
    finally:
        proc.stdout.close()
        err = proc.stderr.read().decode(errors="replace")[-400:]
        proc.stderr.close()
        code = proc.wait()
        if code != 0:
            raise RuntimeError(f"ffmpeg audio decode failed ({code}): {err}")


# ── onset strength ──────────────────────────────────────────────────────────────────────

class _Flux:
    """Positive log-magnitude flux averaged over the band, fed sample chunks in order."""

    def __init__(self, sr: int, band=BAND_HZ):
        self.sr = sr
        freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
        self.bins = np.flatnonzero((freqs >= band[0]) & (freqs <= band[1]))
        if len(self.bins) == 0:
            raise ValueError("Band is outside the sampled spectrum")
        self.window = np.hanning(N_FFT).astype(np.float32)
        self.tail = np.zeros(0, np.float32)    # samples not yet covered by a full hop
        self.prev = None                       # previous frame's log-magnitude band
        self.parts: list[np.ndarray] = []
        self.frames = 0

    def push(self, samples: np.ndarray):
        x = np.concatenate([self.tail, samples.astype(np.float32, copy=False)])
        if len(x) < N_FFT:
            self.tail = x
            return
        n = 1 + (len(x) - N_FFT) // HOP
        frames = sliding_window_view(x, N_FFT)[::HOP][:n] * self.window
        mag = np.abs(np.fft.rfft(frames, axis=1)[:, self.bins])
        log = np.log1p(1000.0 * mag).astype(np.float32)
        prev = log[:1] if self.prev is None else self.prev[None]
        diff = np.diff(np.concatenate([prev, log]), axis=0)
        self.parts.append(np.maximum(diff, 0.0).mean(axis=1).astype(np.float32))
        self.prev = log[-1]
        self.frames += n
        self.tail = x[n * HOP:]

    def result(self) -> np.ndarray:
        return np.concatenate(self.parts) if self.parts else np.zeros(0, np.float32)


def _robust_z(flux: np.ndarray, dt: float) -> tuple[np.ndarray, dict]:
    """(flux - running median) / running MAD on 100 ms blocks; floors avoid silent blow-ups."""
    n = len(flux)
    if n == 0:
        return flux.astype(np.float32), {"median": 0.0, "mad": 0.0}
    block = max(1, int(round(BLOCK_S / dt)))
    nb = int(np.ceil(n / block))
    padded = np.full(nb * block, np.nan, np.float32)
    padded[:n] = flux
    blocks = padded.reshape(nb, block)
    med_b = np.nanmedian(blocks, axis=1)
    mad_b = np.nanmedian(np.abs(blocks - med_b[:, None]), axis=1)
    med_r = ndimage.median_filter(med_b, size=NORM_BLOCKS, mode="nearest")
    mad_r = ndimage.median_filter(mad_b, size=NORM_BLOCKS, mode="nearest")
    centres = (np.arange(nb) + 0.5) * block
    idx = np.arange(n)
    med = np.interp(idx, centres, med_r)
    mad = np.interp(idx, centres, mad_r)
    floor = max(1e-4, 0.05 * float(np.median(flux)))
    z = (flux - med) / (1.4826 * mad + floor)
    return z.astype(np.float32), {"median": float(np.median(flux)), "mad": float(np.median(mad_b))}


def impact_curve_from_samples(samples: np.ndarray, sr: int = SR, start_s: float = 0.0,
                              band=BAND_HZ) -> ImpactCurve:
    """In-memory variant (tests, short clips). `start_s` = first sample on the video clock."""
    flux = _Flux(sr, band)
    step = int(CHUNK_S * sr)
    for i in range(0, len(samples), step):
        flux.push(np.asarray(samples[i:i + step], np.float32))
    return _finish(flux, sr, start_s)


def impact_curve(path: str, sr: int = SR, band=BAND_HZ) -> ImpactCurve | None:
    """Stream the first audio track of `path`; None when there is no usable audio."""
    if shutil.which("ffmpeg") is None:
        return None
    video_start, audio_start = stream_starts(path)
    if audio_start is None:
        return None
    flux = _Flux(sr, band)
    for chunk in _pcm_chunks(path, sr, CHUNK_S):
        flux.push(chunk)
    if flux.frames < 10:
        return None
    return _finish(flux, sr, float(audio_start - (video_start or 0.0)))


def _finish(flux: _Flux, sr: int, start_s: float) -> ImpactCurve:
    raw = flux.result()
    dt = HOP / sr
    z, stats = _robust_z(raw, dt)
    # frame k spans samples [k*HOP, k*HOP+N_FFT): stamp it at the window centre
    t0 = start_s + (N_FFT / 2) / sr
    return ImpactCurve(t0=t0, dt=dt, z=z, diagnostics={
        "sr": sr, "band_hz": list(BAND_HZ), "hop_s": dt, "samples": int(len(raw)),
        "start_s": float(start_s), **stats})


# ── events and evidence ─────────────────────────────────────────────────────────────────

def onsets(curve: ImpactCurve, z_min: float = 3.0) -> tuple[np.ndarray, np.ndarray]:
    """Local maxima within ±30 ms with z >= z_min → (times, z), times uncorrected for lag."""
    if len(curve.z) == 0:
        return np.zeros(0), np.zeros(0, np.float32)
    half = max(1, int(round(PEAK_HALF_S / curve.dt)))
    local = ndimage.maximum_filter1d(curve.z, size=2 * half + 1, mode="nearest")
    idx = np.flatnonzero((curve.z >= local) & (curve.z >= z_min))
    if len(idx):  # flat tops: keep the first sample of each plateau
        keep = np.concatenate([[True], np.diff(idx) > half])
        idx = idx[keep]
    return curve.t0 + curve.dt * idx, curve.z[idx]


def frame_evidence(curve: ImpactCurve, frame_t: np.ndarray, lag_s: float, tol_s: float) -> np.ndarray:
    """Per video frame: strongest audio z within ±tol_s of (frame time + lag)."""
    frame_t = np.asarray(frame_t, np.float64)
    if len(curve.z) == 0 or len(frame_t) == 0:
        return np.zeros(len(frame_t), np.float32)
    half = max(0, int(round(tol_s / curve.dt)))
    peak = ndimage.maximum_filter1d(curve.z, size=2 * half + 1, mode="nearest")
    target = frame_t + lag_s
    out = peak[curve.index(target)].astype(np.float32)
    outside = (target < curve.t0 - tol_s) | (target > curve.t0 + curve.dt * (len(curve.z) - 1) + tol_s)
    out[outside] = 0.0
    return out


@dataclass
class LagEstimate:
    lag_s: float          # audio − video (s); subtract from audio times to reach the video clock
    score: float          # mean per-anchor kernel support at the chosen lag (0..1)
    baseline: float       # median support over all candidate lags (chance level)
    match_rate: float     # share of anchors with an onset within ±tol_s at the chosen lag
    anchors: int

    @property
    def excess(self) -> float:
        return self.score - self.baseline


Z_WEIGHT_CAP = 20.0   # onset weight = min(z, cap) / cap: the near court's own contacts are loud


def estimate_lag(onset_t: np.ndarray, anchor_t: np.ndarray, onset_z: np.ndarray | None = None, *,
                 max_lag_s: float = 0.25, bandwidth_s: float = 0.012, step_s: float = 0.001,
                 tol_s: float = 0.025) -> LagEstimate:
    """Audio−video lag that best lines visual anchors up with audio onsets.

    Kernel score: every anchor contributes its best Gaussian support (σ = bandwidth_s) from
    the onsets around it, so ~1-frame anchor jitter (HitNet's measured offset spread) blurs
    the peak instead of breaking it. With `onset_z`, each onset's support is scaled by
    min(z, 20)/20 — loud onsets are the court's own contacts, quiet ones mostly clutter or
    neighbouring courts; on 22 anchors this picked the right one of two lag peaks.
    `excess` = peak − chance level is the gate statistic. Ties prefer the smaller |lag|.
    """
    a = np.sort(np.asarray(anchor_t, np.float64))
    order = np.argsort(np.asarray(onset_t, np.float64), kind="stable")
    o = np.asarray(onset_t, np.float64)[order]
    w = (np.ones(len(o)) if onset_z is None else
         np.clip(np.asarray(onset_z, np.float64)[order], 0.0, Z_WEIGHT_CAP) / Z_WEIGHT_CAP)
    if len(a) == 0 or len(o) == 0:
        return LagEstimate(0.0, 0.0, 0.0, 0.0, int(len(a)))
    reach = max_lag_s + 3 * bandwidth_s
    lo = np.searchsorted(o, a - reach, "left")
    hi = np.searchsorted(o, a + reach, "right")
    counts = hi - lo
    if counts.sum() == 0:
        return LagEstimate(0.0, 0.0, 0.0, 0.0, int(len(a)))
    ai = np.repeat(np.arange(len(a)), counts)
    oj = np.concatenate([np.arange(l, r) for l, r in zip(lo, hi) if r > l])
    resid = o[oj] - a[ai]
    lags = np.arange(-max_lag_s, max_lag_s + step_s / 2, step_s)
    support = np.zeros((len(a), len(lags)))
    weight = w[oj]
    for start in range(0, len(resid), 4096):          # bounded memory for long matches
        r = resid[start:start + 4096]
        k = np.exp(-0.5 * ((r[:, None] - lags[None, :]) / bandwidth_s) ** 2) * weight[start:start + 4096, None]
        np.maximum.at(support, ai[start:start + 4096], k)
    score = support.mean(axis=0)
    best = np.flatnonzero(score >= score.max() - 1e-9)
    i = best[np.argmin(np.abs(lags[best]))]
    lag = float(lags[i])
    matched = np.unique(ai[np.abs(resid - lag) <= tol_s])
    return LagEstimate(lag, float(score[i]), float(np.median(score)), len(matched) / len(a), int(len(a)))
