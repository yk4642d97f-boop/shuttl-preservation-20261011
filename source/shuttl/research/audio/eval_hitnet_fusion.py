#!/usr/bin/env python
"""HitNet v2 (+ audio fusion, + doubles pairing) on your own labelled phone recordings.

This is the validation the sandbox study could not do (HitNet weights are in the encrypted
preservation bundle). Run it on the cloud GPU worker, from source/shuttl/backend:

  # 1) once per video, GPU: production tracking → players → HitNet curves + soundtrack curve
  PYTHONPATH=. python ../research/audio/eval_hitnet_fusion.py collect \
      --manifest ~/phone/manifest.csv --hitnet-weights "$SHUTTL_HITNET_WEIGHTS" --device cuda \
      --cache ~/phone/cache
  # 2) CPU, seconds, rerun freely
  PYTHONPATH=. python ../research/audio/eval_hitnet_fusion.py evaluate --cache ~/phone/cache \
      --json ../research/audio/results_hitnet_fusion.json

manifest CSV columns: video, labels, venue, mode   (mode: singles | doubles)
labels CSV: one row per racket contact. Column `frame` (0-based decoded frame index) or
  ShuttleSet's `frame_num`; optional `type` — rows whose type is serve / 发球 / 發短球 / 發長球
  count as serves (the visual model's weak spot, recall 78.9 %).

evaluate reports, per recording and pooled, at ±1/±2 frames (P/R/F1, serve recall, false
alarms per minute — DOUBLE_DATA_PROTOCOL.md's hit metrics): the visual decoder alone, the
shipped fusion defaults (per-recording gate), and a leave-one-venue-out refit of
(beta, penalty, z_snap, min_excess). Parameters are recommended only when every held-out
venue that passes the gate improves — otherwise keep SHUTTL_AUDIO_FUSION off.
"""
from __future__ import annotations

import argparse
import collections
import csv
import dataclasses
import itertools
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.services.tracking import audio_hits, hit_fusion, hitnet  # noqa: E402

SERVE_TYPES = {"serve", "short_serve", "long_serve", "发球", "發球", "發短球", "發長球", "发短球", "发长球"}
GRID = dict(beta=(1.0, 2.0, 3.0), penalty=(0.0, 0.5, 1.0), z_snap=(None, 6.0), min_excess=(0.08, 0.10, 0.12, 0.14))


def read_labels(path: str) -> tuple[np.ndarray, np.ndarray]:
    frames, serve = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            value = row.get("frame", row.get("frame_num"))
            try:
                frames.append(int(round(float(value))))
            except (TypeError, ValueError):
                continue
            serve.append((row.get("type") or "").strip().lower() in SERVE_TYPES)
    order = np.argsort(frames, kind="stable")
    return np.asarray(frames, int)[order], np.asarray(serve, bool)[order]


