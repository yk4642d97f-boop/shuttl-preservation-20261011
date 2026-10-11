"""Freeze a validation-selected candidate, then score once on isolated matches.

Reports per-match numbers and paired match-bootstrap uncertainty, never retunes.
"""
import argparse
import json
from pathlib import Path
import time

import numpy as np
import torch

import hit_experiment as E


def measure(paths, partition):
    models = E.load_models(paths)
    ids, rallies = E.load_partition(partition)
    rows = {}
    for mid in ids:
        rr = [r for r in rallies if r["mid"] == mid]
        begin = time.monotonic()
        m = E.evaluate(models, rr)
        m["seconds"] = time.monotonic() - begin
        m["frames"] = sum(len(r["raw"]) for r in rr)
        rows[mid] = m
    counts = {str(t): np.sum([r["counts"][t] for r in rows.values()], axis=0).tolist() for t in (1, 2, 4)}
    return {"per_match": rows, "counts": counts,
            "f1_at_2": E.C.scorelib.prf(*counts["2"])[2],
            "serve": np.sum([r["serve"] for r in rows.values()], axis=0).tolist(),
            "rally": np.sum([r["rally"] for r in rows.values()], axis=0).tolist()}


def bootstrap(old, new, seed=20261007):
    ids = sorted(old["per_match"])
    a = np.array([old["per_match"][i]["counts"][2] for i in ids])
    b = np.array([new["per_match"][i]["counts"][2] for i in ids])
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(ids), (10000, len(ids)))
    ac, bc = a[indices].sum(1), b[indices].sum(1)
    delta = 2 * bc[:, 0] / (2 * bc[:, 0] + bc[:, 1] + bc[:, 2]) - 2 * ac[:, 0] / (2 * ac[:, 0] + ac[:, 1] + ac[:, 2])
    return {"delta_f1_at_2": new["f1_at_2"] - old["f1_at_2"],
            "paired_match_bootstrap_95pct": np.quantile(delta, [0.025, 0.975]).tolist(),
            "matches": len(ids), "note": "Small number of matches; not a venue/domain generalization guarantee."}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", type=Path, required=True)
    args = ap.parse_args()
    torch.set_num_threads(2)
    old = [E.HIT / "ckpt" / (k + ".pt") for k in ("tcn_s0", "tcn_s1", "tcn_lr")]
    candidate = args.candidate.resolve()
    ck = torch.load(candidate, map_location="cpu", weights_only=False)
    assert not set(ck["train_matches"]) & set(E.VAL + E.AUDIT + E.TEST)
    freeze = {"candidate": str(candidate), "sha256": E.sha(candidate), "epoch": ck["epoch"],
              "val_f1": ck["val_f1"], "manifest_sha256": E.sha(E.HERE / "data_manifest.json"),
              "decoder": E.DECODER, "selection": "Maximum pooled validation F1@2; test/audit unseen by this experiment"}
    freeze_path = E.HERE / "selection.json"
    if freeze_path.exists():
        assert json.loads(freeze_path.read_text()) == freeze, "Candidate already frozen; do not tune using test feedback"
    else:
        E.write_json(freeze_path, freeze)
    result = {"selection": freeze, "scope": "Annotated singles rallies only; fixed 0.4/0.30 decoder; predicted hits, no shift"}
    for part in ("val", "audit", "test"):
        arms = {"old_single": measure(old[:1], part), "old_ensemble3": measure(old, part),
                "candidate_single": measure([candidate], part)}
        arms["comparison"] = bootstrap(arms["old_ensemble3"], arms["candidate_single"])
        result[part] = arms
        E.write_json(E.HERE / "comparison.json", result)
        print(part, json.dumps({k: {"f1_at_2": v["f1_at_2"], "serve": v["serve"]}
                               for k, v in arms.items() if k != "comparison"}), flush=True)
        print("comparison", json.dumps(arms["comparison"]), flush=True)


if __name__ == "__main__":
    main()
