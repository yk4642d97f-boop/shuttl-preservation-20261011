#!/usr/bin/env python
"""HitNet v2 (+ audio fusion, + doubles pairing) on labelled phone / amateur recordings.

Run on the cloud GPU worker, from source/shuttl/backend:

  # 1) once per video, GPU: production tracking → players → HitNet curves + soundtrack curve
  PYTHONPATH=. python ../research/audio/eval_hitnet_fusion.py collect \
      --manifest ~/phone/manifest.csv --hitnet-weights "$SHUTTL_HITNET_WEIGHTS" --device cuda \
      --cache ~/phone/cache
  # 2) CPU, seconds, rerun freely
  PYTHONPATH=. python ../research/audio/eval_hitnet_fusion.py evaluate --cache ~/phone/cache \
      --json ../research/audio/results_hitnet_fusion.json [--concat-by-venue]

manifest CSV columns: video, labels, venue, mode   (mode: singles | doubles)
labels CSV: one row per racket contact. Column `frame` (0-based decoded frame index) or
  ShuttleSet's `frame_num`; optional `type` — serve / 发球 / 發短球 / 發長球 rows count as serves;
  optional `side` (near | far) — the hitter's half, scored against HitNet's Top head.
Model paths come from the worker configuration (tasks._options) or, outside the worker image,
from SHUTTL_WEIGHTS_DIR / INFERENCE_DEVICE. `collect` also stores the rule detector's hits as a
baseline and, for doubles, each partner pairing's own curve.

evaluate reports at ±1/±2 frames — P/R/F1, serve recall, false alarms per minute
(DOUBLE_DATA_PROTOCOL.md's hit metrics) and hitter-side accuracy on matched hits — for the rule
detector, HitNet alone, the shipped audio fusion (per-recording gate) and, for doubles, the
first partner pairing alone. `--concat-by-venue` joins short clips of one venue/mode into one
recording so the audio gate sees as many anchors as a full match would. A leave-one-venue-out
refit of (beta, penalty, z_snap, min_excess) recommends parameters only when ≥3 venues exist and
every held-out venue that passes the gate improves — otherwise keep SHUTTL_AUDIO_FUSION off.
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
SINGLES_GAP_S = 0.30


def read_labels(path: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frames, serve, side = [], [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            value = row.get("frame", row.get("frame_num"))
            try:
                frames.append(int(round(float(value))))
            except (TypeError, ValueError):
                continue
            serve.append((row.get("type") or "").strip().lower() in SERVE_TYPES)
            s = (row.get("side") or "").strip().lower()
            side.append(s if s in ("near", "far") else "")
    order = np.argsort(frames, kind="stable")
    return (np.asarray(frames, int)[order], np.asarray(serve, bool)[order],
            np.asarray(side, dtype="<U4")[order])


def _pipeline_options(doubles: bool, device: str):
    try:  # the worker's own configuration when the full backend stack is installed
        from app.services.tracking.tasks import _options
        opts = _options({"doubles": doubles})
    except Exception:  # noqa: BLE001 — research env without celery/db packages
        from app.services.tracking.pipeline_v2 import PipelineOptions
        opts = PipelineOptions(weights_dir=os.environ.get("SHUTTL_WEIGHTS_DIR") or None, doubles=doubles)
    opts.device = device
    opts.hitnet_weights = None      # tracking/players only; HitNet runs below on the same inputs
    opts.bst_manifest = opts.rtmpose_weights = None   # strokes are not scored here
    opts.audio_fusion = opts.hitnet_doubles = False
    return opts


def collect(args) -> None:
    from app.services.tracking.pipeline_v2 import analyze_video
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
        res = analyze_video(row["video"], _pipeline_options(doubles, args.device))
        if res.track is None:
            print("no shuttle track:", row["video"], res.diagnostics.get("stages"))
            continue
        slots = hitnet.partner_slots(res.players)
        pairing_mode = doubles
        try:
            curves = model.curves(res.track, res.meta, res.players, doubles=doubles)
        except ValueError:          # singles clip with bystanders seen on one half
            curves, pairing_mode = model.curves(res.track, res.meta, res.players, doubles=True), True
        extra = {}
        if pairing_mode:            # each pairing on its own, for the "first pairing only" baseline
            per = [model.curves(res.track, res.meta,
                                hitnet._only(res.players, tuple(i for i in pair if i is not None)))
                   for pair in curves.pairings]
            extra = dict(p_pairs=np.stack([c.probability for c in per]), top_pairs=np.stack([c.top for c in per]),
                         pairings=np.asarray([[-1 if i is None else i for i in p] for p in curves.pairings], int))
        sound = audio_hits.impact_curve(row["video"])
        frames, serve, side = read_labels(row["labels"])
        np.savez_compressed(
            out, t=np.asarray(res.meta.timestamps, np.float64), fps=float(res.meta.fps),
            p=curves.probability, top=curves.top, segments=np.asarray(curves.segments, int).reshape(-1, 2),
            audio=np.asarray([] if sound is None else [sound.t0, sound.dt], np.float64),
            z=np.zeros(0, np.float32) if sound is None else sound.z.astype(np.float32),
            hits=frames, serve=serve, side=side, venue=row["venue"], mode="doubles" if doubles else "singles",
            pairing_mode=pairing_mode, video=row["video"], sha256=model.sha256,
            rules=np.asarray([h.frame for h in res.hits], int),
            rules_side=np.asarray([h.hitter or "" for h in res.hits], dtype="<U4"),
            players_far=len(slots["far"]), players_near=len(slots["near"]), **extra)
        print(f"collected {out.name}: {len(frames)} labelled hits, audio={'yes' if sound else 'no'}, "
              f"pairing_mode={pairing_mode}, partners far/near={len(slots['far'])}/{len(slots['near'])}")


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
    side: np.ndarray
    rules: np.ndarray
    rules_side: np.ndarray
    pairs: tuple[np.ndarray, np.ndarray] | None = None     # (n_pairings, n) probability / top
    parts: int = 1


def load(cache: str) -> list[Recording]:
    out = []
    for path in sorted(Path(cache).glob("*.npz")):
        d = np.load(path, allow_pickle=False)
        segments = [tuple(map(int, s)) for s in d["segments"]]
        curves = hitnet.HitCurves(d["p"].astype(np.float32), d["top"].astype(np.float32),
                                  np.zeros(len(d["p"]), np.int16), [], segments)
        sound = (audio_hits.ImpactCurve(float(d["audio"][0]), float(d["audio"][1]), d["z"].astype(np.float32))
                 if len(d["audio"]) else None)
        n = len(d["hits"])
        out.append(Recording(
            path.stem, str(d["venue"]), str(d["mode"]), d["t"], float(d["fps"]), curves, sound,
            d["hits"].astype(int), d["serve"].astype(bool),
            d["side"] if "side" in d.files else np.full(n, "", "<U4"),
            d["rules"].astype(int) if "rules" in d.files else np.zeros(0, int),
            d["rules_side"] if "rules_side" in d.files else np.zeros(0, "<U4"),
            (d["p_pairs"], d["top_pairs"]) if "p_pairs" in d.files else None))
    return out


def concat_by_venue(recs: list[Recording], pad_s: float = 5.0) -> list[Recording]:
    """Join the clips of each (venue, mode) into one recording: clock and frames offset, audio
    curve placed on one grid. Lets the per-recording audio gate see all of a venue's anchors."""
    groups = collections.defaultdict(list)
    for r in recs:
        groups[(r.venue, r.mode)].append(r)
    out = []
    for (venue, mode), rs in sorted(groups.items()):
        dt = next((r.sound.dt for r in rs if r.sound is not None), None)
        t, p, top, segs, hits, serve, side, rules, rules_side, pp, tp = ([] for _ in range(11))
        offset_s, offset_f = 0.0, 0
        zs = []
        for r in rs:
            t.append(r.t - r.t[0] + offset_s)
            p.append(r.curves.probability)
            top.append(r.curves.top)
            segs += [(a + offset_f, b + offset_f) for a, b in r.curves.segments]
            hits.append(r.hits + offset_f)
            serve.append(r.serve)
            side.append(r.side)
            rules.append(r.rules + offset_f)
            rules_side.append(r.rules_side)
            if r.pairs is not None:
                pp.append(r.pairs[0])
                tp.append(r.pairs[1])
            if r.sound is not None and dt is not None:
                zs.append((r.sound.t0 - r.t[0] + offset_s, r.sound.z))
            offset_s += float(r.t[-1] - r.t[0]) + pad_s
            offset_f += len(r.t)
        sound = None
        if zs:
            z = np.zeros(int(np.ceil(offset_s / dt)) + 1, np.float32)
            for t0, zz in zs:
                i0 = max(0, int(round(t0 / dt)))
                k = min(len(zz), len(z) - i0)
                z[i0:i0 + k] = zz[:k]
            sound = audio_hits.ImpactCurve(0.0, dt, z)
        n = offset_f
        curves = hitnet.HitCurves(np.concatenate(p), np.concatenate(top), np.zeros(n, np.int16), [], segs)
        pairs = None
        if pp and len(pp) == len(rs) and len({a.shape[0] for a in pp}) == 1:
            pairs = (np.concatenate(pp, axis=1), np.concatenate(tp, axis=1))
        out.append(Recording(f"{venue}_{mode}", venue, mode, np.concatenate(t), rs[0].fps, curves, sound,
                             np.concatenate(hits), np.concatenate(serve), np.concatenate(side),
                             np.concatenate(rules), np.concatenate(rules_side), pairs, len(rs)))
    return out