def collect(args) -> None:
    from app.services.tracking.pipeline_v2 import PipelineOptions, analyze_video
    try:  # the worker's own configuration (weights dirs, device) when available
        from app.services.tracking.tasks import _options
    except Exception:  # noqa: BLE001 — research convenience outside the worker image
        _options = None
    model = hitnet.load(args.hitnet_weights, args.device)
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    with open(args.manifest, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        out = cache / (Path(row["video"]).stem + ".npz")
        if out.exists() and not args.force:
            print("cached", out.name)
            continue
        doubles = row.get("mode", "singles").strip().lower() == "doubles"
        opts = _options({"doubles": doubles}) if _options else PipelineOptions()
        opts.device = args.device
        opts.hitnet_weights = None              # tracking/players only; HitNet runs below
        res = analyze_video(row["video"], opts)
        if res.track is None:
            print("no shuttle track:", row["video"], res.diagnostics.get("stages"))
            continue
        curves = model.curves(res.track, res.meta, res.players, doubles=doubles)
        sound = audio_hits.impact_curve(row["video"])
        frames, serve = read_labels(row["labels"])
        np.savez_compressed(
            out, t=np.asarray(res.meta.timestamps, np.float64), fps=float(res.meta.fps),
            p=curves.probability, top=curves.top, segments=np.asarray(curves.segments, int).reshape(-1, 2),
            audio=np.asarray([] if sound is None else [sound.t0, sound.dt], np.float64),
            z=np.zeros(0, np.float32) if sound is None else sound.z.astype(np.float32),
            hits=frames, serve=serve, venue=row["venue"], mode="doubles" if doubles else "singles",
            video=row["video"], sha256=model.sha256)
        print(f"collected {out.name}: {len(frames)} labelled hits, audio={'yes' if sound else 'no'}")


@dataclasses.dataclass
class Recording:
    name: str
    venue: str
    mode: str
    t: np.ndarray
    fps: float
    curves: hitnet.HitCurves
    sound: audio_hits.ImpactCurve | None
    hits: np.ndarray
    serve: np.ndarray


def load(cache: str) -> list[Recording]:
    out = []
    for path in sorted(Path(cache).glob("*.npz")):
        d = np.load(path, allow_pickle=False)
        segments = [tuple(map(int, s)) for s in d["segments"]]
        curves = hitnet.HitCurves(d["p"].astype(np.float32), d["top"].astype(np.float32),
                                  np.zeros(len(d["p"]), np.int16), [], segments)
        sound = (audio_hits.ImpactCurve(float(d["audio"][0]), float(d["audio"][1]), d["z"].astype(np.float32))
                 if len(d["audio"]) else None)
        out.append(Recording(path.stem, str(d["venue"]), str(d["mode"]), d["t"], float(d["fps"]),
                             curves, sound, d["hits"].astype(int), d["serve"].astype(bool)))
    return out


def match(det: np.ndarray, gt: np.ndarray, tol: int) -> tuple[int, int, int, np.ndarray]:
    """One-to-one greedy pairing on |offset| (research/hits/score.py protocol)."""
    pairs = sorted((abs(int(a) - int(b)), i, j) for i, a in enumerate(det) for j, b in enumerate(gt)
                   if abs(int(a) - int(b)) <= tol)
    used_d, used_g = set(), set()
    for _, i, j in pairs:
        if i not in used_d and j not in used_g:
            used_d.add(i)
            used_g.add(j)
    hit = np.zeros(len(gt), bool)
    hit[list(used_g)] = True
    return len(used_d), len(det) - len(used_d), len(gt) - len(used_g), hit


def prf(c: collections.Counter) -> dict:
    p = c["tp"] / max(1, c["tp"] + c["fp"])
    r = c["tp"] / max(1, c["tp"] + c["fn"])
    return dict(P=round(p, 3), R=round(r, 3), F1=round(2 * p * r / max(1e-9, p + r), 3),
                serve_R=round(c["serve_tp"] / c["serve_n"], 3) if c["serve_n"] else None,
                fp_per_min=round(c["fp"] / c["minutes"], 2) if c["minutes"] else None,
                **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in c.items()})


def run(rec: Recording, params: hit_fusion.FusionParams | None, use_audio: bool):
    gap = hitnet.DOUBLES_GAP_S if rec.mode == "doubles" else 0.3
    frames, _, gate, moved = hitnet.decode(rec.curves, rec.t, rec.fps, thr=0.4, gap_s=gap,
                                           audio_curve=rec.sound if use_audio else None, params=params)
    counts = {}
    for tol in (1, 2):
        tp, fp, fn, hit = match(np.asarray(frames, int), rec.hits, tol)
        counts[tol] = collections.Counter(tp=tp, fp=fp, fn=fn, serve_n=int(rec.serve.sum()),
                                          serve_tp=int(hit[rec.serve].sum()),
                                          minutes=float(rec.t[-1] - rec.t[0]) / 60 if len(rec.t) else 0.0)
    return counts, gate, moved


