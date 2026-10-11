#!/usr/bin/env python3
"""calib_sweep2 tables: acceptance and false accepts per grid / cell / hard kind.

Usage: report.py AFTER.csv [--before BEFORE.csv] [--fa 0.10]
A false accept = accepted with worst keypoint floor error > --fa metres (Task 9: 0.10).
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict


def f(v):
    try:
        return None if v in (None, "", "None") else float(v)
    except ValueError:
        return None


def load(path: str) -> dict[int, dict]:
    return {int(r["id"]): r for r in csv.DictReader(open(path))}


def is_acc(r) -> bool:
    return str(r["accepted"]) == "True"


PX = 3.0      # CourtLock agreePx; coordinator D2: FA needs floor > fa AND px_max > PX


def is_strict(r, fa: float) -> bool:
    """Task 9's original metric: accepted with floor error > fa (always reported)."""
    return is_acc(r) and (f(r["floor_max_m"]) or 0) > fa


def is_fa(r, fa: float) -> bool:
    """FALSE ACCEPT (wrong camera): floor > fa AND worst keypoint error > PX."""
    return is_strict(r, fa) and (f(r["px_max"]) or 0) > PX


def is_imprecise(r, fa: float) -> bool:
    """Right camera at its resolution limit: floor > fa but keypoints <= PX."""
    return is_strict(r, fa) and not is_fa(r, fa)


def group(rows: dict, key) -> dict:
    g = defaultdict(list)
    for i, r in rows.items():
        g[key(r)].append(i)
    return g


def line(label: str, ids, after: dict, before: dict | None, fa: float) -> str:
    def stat(rows):
        acc = sum(is_acc(rows[i]) for i in ids if i in rows)
        n = sum(1 for i in ids if i in rows)
        bad = sum(is_fa(rows[i], fa) for i in ids if i in rows)
        imp = sum(is_imprecise(rows[i], fa) for i in ids if i in rows)
        st = sum(is_strict(rows[i], fa) for i in ids if i in rows)
        return (f"{acc:4d}/{n:<4d} {100 * acc / max(n, 1):5.1f}%  FA {bad:2d}  imprecise {imp:2d}"
                f"  strict {st:2d}")
    s = f"  {label:28s} {stat(after)}"
    if before:
        s = f"  {label:28s} before {stat(before)}  →  after {stat(after)}"
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("after")
    ap.add_argument("--before")
    ap.add_argument("--fa", type=float, default=0.10)
    a = ap.parse_args()
    A = load(a.after)
    B = load(a.before) if a.before else None
    print(f"FA (wrong camera) = accepted, worst floor error > {a.fa} m AND worst keypoint error > {PX} px; "
          f"imprecise = floor > {a.fa} m, keypoints <= {PX} px; strict = floor > {a.fa} m (Task 9 original)")
    for title, key in (("per grid", lambda r: r["grid"]),
                       ("per grid, whole court in frame", lambda r: f"{r['grid']} whole={r['whole_court']}"),
                       ("hard cases per kind", lambda r: r["kind"] if r["grid"] == "hard" else None),
                       ("low grid per height", lambda r: f"h={r['height_m']}" if r["grid"] == "low" else None),
                       ("low grid per distance", lambda r: f"d={r['dist_m']}" if r["grid"] == "low" else None),
                       ("rec grid per height", lambda r: f"h={r['height_m']}" if r["grid"] == "rec" else None),
                       ("rec grid per distance", lambda r: f"d={r['dist_m']}" if r["grid"] == "rec" else None)):
        print(f"\n{title}:")
        for k, ids in sorted(group(A, key).items(), key=lambda kv: str(kv[0])):
            if k is not None:
                print(line(str(k), ids, A, B, a.fa))
    fas = [r for r in A.values() if is_fa(r, a.fa)]
    print(f"\nfalse accepts after ({len(fas)}):")
    for r in sorted(fas, key=lambda r: -(f(r["floor_max_m"]) or 0)):
        print(f"  id {r['id']} {r['grid']}/{r['kind']} h{r['height_m']} d{r['dist_m']} lat{r['lat_m']} "
              f"roll{r['roll_deg']} pitch{r['pitch_deg']}: floor {f(r['floor_max_m']):.3f} m, px_max "
              f"{f(r['px_max']):.2f}, focal {100 * f(r['focal_rel']):.2f} %, src {r['source']}")
    rej = Counter(r["reason"] for r in A.values() if not is_acc(r))
    print(f"\nreject reasons after: {dict(rej)}")
    if B:
        lost = [i for i in A if i in B and is_acc(B[i]) and not is_acc(A[i])]
        print(f"accepted before but rejected after: {len(lost)} {lost[:30]}")


if __name__ == "__main__":
    main()