def match(det: np.ndarray, gt: np.ndarray, tol: int) -> tuple[list[tuple[int, int]], int, int]:
    """One-to-one greedy pairing on |offset| (research/hits/score.py protocol) → pairs, fp, fn."""
    cand = sorted((abs(int(a) - int(b)), i, j) for i, a in enumerate(det) for j, b in enumerate(gt)
                  if abs(int(a) - int(b)) <= tol)
    used_d, used_g, pairs = set(), set(), []
    for _, i, j in cand:
        if i not in used_d and j not in used_g:
            used_d.add(i)
            used_g.add(j)
            pairs.append((i, j))
    return pairs, len(det) - len(pairs), len(gt) - len(pairs)


def offsets(rec: Recording, frames, tol: int = 6) -> collections.Counter:
    """Detection − label frame offsets of one-to-one matches within ±tol (label convention check)."""
    pairs, _, _ = match(np.asarray(frames, int), rec.hits, tol)
    return collections.Counter(int(frames[i]) - int(rec.hits[j]) for i, j in pairs)


def score(rec: Recording, frames, sides) -> dict[int, collections.Counter]:
    frames = np.asarray(frames, int)
    out = {}
    for tol in (1, 2):
        pairs, fp, fn = match(frames, rec.hits, tol)
        hit = np.zeros(len(rec.hits), bool)
        side_ok = side_n = 0
        for i, j in pairs:
            hit[j] = True
            if rec.side[j]:
                side_n += 1
                side_ok += sides[i] == rec.side[j]
        out[tol] = collections.Counter(tp=len(pairs), fp=fp, fn=fn, serve_n=int(rec.serve.sum()),
                                       serve_tp=int(hit[rec.serve].sum()), side_n=side_n, side_ok=int(side_ok),
                                       minutes=float(rec.t[-1] - rec.t[0]) / 60 if len(rec.t) else 0.0)
    return out


