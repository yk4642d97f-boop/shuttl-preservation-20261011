#!/usr/bin/env python3
"""Compare a resumed run dir against the uninterrupted reference run dir.

Byte-exact:  semantic-result.json (MatchAnalysis minus players / diagnostics / time)
             players-comparable.bin (PlayersCodec, full precision incl. keypoints)
Field-exact: diagnostics.json minus keys that legitimately differ on resume:
             stages (timings, "resumed", sampler fields), calibration_auto (not
             recomputed when the camera comes from a checkpoint), archive.
Prints one JSON line: {"case", "pass", "semantic_equal", "players_equal", "diag_equal", "diffs"}.
Usage: compare.py <reference-dir> <candidate-dir> [case-name]
"""
import hashlib, json, os, sys

VOLATILE = {"stages", "calibration_auto", "archive"}


def sha(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def diff(a, b, path="", out=None, limit=20):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if type(a) != type(b):
        out.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'ref' if k in a else 'cand'}")
            else:
                diff(a[k], b[k], f"{path}/{k}", out, limit)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: len {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, limit)
    elif a != b:
        out.append(f"{path}: {a!r} != {b!r}")
    return out


def load(p):
    with open(p) as f:
        return json.load(f)


def main():
    ref, cand = sys.argv[1], sys.argv[2]
    case = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(cand)
    r = {"case": case}
    sem_r, sem_c = os.path.join(ref, "semantic-result.json"), os.path.join(cand, "semantic-result.json")
    if not os.path.exists(sem_c):
        r.update({"pass": False, "diffs": ["candidate has no semantic-result.json (run did not finish)"]})
        print(json.dumps(r)); return 1
    r["semantic_equal"] = sha(sem_r) == sha(sem_c)
    r["players_equal"] = sha(os.path.join(ref, "players-comparable.bin")) == sha(os.path.join(cand, "players-comparable.bin"))
    dr = {k: v for k, v in load(os.path.join(ref, "diagnostics.json")).items() if k not in VOLATILE}
    dc = {k: v for k, v in load(os.path.join(cand, "diagnostics.json")).items() if k not in VOLATILE}
    diffs = diff(dr, dc, "diagnostics")
    r["diag_equal"] = not diffs
    if not r["semantic_equal"]:
        diffs = diff(load(sem_r), load(sem_c), "result") + diffs
    if not r["players_equal"]:
        diffs.append("players-comparable.bin differs")
    # A resumed run must not report failed stages the reference did not have.
    fc = load(os.path.join(cand, "diagnostics.json")).get("stage_failures")
    if fc:
        diffs.append(f"candidate stage_failures: {fc}")
    r["pass"] = r["semantic_equal"] and r["players_equal"] and r["diag_equal"] and not fc
    r["diffs"] = diffs[:20]
    print(json.dumps(r))
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
