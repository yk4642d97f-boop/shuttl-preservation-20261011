#!/usr/bin/env python3
"""Memory curves + per-run table for the uninterrupted runs.

Usage (backend/.venv python, has matplotlib): plot.py <run-dir> [<run-dir> ...]
Writes, for each run, tools/endurance/results/<label>/{memory.png,memory.csv,summary.json,
timing.txt,events.log} and a combined memory-all.png + uninterrupted.csv.
"""
import csv, json, os, shutil, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "tools/endurance/results")
STAGES = ["detect", "link", "calibrate", "players", "hits", "reconstruct3d", "rallies", "shots", "score"]


def rows(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def load_range(timing):
    lines = open(timing).read().splitlines()
    ups = [l for l in lines if "load averages" in l]
    one = [float(u.split("load averages:")[1].split()[0]) for u in ups]
    return one


def main():
    table = []
    fig_all, ax_all = plt.subplots(figsize=(11, 5))
    for d in sys.argv[1:]:
        label = os.path.basename(d.rstrip("/"))
        out = os.path.join(RES, label); os.makedirs(out, exist_ok=True)
        for n in ["memory.csv", "summary.json", "events.log", "live-stage-metrics.jsonl"]:
            if os.path.exists(os.path.join(d, n)):
                shutil.copy(os.path.join(d, n), out)
        timing = os.path.join(RES, f"timing-{label}.txt")
        if os.path.exists(timing):
            shutil.copy(timing, os.path.join(out, "timing.txt"))
        r = rows(os.path.join(d, "memory.csv"))
        t = [float(x["elapsed_seconds"]) / 60 for x in r]
        fp = [float(x["phys_footprint_mb"]) for x in r]
        ck = [int(x["checkpoint_bytes"]) / 2**20 for x in r]
        fig, ax = plt.subplots(figsize=(11, 5))
        ax.plot(t, fp, lw=1, label="phys_footprint MB")
        ax.plot(t, ck, lw=1, label="checkpoint dir MB")
        prev = None
        for x, row in zip(t, r):
            if row["stage"] != prev:
                ax.axvline(x, color="grey", lw=0.4); ax.text(x, max(fp) * 1.01, row["stage"], rotation=90, fontsize=7, va="bottom")
                prev = row["stage"]
        ax.set_xlabel("minutes"); ax.set_ylabel("MB"); ax.set_title(f"{label}: memory over time (1 s samples)"); ax.legend()
        fig.tight_layout(); fig.savefig(os.path.join(out, "memory.png"), dpi=110); plt.close(fig)
        ax_all.plot(t, fp, lw=1, label=label)
        s = json.load(open(os.path.join(d, "summary.json")))
        st = s["stage_diagnostics"]["stages"]
        peak_by_stage = {}
        for row in r:
            peak_by_stage[row["stage"]] = max(peak_by_stage.get(row["stage"], 0), float(row["phys_footprint_mb"]))
        loads = load_range(timing) if os.path.exists(timing) else []
        rec = {"run": label, "minutes": round(s["video_frames"] / s["fps"] / 60, 1),
               "total_s": round(s["pipeline_seconds"], 1),
               **{f"{k}_s": st.get(k, {}).get("seconds") for k in STAGES},
               **{f"{k}_peak_mb": round(peak_by_stage.get(k, 0), 1) for k in ["detect", "link", "calibrate", "players", "reconstruct3d", "idle"]},
               "run_peak_mb": max(float(x["peak_phys_footprint_mb"]) for x in r),
               "ckpt_peak_mb": round(s["checkpoint_bytes"]["peak_during_run"] / 2**20, 1),
               "archive_json_mb": round(s["archive_json_bytes"] / 2**20, 2),
               "players_bin_mb": round(s["players_bin_bytes"] / 2**20, 2),
               "camera": s["camera_found"], "hits": s["hits"], "rallies": s["rallies"], "shots": s["shots"],
               "players": s["players"], "load_start": loads[0] if loads else None, "load_end": loads[-1] if loads else None,
               "timing_reliable": bool(loads) and max(loads) < 8}
        table.append(rec)
    ax_all.set_xlabel("minutes"); ax_all.set_ylabel("phys_footprint MB"); ax_all.legend(); ax_all.set_title("All uninterrupted runs")
    fig_all.tight_layout(); fig_all.savefig(os.path.join(RES, "memory-all.png"), dpi=110)
    with open(os.path.join(RES, "uninterrupted.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0])); w.writeheader(); w.writerows(table)
    for rec in table:
        print(json.dumps(rec))


if __name__ == "__main__":
    main()