def prf(c: collections.Counter) -> dict:
    p = c["tp"] / max(1, c["tp"] + c["fp"])
    r = c["tp"] / max(1, c["tp"] + c["fn"])
    return dict(P=round(p, 3), R=round(r, 3), F1=round(2 * p * r / max(1e-9, p + r), 3),
                serve_R=round(c["serve_tp"] / c["serve_n"], 3) if c["serve_n"] else None,
                side_acc=round(c["side_ok"] / c["side_n"], 3) if c["side_n"] else None,
                fp_per_min=round(c["fp"] / c["minutes"], 2) if c["minutes"] else None,
                **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in c.items()})


def _gap(rec: Recording) -> float:
    return hitnet.DOUBLES_GAP_S if rec.mode == "doubles" else SINGLES_GAP_S


def variants(rec: Recording, params: hit_fusion.FusionParams | None = None, *, full: bool = True):
    """Detector variants on one recording → {name: (counts, gate, hits changed by audio)}."""
    params = params or hit_fusion.FusionParams()
    side_of = lambda top, frames: ["far" if top[f] > .5 else "near" for f in frames]  # noqa: E731
    out = {}
    frames, _, gate, moved = hitnet.decode(rec.curves, rec.t, rec.fps, thr=.4, gap_s=_gap(rec),
                                           audio_curve=rec.sound, params=params)
    out["hitnet_audio"] = (score(rec, frames, side_of(rec.curves.top, frames)), gate, moved)
    if not full:
        return out
    frames, _, _, _ = hitnet.decode(rec.curves, rec.t, rec.fps, thr=.4, gap_s=_gap(rec))
    out["hitnet"] = (score(rec, frames, side_of(rec.curves.top, frames)), None, 0)
    out["rules"] = (score(rec, rec.rules, list(rec.rules_side)), None, 0)
    if rec.mode == "doubles":
        frames, _, _, _ = hitnet.decode(rec.curves, rec.t, rec.fps, thr=.4, gap_s=SINGLES_GAP_S)
        out["hitnet_gap0.30"] = (score(rec, frames, side_of(rec.curves.top, frames)), None, 0)
    if rec.pairs is not None:
        first = hitnet.HitCurves(rec.pairs[0][0].astype(np.float32), rec.pairs[1][0].astype(np.float32),
                                 np.zeros(len(rec.t), np.int16), [], rec.curves.segments)
        frames, _, _, _ = hitnet.decode(first, rec.t, rec.fps, thr=.4, gap_s=_gap(rec))
        out["first_pairing_only"] = (score(rec, frames, side_of(first.top, frames)), None, 0)
    return out


