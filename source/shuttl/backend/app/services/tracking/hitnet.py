"""Cloud HitNet adapter.

Validated: singles (annotated singles rallies). Experimental, opt-in only:
  * doubles — the singles checkpoint runs once per far×near partner pairing (2×2 = 4) and
    the per-frame maximum is decoded; the side comes from the winning pairing's Top head.
    The partner is named only when one player is observed on that side, otherwise
    `player_track_id` stays None so reconstruct3d / shots choose it (feet nearest the 3-D
    contact: 96.8 % on S2Doubles with annotated contacts, research/doubles/REPORT.md).
  * audio — `hit_fusion` moves probability/timing with impact onsets when the recording's
    soundtrack passes the per-recording gate (research/audio/REPORT.md).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
from pathlib import Path

import numpy as np
import torch

from app.services.tracking import hit_fusion
from app.services.tracking import hitnet_core as core
from app.services.tracking.data_types import HitEvent, PlayerObservation, Track2D, VideoMeta
from app.services.tracking.video_io import pts_gaps

DOUBLES_GAP_S = 0.25   # pro doubles: 1.82 % of inter-hit gaps < 0.30 s, 0.18 % < 0.25 s


def player_index(players: list[PlayerObservation] | None):
    index = {}
    multiple = False
    for observation in players or []:
        if observation.side not in ("far", "near"):
            continue
        key = (observation.frame, observation.side)
        previous = index.get(key)
        if previous is not None and previous.track_id != observation.track_id:
            multiple = True
        if previous is None or observation.track_id < previous.track_id:
            index[key] = observation
    return index, multiple


def partner_slots(players: list[PlayerObservation] | None, per_side: int = 2) -> dict[str, list[int]]:
    """Most frequently observed track ids per side — the doubles partners (ties: lower id)."""
    counts = {"far": Counter(), "near": Counter()}
    for observation in players or []:
        if observation.side in counts:
            counts[observation.side][observation.track_id] += 1
    return {side: [tid for tid, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:per_side]]
            for side, c in counts.items()}


def _only(players: list[PlayerObservation] | None, ids: tuple[int, ...]) -> list[PlayerObservation]:
    keep = set(ids)
    return [o for o in players or [] if o.track_id in keep]


@dataclass
class HitCurves:
    """Per-frame decoder input: P(hit), P(hitter is far/Top), which pairing produced it."""
    probability: np.ndarray
    top: np.ndarray
    pairing: np.ndarray
    pairings: list[tuple[int | None, int | None]]
    segments: list[tuple[int, int]] = field(default_factory=list)


def raw_matrix(track: Track2D, meta: VideoMeta, players: list[PlayerObservation] | None) -> np.ndarray:
    if meta.width <= 0 or meta.height <= 0:
        raise ValueError("Positive upright video dimensions are required")
    n = track.n
    if (np.shape(track.xy) != (n, 2) or
            any(np.shape(a) != (n,) for a in (track.conf, track.visible, track.interpolated))):
        raise ValueError("Track arrays must have one aligned entry per frame")
    raw = np.full((n, 16), np.nan, np.float32)
    xy = np.asarray(track.xy, np.float64)
    visible = np.asarray(track.visible, bool) & np.isfinite(xy).all(1)
    raw[visible, :2] = xy[visible] / [meta.width, meta.height]
    raw[visible, 2] = np.asarray(track.conf)[visible]
    raw[:, 3] = track.interpolated
    index, _ = player_index(players)
    for (frame, side), observation in index.items():
        if not 0 <= frame < n:
            continue
        player = 0 if side == "far" else 1
        box = np.asarray(observation.bbox, np.float64)
        if box.shape == (4,) and np.isfinite(box).all():
            raw[frame, 4 + player * 4:8 + player * 4] = [
                (box[0] + box[2]) / 2 / meta.width, (box[1] + box[3]) / 2 / meta.height,
                (box[2] - box[0]) / meta.width, (box[3] - box[1]) / meta.height]
        if observation.foot_world is not None:
            foot = np.asarray(observation.foot_world, np.float64)
            if foot.shape == (2,) and np.isfinite(foot).all():
                raw[frame, 12 + player * 2:14 + player * 2] = foot
    return raw


class HitNet:
    def __init__(self, weights: str | Path, device: str = "cpu"):
        self.path = Path(weights).resolve()
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        # Only load the portable export, not an arbitrary Python training checkpoint.
        checkpoint = torch.load(self.path, map_location="cpu", weights_only=True)
        if checkpoint.get("arch") != "tcn" or checkpoint.get("n_in") != 51:
            raise ValueError("Unsupported HitNet architecture or feature contract")
        self.decoder = checkpoint.get("decoder", {})
        if self.decoder != {"thr": .4, "gap_s": .3, "lam": 0.0}:
            raise ValueError("Unexpected HitNet decoder contract")
        self.device = torch.device(device)
        self.net = core.HitTCN(51, int(checkpoint["hidden"]))
        self.net.load_state_dict(checkpoint["state"], strict=True)
        self.net.to(self.device).eval()

    @torch.inference_mode()
    def logits(self, raw: np.ndarray, fps: float) -> np.ndarray:
        if not np.isfinite(fps) or fps <= 0:
            raise ValueError("FPS must be positive and finite")
        if raw.ndim != 2 or raw.shape[1] != 16:
            raise ValueError("HitNet expects (frames,16) raw features")
        n = len(raw)
        if n == 0:
            return np.empty((0, 2), np.float32)
        x = torch.from_numpy(core.derive(raw, fps))
        window, stride = 384, 192
        if n <= window:
            result = self.net(x[None].to(self.device))[0].float().cpu().numpy()
            if not np.isfinite(result).all():
                raise ValueError("Non-finite HitNet model output")
            return result
        starts = list(range(0, n - window + 1, stride))
        if starts[-1] != n - window:
            starts.append(n - window)
        result = np.empty((n, 2), np.float32)
        margin = (window - stride) // 2
        for i, start in enumerate(starts):
            logits = self.net(x[start:start + window][None].to(self.device))[0].float().cpu().numpy()
            lo = 0 if i == 0 else margin
            hi = window if i == len(starts) - 1 else window - margin
            result[start + lo:start + hi] = logits[lo:hi]
        if not np.isfinite(result).all():
            raise ValueError("Non-finite HitNet model output")
        return result

    def _validate(self, track: Track2D, meta: VideoMeta) -> np.ndarray:
        if len(meta.timestamps) != track.n or meta.n_frames != track.n:
            raise ValueError("Video timestamps and track frames are not aligned")
        timestamps = np.asarray(meta.timestamps, np.float64)
        if not np.array_equal(np.asarray(track.t), timestamps):
            raise ValueError("Track and video timestamps differ")
        if not np.isfinite(timestamps).all() or np.any(np.diff(timestamps) <= 0):
            raise ValueError("Timestamps must be finite and strictly increasing")
        return timestamps

    def curves(self, track: Track2D, meta: VideoMeta, players: list[PlayerObservation] | None,
               *, doubles: bool = False) -> HitCurves:
        """Per-frame P(hit)/P(Top) for every presentation-clock segment with a shuttle sighting.

        Singles: one pass, exactly the validated path. Doubles: one pass per far×near
        partner pairing; each frame keeps the pairing with the highest P(hit).
        """
        if doubles:
            slots = partner_slots(players)
            fars, nears = slots["far"] or [None], slots["near"] or [None]
            pairings = [(f, n) for f in fars for n in nears]
            raws = [raw_matrix(track, meta, _only(players, tuple(i for i in pair if i is not None)))
                    for pair in pairings]
        else:
            _, multiple = player_index(players)
            if multiple:
                raise ValueError("This HitNet checkpoint has only been validated with two players")
            pairings = [(None, None)]
            raws = [raw_matrix(track, meta, players)]
        n = track.n
        out = HitCurves(np.zeros(n, np.float32), np.full(n, .5, np.float32),
                        np.full(n, -1, np.int16), pairings)
        if not n:
            return out
        timestamps = self._validate(track, meta)
        boundaries = [0, *pts_gaps(timestamps).tolist(), n]
        for start, stop in zip(boundaries[:-1], boundaries[1:]):
            if not np.isfinite(raws[0][start:stop, :2]).all(1).any():
                continue  # no shuttle observation to support a learned hit
            per = [self.logits(raw[start:stop], meta.fps) for raw in raws]
            probability = np.stack([core.sigmoid(lg[:, 0]) for lg in per])
            top = np.stack([core.sigmoid(lg[:, 1]) for lg in per])
            best = np.argmax(probability, axis=0)
            cols = np.arange(stop - start)
            out.probability[start:stop] = probability[best, cols]
            out.top[start:stop] = top[best, cols]
            out.pairing[start:stop] = best
            out.segments.append((start, stop))
        return out

    def detect(self, track: Track2D, meta: VideoMeta, players: list[PlayerObservation] | None,
               *, doubles: bool = False, experimental_doubles: bool = False, audio_curve=None,
               fusion: hit_fusion.FusionParams | None = None, gap_s: float | None = None,
               diagnostics: dict | None = None) -> list[HitEvent]:
        """Decode hits. Defaults reproduce the validated singles decoder exactly.

        Doubles footage is still rejected unless `experimental_doubles` asks for the
        partner-pairing mode; `audio_curve` is the other experimental opt-in (module
        docstring). `gap_s` overrides the NMS gap (pairing mode default DOUBLES_GAP_S).
        """
        index, multiple = player_index(players)
        if (doubles or multiple) and not experimental_doubles:
            raise ValueError("This HitNet checkpoint has only been validated with two players")
        doubles = bool(experimental_doubles)
        if not track.n:
            return []
        timestamps = self._validate(track, meta)
        curves = self.curves(track, meta, players, doubles=doubles)
        gap = float(gap_s) if gap_s is not None else (DOUBLES_GAP_S if doubles else self.decoder["gap_s"])
        frames, scores, gate, moved = decode(curves, timestamps, meta.fps, thr=self.decoder["thr"],
                                             gap_s=gap, audio_curve=audio_curve, params=fusion)
        by_side = _observed_ids(players) if doubles else None
        hits, ambiguous, by_pairing = [], 0, Counter()
        for frame, score in zip(frames, scores):
            side = "far" if curves.top[frame] > .5 else "near"
            if doubles:
                by_pairing[int(curves.pairing[frame])] += 1
                ids = by_side.get((frame, side), set())
                track_id = next(iter(ids)) if len(ids) == 1 else None
                ambiguous += track_id is None and len(ids) > 1
            else:
                observation = index.get((frame, side))
                track_id = observation.track_id if observation else None
            hits.append(HitEvent(frame=frame, t=float(timestamps[frame]),
                                 xy_px=tuple(float(v) for v in track.xy[frame]), hitter=side,
                                 confidence=score, player_track_id=track_id, source="hitnet"))
        if diagnostics is not None:
            if doubles:
                diagnostics["doubles"] = {
                    "pairings": [list(p) for p in curves.pairings], "gap_s": gap,
                    "hits_by_pairing": {str(k): v for k, v in sorted(by_pairing.items())},
                    "hitter_left_to_geometry": ambiguous}
            if audio_curve is not None or gate is not None:
                diagnostics["audio"] = {**(gate.as_dict() if gate else {"used": False, "reason": "no_audio"}),
                                        "hits_changed_by_audio": moved}
        return hits


def decode(curves: HitCurves, timestamps: np.ndarray, fps: float, *, thr: float, gap_s: float,
           audio_curve=None, params: hit_fusion.FusionParams | None = None):
    """Production decoder over HitCurves → (frames, confidences, audio gate, hits changed by audio).

    Without audio (or when the per-recording gate is off) this is `decode_nms` on every PTS
    segment, i.e. the validated singles decoder. Research evaluations call it directly.
    """
    params = params or hit_fusion.FusionParams()
    gate = None
    if audio_curve is not None:
        gate = hit_fusion.assess(audio_curve, timestamps, curves.probability, fps, thr, gap_s, params)
    frames, scores, moved = [], [], 0
    reach = max(1, int(round(params.max_shift_frames)))
    for start, stop in curves.segments:
        probability = curves.probability[start:stop]
        plain = core.decode_nms(probability, fps, thr, gap_s)
        if gate is None or not gate.used:
            frames += [start + int(r) for r in plain]
            scores += [float(probability[r]) for r in plain]
            continue
        rows, fused, _ = hit_fusion.fuse_and_decode(probability, timestamps[start:stop], fps, audio_curve,
                                                    thr=thr, gap_s=gap_s, params=params, gate=gate)
        moved += len(set(rows) - set(plain))
        for r in rows:   # confidence: fused probability near the (possibly snapped) frame
            frames.append(start + int(r))
            scores.append(float(np.max(fused[max(0, r - reach):r + reach + 1])))
    return frames, scores, gate, moved


def _observed_ids(players: list[PlayerObservation] | None) -> dict[tuple[int, str], set[int]]:
    """(frame, side) → track ids seen at that frame (doubles hitter naming)."""
    out: dict[tuple[int, str], set[int]] = {}
    for o in players or []:
        if o.side in ("far", "near"):
            out.setdefault((o.frame, o.side), set()).add(o.track_id)
    return out


@lru_cache(maxsize=2)
def _cached(path: str, size: int, mtime_ns: int, device: str) -> HitNet:
    return HitNet(path, device)


def load(weights: str | Path, device: str = "cpu") -> HitNet:
    path = Path(weights).resolve()
    stat = path.stat()
    return _cached(str(path), stat.st_size, stat.st_mtime_ns, device)
