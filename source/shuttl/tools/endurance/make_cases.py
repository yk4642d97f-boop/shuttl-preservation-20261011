#!/usr/bin/env python3
"""Writes the interruption-matrix case files (deterministic: random.Random(11)).

Usage: make_cases.py <ref-run-dir> <clip> <uuid> <out.json> [smoke]
Kill delays are drawn inside each stage's / write's measured duration in the reference
run (events.log), so every kill lands inside the stage or checkpoint write it targets.
"""
import json, random, sys

ref, clip, uuid, out = sys.argv[1:5]
smoke = len(sys.argv) > 5 and sys.argv[5] == "smoke"
rng = random.Random(11)
ev = [l.split(" ", 4) for l in open(f"{ref}/events.log") if l.startswith("EVENT ")]
t = lambda kind, detail: next(float(e[1]) for e in ev if e[3] == kind and e[4].strip().startswith(detail))
stage_s = {e[4].split()[0]: float(e[4].split()[1]) for e in ev if e[3] == "stage_finish"}
save_s = {}
for i, e in enumerate(ev):
    if e[3] == "save_begin":
        key = e[4].split()[0]
        end = next(float(x[1]) for x in ev[i:] if x[3] == "save_end" and x[4].startswith(key))
        save_s[key] = max(save_s.get(key, 0), end - float(e[1]))


def delays(stage, n, lo=0.02, hi=0.75):  # hi < 1: a run can be ~20 % faster than the reference
    return [round(rng.uniform(lo, hi) * stage_s[stage], 4) for _ in range(n)]


def fracs(n, lo=0.11, hi=0.49, gap=0.03):
    while True:
        xs = sorted(round(rng.uniform(lo, hi), 4) for _ in range(n))
        if all(b - a >= gap for a, b in zip(xs, xs[1:])):
            return xs


def w(key, n):  # kill while a checkpoint write is in flight
    return [f"save_begin:{key}:{round(rng.uniform(0.05, 0.9) * max(save_s[key], 0.002), 5)}" for _ in range(n)]


cases = []
if smoke:
    cases += [
        {"name": "s-detect-chain", "kills": [f"progress:{f}:0" for f in fracs(2)], "snapshot_after": {"0": "s-mid-detect"}},
        {"name": "s-players", "kills": [f"stage_start:players:{delays('players', 1)[0]}"], "snapshot_after": {"0": "s-post-camera"}},
        {"name": "s-players-write", "seed": "s-post-camera", "kills": w("players", 1)},
        {"name": "s-post-players", "seed": "s-post-camera", "kills": ["stage_start:hits:0", "stage_start:rallies:0"],
         "snapshot_after": {"0": "s-post-players"}},
        {"name": "s-torn-partial", "seed": "s-mid-detect", "prep": [{"op": "truncate", "path": "detect_partial.bin", "frac": 0.8}], "kills": []},
    ]
else:
    a, b = fracs(5), fracs(5)
    cases += [
        {"name": "detect-chain-A", "kills": [f"progress:{f}:0" for f in a],
         "snapshot_after": {"0": "mid-detect", "4": "late-detect"}},
        {"name": "detect-chain-B", "kills": [f"progress:{f}:0" for f in b]},
        {"name": "detect-partial-write", "kills": w("detect_partial", 3)},
        {"name": "double-resume-immediate", "kills": ["progress:0.2:0", "stage_start:detect:4"]},
        {"name": "players-chain", "kills": [f"stage_start:players:{d}" for d in delays("players", 10)],
         "snapshot_after": {"0": "post-camera"}},
        {"name": "players-write", "seed": "post-camera", "kills": w("players", 3)},
        {"name": "post-players-chain", "seed": "post-camera",
         "kills": ["stage_start:hits:0"] + [f"stage_start:{s}:{d}" for s in ["hits", "reconstruct3d", "rallies", "shots", "score"]
                                             for d in delays(s, 10 if s != "hits" else 9, 0.0, 1.0)],
         "snapshot_after": {"0": "post-players"}},
        {"name": "link-calibrate-chain", "seed": "post-players",
         "prep": [{"op": "rm", "path": "track.json"}, {"op": "rm", "path": "camera.json"}],
         "kills": [f"stage_start:link:{d}" for d in delays("link", 10, 0.0, 1.0)] + w("track", 2)
                  + [f"stage_start:calibrate:{d}" for d in delays("calibrate", 10, 0.0, 1.0)] + w("camera", 2)},
        {"name": "candidates-write", "seed": "late-detect", "kills": w("candidates", 3)},
        {"name": "pd-rm-candidates", "seed": "post-players", "prep": [{"op": "rm", "path": "candidates.json"}], "kills": []},
        {"name": "pd-truncate-players", "seed": "post-players", "prep": [{"op": "truncate", "path": "players.bin", "frac": 0.5}], "kills": []},
        {"name": "pd-garbage-camera", "seed": "post-players", "prep": [{"op": "garbage", "path": "camera.json"}], "kills": []},
    ] + [
        {"name": f"pd-torn-partial-{int(f * 100)}", "seed": "late-detect",
         "prep": [{"op": "truncate", "path": "detect_partial.bin", "frac": f}], "kills": []} for f in (0.31, 0.77, 0.97)
    ] + [
        {"name": "diskfull-detect", "seed": "mid-detect", "prep": [{"op": "diskfull", "image_mb": 200, "leave_mb": 3}],
         "kills": ["stage_start:players:30"], "between": {"0": [{"op": "free_disk"}]}},
        {"name": "diskfull-players", "seed": "post-camera", "prep": [{"op": "diskfull", "image_mb": 200, "leave_mb": 20}], "kills": []},
    ]
cfg = {"clip": clip, "uuid": uuid, "mode": "singles", "reference": ref,
       "timeout_s": int(sum(stage_s.values()) * 3 + 4 * 3600), "stage_s": stage_s, "save_s": save_s, "cases": cases}
json.dump(cfg, open(out, "w"), indent=1)
print(json.dumps({"stage_s": stage_s, "save_s": save_s, "n_cases": len(cases),
                  "n_kills": sum(len(c["kills"]) for c in cases)}, indent=1))