def evaluate(args) -> None:
    recs = load(args.cache)
    if not recs:
        raise SystemExit(f"no *.npz in {args.cache} — run `collect` first")
    if args.concat_by_venue:
        recs = concat_by_venue(recs)
    default = hit_fusion.FusionParams()
    report = {"default_params": dataclasses.asdict(default), "concat_by_venue": bool(args.concat_by_venue),
              "recordings": {}, "pooled": {}, "lovo": {}}
    pooled = collections.defaultdict(lambda: {1: collections.Counter(), 2: collections.Counter()})
    offset_hist = collections.defaultdict(collections.Counter)
    for rec in recs:
        res = variants(rec, default)
        gate = res["hitnet_audio"][1]
        plain, _, _, _ = hitnet.decode(rec.curves, rec.t, rec.fps, thr=.4, gap_s=_gap(rec))
        offset_hist[rec.mode].update(offsets(rec, plain))
        report["recordings"][rec.name] = dict(
            venue=rec.venue, mode=rec.mode, clips=rec.parts, hits=int(len(rec.hits)), audio=rec.sound is not None,
            gate=gate.as_dict() if gate else None, hits_changed_by_audio=res["hitnet_audio"][2],
            **{name: {f"tol{k}": prf(v) for k, v in counts.items()} for name, (counts, _, _) in res.items()})
        for name, (counts, _, _) in res.items():
            for tol in (1, 2):
                pooled[(rec.mode, name)][tol].update(counts[tol])
        print(f"{rec.name:24s} {rec.mode:7s} clips={rec.parts:2d} hits={len(rec.hits):4d} "
              f"gate={gate.as_dict() if gate else None}")
        for name, (counts, _, _) in res.items():
            a, b = prf(counts[2]), prf(counts[1])
            print(f"   {name:20s} P {a['P']:.3f} R {a['R']:.3f} F1@2 {a['F1']:.3f} F1@1 {b['F1']:.3f} "
                  f"serve_R {a['serve_R']} side {a['side_acc']} FP/min {a['fp_per_min']}")
    for (mode, name), tots in sorted(pooled.items()):
        report["pooled"].setdefault(mode, {})[name] = {f"tol{k}": prf(v) for k, v in tots.items()}
        a, b = prf(tots[2]), prf(tots[1])
        print(f"[pooled {mode}] {name:20s} P {a['P']:.3f} R {a['R']:.3f} F1@2 {a['F1']:.3f} F1@1 {b['F1']:.3f} "
              f"serve_R {a['serve_R']} side {a['side_acc']}")
    for mode, hist in sorted(offset_hist.items()):
        report.setdefault("hitnet_offset_frames", {})[mode] = {str(k): v for k, v in sorted(hist.items())}
        print(f"[offsets {mode}] HitNet − label (frames, matches within ±6):", dict(sorted(hist.items())))
    grid = [dataclasses.replace(default, beta=b, penalty=pe, z_snap=zs, min_excess=me)
            for b, pe, zs, me in itertools.product(*GRID.values())]

    def fused_f1(rs, params):
        tot = collections.Counter()
        for r in rs:
            tot.update(variants(r, params, full=False)["hitnet_audio"][0][2])
        return prf(tot)["F1"]

    for mode in sorted({r.mode for r in recs}):
        sub = [r for r in recs if r.mode == mode]
        venues = sorted({r.venue for r in sub})
        folds, improved_all = {}, True
        for held in venues:
            train, test = [r for r in sub if r.venue != held], [r for r in sub if r.venue == held]
            best = max(grid, key=lambda q: fused_f1(train, q)) if train else default
            vis = collections.Counter()
            for r in test:
                vis.update(variants(r, default)["hitnet"][0][2])
            fit, gated = collections.Counter(), False
            for r in test:
                counts, gate, _ = variants(r, best, full=False)["hitnet_audio"]
                fit.update(counts[2])
                gated |= bool(gate and gate.used)
            folds[held] = dict(params={k: getattr(best, k) for k in GRID}, gated_on=gated,
                               hitnet=prf(vis), fused_lovo=prf(fit))
            if gated and prf(fit)["F1"] <= prf(vis)["F1"]:
                improved_all = False
        ok = improved_all and len(venues) >= 3
        fit_all = max(grid, key=lambda q: fused_f1(sub, q)) if ok else None
        report["lovo"][mode] = dict(venues=len(venues), folds=folds, every_gated_venue_improved=improved_all,
                                    recommended={k: getattr(fit_all, k) for k in GRID} if ok else None)
    Path(args.json).write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print("wrote", args.json)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--manifest", required=True)
    c.add_argument("--hitnet-weights", default=os.environ.get("SHUTTL_HITNET_WEIGHTS"))
    c.add_argument("--device", default=os.environ.get("INFERENCE_DEVICE") or "cuda")
    c.add_argument("--cache", required=True)
    c.add_argument("--force", action="store_true")
    e = sub.add_parser("evaluate")
    e.add_argument("--cache", required=True)
    e.add_argument("--json", default="results_hitnet_fusion.json")
    e.add_argument("--concat-by-venue", action="store_true")
    args = ap.parse_args()
    if args.cmd == "collect":
        if not args.hitnet_weights:
            ap.error("--hitnet-weights (or SHUTTL_HITNET_WEIGHTS) is required")
        collect(args)
    else:
        evaluate(args)


if __name__ == "__main__":
    main()
