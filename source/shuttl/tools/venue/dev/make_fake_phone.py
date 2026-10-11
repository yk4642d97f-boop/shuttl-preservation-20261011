#!/usr/bin/env python3
"""dev/make_fake_phone.py — build a fake "phone" analysis from a Mac one (testing only).

Usage: ./make_fake_phone.py <mac_analysis.json> <out.json> [--seed 7]

Perturbs the Mac result the way a real phone run plausibly differs: a few hits
shifted by ±1..4 frames, some hits dropped, one extra hit, a rally trimmed, the
calibration confidence lowered, speeds scaled. Used to exercise analyze.py's
comparison + report.py without a phone.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    ap = argparse.ArgumentParser(prog="make_fake_phone.py")
    ap.add_argument("mac_analysis")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    a = json.load(open(args.mac_analysis, encoding="utf-8"))
    a = copy.deepcopy(a)

    if a.get("camera"):
        a["camera"]["confidence"] = round(max(0.4, float(a["camera"].get("confidence") or 0.8) * 0.72), 3)
        a["camera"]["reproj_rmse_px"] = round(float(a["camera"].get("reproj_rmse_px") or 1.0) * 2.1, 2)
    dropped = 0
    shifted = 0
    for r in a.get("rallies", []):
        shots = r.get("shots") or []
        keep = []
        for i, s in enumerate(shots):
            if i > 0 and i % 5 == 3 and dropped < 3:
                dropped += 1
                continue
            if i > 0 and rnd.random() < 0.35:
                s["frame"] = int(s["frame"]) + rnd.choice([-4, -3, -2, 2, 3, 4])
                shifted += 1
            keep.append(s)
        keep.sort(key=lambda s: s["frame"])
        r["shots"] = keep
        if rnd.random() < 0.5 and len(keep) > 4:
            r["start_frame"] = int(r["start_frame"]) + rnd.randint(2, 8)
            r["end_frame"] = int(r["end_frame"]) - rnd.randint(1, 4)
        r["confidence"] = round(rnd.uniform(0.3, 0.75), 2)
        r["outcome_confidence"] = round(rnd.uniform(0.3, 0.9), 2)
        if rnd.random() < 0.25 and len(a["rallies"]) > 1:
            pass
    for r in a.get("rallies", []):
        for s in r.get("shots") or []:
            f = s.get("flight")
            if f and f.get("speed0_kmh"):
                f["speed0_kmh"] = round(float(f["speed0_kmh"]) * 0.93, 1)
    s = a.get("summary") or {}
    if s.get("max_speed_kmh"):
        s["max_speed_kmh"] = round(float(s["max_speed_kmh"]) * 0.93, 1)
    a["video"] = dict(a.get("video") or {})
    a["diagnostics"] = {
        "video": a["diagnostics"].get("video") if isinstance(a.get("diagnostics"), dict) else None,
        "stages": {"detect": {"ok": True, "seconds": 21.4}, "link": {"ok": True, "seconds": 0.9},
                   "calibrate": {"ok": True, "seconds": 1.2}, "players": {"ok": True, "seconds": 9.8},
                   "hits": {"ok": True, "seconds": 0.3}, "reconstruct3d": {"ok": True, "seconds": 1.1},
                   "rallies": {"ok": True, "seconds": 0.1}, "shots": {"ok": True, "seconds": 0.1},
                   "score": {"ok": True, "seconds": 0.0}},
    }
    a["processing_time_seconds"] = 34.9
    a["_fake_note"] = f"fake phone analysis (dropped={dropped}, shifted={shifted}, seed={args.seed})"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(a, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {args.out}: dropped={dropped} shifted={shifted} camera_conf="
          f"{a['camera']['confidence'] if a.get('camera') else None}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