def pooled(recs, params, use_audio):
    tot = {1: collections.Counter(), 2: collections.Counter()}
    for rec in recs:
        counts, _, _ = run(rec, params, use_audio)
        for tol in tot:
            tot[tol].update(counts[tol])
    return tot


def evaluate(args) -> None:
    recs = load(args.cache)
    if not recs:
        raise SystemExit(f"no *.npz in {args.cache} — run `collect` first")
    default = hit_fusion.FusionParams()
    grid = [dataclasses.replace(default, beta=b, penalty=pe, z_snap=zs, min_excess=me)
            for b, pe, zs, me in itertools.product(*GRID.values())]
    report = {"default_params": dataclasses.asdict(default), "recordings": {}, "lovo": {}}
    for rec in recs:
        vis, _, _ = run(rec, None, False)
        fus, gate, moved = run(rec, default, True)
        report["recordings"][rec.name] = dict(
            venue=rec.venue, mode=rec.mode, hits=int(len(rec.hits)), audio=rec.sound is not None,
            gate=gate.as_dict() if gate else None, hits_changed_by_audio=moved,
            visual={f"tol{k}": prf(v) for k, v in vis.items()}, fused_default={f"tol{k}": prf(v) for k, v in fus.items()})
        print(f"{rec.name:28s} {rec.mode:7s} gate={gate.as_dict() if gate else None}")
        print(f"   visual F1@2 {prf(vis[2])['F1']:.3f}  fused F1@2 {prf(fus[2])['F1']:.3f}"
              f"   serve R {prf(vis[2])['serve_R']} → {prf(fus[2])['serve_R']}")
    for mode in sorted({r.mode for r in recs}):
        sub = [r for r in recs if r.mode == mode]
        venues = sorted({r.venue for r in sub})
        rows, improved_all = {}, True
        for held in venues:
            train, test = [r for r in sub if r.venue != held], [r for r in sub if r.venue == held]
            best = max(grid, key=lambda q: prf(pooled(train, q, True)[2])["F1"]) if train else default
            vis, fus, fit = (pooled(test, None, False), pooled(test, default, True), pooled(test, best, True))
            gated = any((g := run(r, best, True)[1]) is not None and g.used for r in test)
            rows[held] = dict(params={k: getattr(best, k) for k in GRID}, gated_on=gated,
                              visual=prf(vis[2]), fused_default=prf(fus[2]), fused_lovo=prf(fit[2]),
                              visual_tol1=prf(vis[1])["F1"], fused_lovo_tol1=prf(fit[1])["F1"])
            if gated and prf(fit[2])["F1"] <= prf(vis[2])["F1"]:
                improved_all = False
            print(f"[{mode}] held-out {held}: visual {prf(vis[2])['F1']:.3f}  default {prf(fus[2])['F1']:.3f}"
                  f"  LOVO-fit {prf(fit[2])['F1']:.3f}  gated={gated}")
        fit_all = max(grid, key=lambda q: prf(pooled(sub, q, True)[2])["F1"])
        report["lovo"][mode] = dict(folds=rows, every_gated_venue_improved=improved_all and len(venues) >= 3,
                                    venues=len(venues),
                                    recommended={k: getattr(fit_all, k) for k in GRID} if improved_all and len(venues) >= 3 else None)
    Path(args.json).write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print("wrote", args.json)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--manifest", required=True)
    c.add_argument("--hitnet-weights", default=os.environ.get("SHUTTL_HITNET_WEIGHTS"))
    c.add_argument("--device", default="cuda")
    c.add_argument("--cache", required=True)
    c.add_argument("--force", action="store_true")
    e = sub.add_parser("evaluate")
    e.add_argument("--cache", required=True)
    e.add_argument("--json", default="results_hitnet_fusion.json")
    args = ap.parse_args()
    if args.cmd == "collect":
        if not args.hitnet_weights:
            ap.error("--hitnet-weights (or SHUTTL_HITNET_WEIGHTS) is required")
        collect(args)
    else:
        evaluate(args)


if __name__ == "__main__":
    main()
