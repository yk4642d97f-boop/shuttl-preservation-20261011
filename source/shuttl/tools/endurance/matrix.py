#!/usr/bin/env python3
"""Interruption matrix runner (resumable: finished cases are skipped).

Usage: matrix.py <cases.json> [only-case ...]
cases.json: {"clip", "uuid", "mode", "reference" (uninterrupted run dir), "timeout_s",
             "cases": [{"name", "seed"?, "prep"?: [...], "kills": [spec...],
                        "snapshot_after"?: {"<attempt index>": "<name>"}, "final"?: true}]}
Kill specs are ENDURANCE_KILL values (see driver Tracing.swift). Every attempt runs
through /tmp/heavy.sh. Results: tools/endurance/results/matrix/<case>.json + matrix.csv.
"""
import json, os, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DRIVER = os.environ.get("ENDURANCE_DRIVER", "/tmp/luna11/driver/release/EnduranceDriver")
WORK = os.environ.get("ENDURANCE_WORK", "/tmp/luna11/matrix")
SNAP = os.environ.get("ENDURANCE_SNAP", "/tmp/luna11/snapshots")
OUT = os.path.join(ROOT, os.environ.get("ENDURANCE_OUT", "tools/endurance/results/matrix"))  # + /<case-file stem>
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matrix_prep  # noqa: E402


def load1():
    return float(os.getloadavg()[0])


def attempt(cfg, case, d, i, kill):
    env = dict(os.environ)
    env.pop("ENDURANCE_KILL", None)
    if kill:
        env["ENDURANCE_KILL"] = kill
    log = os.path.join(d, f"attempt-{i}.log")
    # Correctness runs share the queue (non-exclusive label); only timing baselines (T11-base*) are exclusive.
    cmd = ["/tmp/heavy.sh", f"T11-k-{case['name']}-{i}", DRIVER, "analyze", cfg["clip"], d, cfg["uuid"], cfg["mode"]]
    rec = {"i": i, "kill": kill, "load_start": load1()}
    with open(log, "w") as f:
        p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
        try:
            rc = p.wait(timeout=cfg["timeout_s"])
        except subprocess.TimeoutExpired:
            subprocess.run(["pkill", "-9", "-f", f"analyze {cfg['clip']} {d} "])
            rc = p.wait(); rec["hang"] = True
    rec.update({"exit": rc, "load_end": load1()})
    text = open(log, errors="replace").read()
    rec["killed"] = "SIGKILL pid=" in text
    rec["finished"] = "attempt_done" in text
    rec["kill_line"] = next((l for l in text.splitlines() if l.startswith("SIGKILL")), None)
    ev = [l.split(" ", 4)[3:] for l in text.splitlines() if l.startswith("EVENT ")]
    rec["loads_hit"] = [e[1].split()[0] for e in ev if e[0] == "load_end" and "hit=true" in e[1]]
    rec["resume_frame"] = next((e[1] for e in ev if e[0] == "load_end" and e[1].startswith("detect_partial hit=true")), None)
    rec["stages_run"] = [e[1] for e in ev if e[0] == "stage_start"]
    # Evidence of where the kill landed: the last event the killed process logged.
    rec["last_event"] = " ".join(ev[-1]) if ev and rec["killed"] else None
    rec["waited_for_queue"] = text.count("[heavy]")
    return rec


def run_case(cfg, case):
    d = os.path.join(WORK, case["name"])
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    ck = os.path.join(d, "checkpoints", cfg["uuid"].lower())
    if case.get("seed"):
        src = os.path.join(SNAP, case["seed"])
        if not os.path.isdir(src):   # the case that makes this snapshot did not land its kill: a harness gap, not a product result
            return {"case": case["name"], "seed": case["seed"], "attempts": [], "notes": [f"SETUP: seed snapshot {case['seed']} missing"],
                    "compare": {"pass": False, "diffs": ["setup: seed snapshot missing"]}, "kills_landed": 0,
                    "kills_requested": len(case["kills"]), "pass": False, "status": "SETUP_MISSING",
                    "reproducer": f"python3 tools/endurance/matrix.py {cfg['_path']} {case['name']}"}
        shutil.copytree(src, ck)
    ctx = {"dir": d, "ck": ck, "notes": []}
    for op in case.get("prep", []):
        matrix_prep.apply(op, ctx)
    res = {"case": case["name"], "seed": case.get("seed"), "prep": case.get("prep", []), "attempts": []}
    try:
        kills = list(case["kills"]) + [None]
        for i, kill in enumerate(kills):
            r = attempt(cfg, case, d, i, kill)
            res["attempts"].append(r)
            snap = case.get("snapshot_after", {}).get(str(i))
            if snap and r["killed"] and os.path.isdir(ck):
                shutil.rmtree(os.path.join(SNAP, snap), ignore_errors=True)
                shutil.copytree(ck, os.path.join(SNAP, snap))
            for op in case.get("between", {}).get(str(i), []):
                matrix_prep.apply(op, ctx)
            if r["finished"] or r.get("hang") or (not r["killed"] and r["exit"] != 0):
                break
    finally:
        matrix_prep.cleanup(ctx)
    res["notes"] = ctx["notes"]
    last = res["attempts"][-1]
    cmp = subprocess.run([sys.executable, os.path.join(ROOT, "tools/endurance/compare.py"), cfg["reference"], d, case["name"]],
                         capture_output=True, text=True)
    res["compare"] = json.loads(cmp.stdout.strip().splitlines()[-1]) if cmp.stdout.strip() else {"pass": False, "diffs": [cmp.stderr[-500:]]}
    res["kills_landed"] = sum(a["killed"] for a in res["attempts"])
    res["kills_requested"] = len(case["kills"])
    res["pass"] = bool(res["compare"].get("pass")) and last["finished"] and res["kills_landed"] == res["kills_requested"]
    res["status"] = ("PASS" if res["pass"] else
                     "KILL_MISSED" if res["compare"].get("pass") and last["finished"] and res["kills_landed"] < res["kills_requested"]
                     else "FAIL")
    res["reproducer"] = f"python3 tools/endurance/matrix.py {cfg['_path']} {case['name']}"
    return res


def main():
    path = sys.argv[1]
    cfg = json.load(open(path)); cfg["_path"] = os.path.relpath(path, ROOT)
    only = set(sys.argv[2:])
    global OUT
    OUT = os.path.join(OUT, os.path.splitext(os.path.basename(path))[0])
    os.makedirs(OUT, exist_ok=True); os.makedirs(SNAP, exist_ok=True)
    for case in cfg["cases"]:
        out = os.path.join(OUT, f"{case['name']}.json")
        if (only and case["name"] not in only) or (not only and os.path.exists(out)):
            continue
        t0 = time.time()
        res = run_case(cfg, case)
        res["wall_s"] = round(time.time() - t0, 1)
        json.dump(res, open(out, "w"), indent=1)
        with open(os.path.join(OUT, "matrix.csv"), "a") as f:
            f.write(f"{case['name']},{res.get('status', 'PASS' if res['pass'] else 'FAIL')},{res['kills_landed']}/{res['kills_requested']},"
                    f"{res['compare'].get('semantic_equal')},{res['compare'].get('players_equal')},{res['wall_s']}\n")
        print(case["name"], res.get("status"), res["compare"].get("diffs", [])[:3], flush=True)


if __name__ == "__main__":
    main()
