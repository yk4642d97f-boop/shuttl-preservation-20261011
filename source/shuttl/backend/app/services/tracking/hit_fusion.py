"""Fuse per-frame visual hit probability with audio impact evidence (opt-in; phone recordings).

The audio track is evidence, not a detector: on the amateur rallies studied, impact onsets
reach high recall but low precision on their own (footsteps, shoe squeaks, neighbouring
courts), see research/audio/REPORT.md. The visual model therefore stays in charge and
audio only moves its probability and timing:

  0. gate: lag from confident visual hits (`audio_hits.estimate_lag`); audio is used only
     when the lag peak clearly beats chance (`min_excess`) with enough anchors;
  1. evidence  e(f) = clip((A(f) − z0) / (z1 − z0), 0, 1), where A(f) is the strongest audio
     z-score within ±tol of the frame time + estimated lag;
  2. logit p'(f) = logit p(f) + beta·e(f) − penalty·(1 − e(f));
  3. decode with HitNet's own peak + NMS rule;
  4. optionally move each decoded hit to the strongest onset (z ≥ z_snap) within
     ±max_shift frames — an onset is used at most once.

Default parameters are a
starting point fitted on a proxy visual model; refit them on HitNet output before release
(research/audio/eval_hitnet_fusion.py).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from . import audio_hits


@dataclass(frozen=True)
class FusionParams:
    beta: float = 2.0             # logit boost at full audio evidence
    penalty: float = 0.5          # logit cut where the audio is silent
    z0: float = 3.0               # evidence starts here (robust z) …
    z1: float = 9.0               # … and saturates here
    tol_frames: float = 1.0       # evidence search half-width
    z_snap: float | None = 6.0    # None disables timing snap
    max_shift_frames: float = 2.0
    onset_z: float = 3.0          # onsets used for lag estimation
    anchor_p: float = 0.9         # visual hits trusted as lag anchors
    min_anchors: int = 30         # fewer → the lag can jump between peaks (REPORT.md)
    min_excess: float = 0.10      # z-weighted lag peak above chance: noisy venue ≈0.05, clean ≥0.11
    max_lag_s: float = 0.25


@dataclass
class AudioGate:
    used: bool
    reason: str
    lag_s: float = 0.0
    excess: float = 0.0
    match_rate: float = 0.0
    anchors: int = 0

    def as_dict(self) -> dict:
        d = asdict(self)
        d["lag_ms"] = round(1000.0 * d.pop("lag_s"), 1)
        d["excess"] = round(d["excess"], 3)
        d["match_rate"] = round(d["match_rate"], 3)
        return d


def local_peaks(p, floor):
    """Torch-free copy of hitnet_core.local_peaks (parity is tested)."""
    p = np.asarray(p)
    pl = np.concatenate([[-1], p[:-1]])
    pr = np.concatenate([p[1:], [-1]])
    return np.where((p > pl) & (p >= pr) & (p >= floor))[0]


def decode_nms(p, fps, thr, gap_s):
    """Torch-free copy of hitnet_core.decode_nms (parity is tested)."""
    p = np.asarray(p)
    gap = max(1, int(round(gap_s * fps)))
    idx = local_peaks(p, thr)
    order = idx[np.argsort(-p[idx], kind="stable")]
    kept: list[int] = []
    for i in order:
        if all(abs(i - j) >= gap for j in kept):
            kept.append(int(i))
    return sorted(kept)


def fuse_probability(p, evidence, *, beta: float, penalty: float, z0: float, z1: float) -> np.ndarray:
    p = np.clip(np.asarray(p, np.float64), 1e-4, 1 - 1e-4)
    e = np.clip((np.asarray(evidence, np.float64) - z0) / max(z1 - z0, 1e-6), 0.0, 1.0)
    logit = np.log(p / (1 - p)) + beta * e - penalty * (1 - e)
    return (1 / (1 + np.exp(-logit))).astype(np.float32)


def snap_frames(frames, frame_t, onset_t, onset_z, lag_s: float, max_shift_s: float,
                priority=None) -> np.ndarray:
    """Move each frame to the video frame nearest its strongest unused onset in range.

    `onset_t` is on the audio side (uncorrected); `lag_s` maps it back to the video clock.
    Frames are processed by `priority` (descending; default: original order).
    """
    frames = np.asarray(frames, np.int64)
    frame_t = np.asarray(frame_t, np.float64)
    if len(frames) == 0 or len(onset_t) == 0:
        return frames.copy()
    video_on = np.asarray(onset_t, np.float64) - lag_s
    onset_z = np.asarray(onset_z, np.float64)
    order = np.argsort(-np.asarray(priority), kind="stable") if priority is not None else np.arange(len(frames))
    used = np.zeros(len(video_on), bool)
    out = frames.copy()
    for k in order:
        t = frame_t[frames[k]]
        cand = np.flatnonzero((np.abs(video_on - t) <= max_shift_s + 1e-9) & ~used)
        if len(cand) == 0:
            continue
        j = cand[np.argmax(onset_z[cand])]
        used[j] = True
        out[k] = int(np.argmin(np.abs(frame_t - video_on[j])))
    return np.unique(out)


def assess(curve: audio_hits.ImpactCurve | None, frame_t, p_visual, fps: float, thr: float,
           gap_s: float, params: FusionParams = FusionParams()) -> AudioGate:
    if curve is None:
        return AudioGate(False, "no_audio")
    frame_t = np.asarray(frame_t, np.float64)
    anchors = decode_nms(p_visual, fps, max(thr, params.anchor_p), gap_s)
    if len(anchors) < params.min_anchors:
        return AudioGate(False, "too_few_anchors", anchors=len(anchors))
    onset_t, onset_z = audio_hits.onsets(curve, params.onset_z)
    est = audio_hits.estimate_lag(onset_t, frame_t[anchors], onset_z, max_lag_s=params.max_lag_s)
    gate = AudioGate(False, "audio_not_informative", est.lag_s, est.excess, est.match_rate, est.anchors)
    if est.excess >= params.min_excess:
        gate.used, gate.reason = True, "ok"
    return gate


def fuse_and_decode(p_visual, frame_t, fps: float, curve: audio_hits.ImpactCurve | None, *,
                    thr: float, gap_s: float, params: FusionParams = FusionParams(),
                    gate: AudioGate | None = None):
    """→ (frames, fused_probability, gate). Falls back to visual-only decoding when gated off."""
    p_visual = np.asarray(p_visual, np.float32)
    gate = gate or assess(curve, frame_t, p_visual, fps, thr, gap_s, params)
    if not gate.used:
        return decode_nms(p_visual, fps, thr, gap_s), p_visual, gate
    tol = params.tol_frames / fps
    ev = audio_hits.frame_evidence(curve, frame_t, gate.lag_s, tol)
    fused = fuse_probability(p_visual, ev, beta=params.beta, penalty=params.penalty,
                             z0=params.z0, z1=params.z1)
    frames = decode_nms(fused, fps, thr, gap_s)
    if params.z_snap is not None and frames:
        onset_t, onset_z = audio_hits.onsets(curve, params.z_snap)
        frames = snap_frames(frames, frame_t, onset_t, onset_z, gate.lag_s,
                             params.max_shift_frames / fps, priority=fused[frames]).tolist()
    return frames, fused, gate
