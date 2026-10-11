"""Portable, bounded detector experiments. Test results never select a candidate.

Run from any directory. No installation into production and no rental API calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DATA = ROOT / "backend/ml/data/raw/shuttlecock_trajectory/TrackNetV2"
OUT = ROOT / "research/cloud_upgrade/cloud_runs"
VAL = ("match8", "match16")


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def trainer():
    sys.path.insert(0, str(ROOT / "backend/ml"))
    import train_detector
    return train_detector


def parameters(arch, device):
    # Explicit whole-match validation: never fall back to random clip splitting.
    return ["--arch", arch, "--data-root", str(DATA / "Train"),
            "--val-root", *(str(DATA / "Train" / m) for m in VAL),
            "--device", device, "--out-dir", str(OUT / arch),
            "--cache-dir", str(OUT / "cache"), "--epochs", "10",
            "--epoch-size", "2400", "--batch-size", "4", "--eval-batch-size", "4",
            "--workers", "0", "--lr", "0.0001", "--seed", "20261007",
            "--save-every", "25", "--log-every", "25"]


def preflight(device):
    import cv2
    import torch
    torch.set_num_threads(2)
    if device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable. Choose a GPU instance; CPU fallback is disabled.")
    manifest_path = ROOT / "BUNDLE_MANIFEST.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for item in manifest["files"]:
            p = ROOT / item["path"]
            if not p.is_file() or sha(p) != item["sha256"]:
                raise SystemExit(f"Bundle checksum mismatch: {item['path']}")
    t = trainer()
    train = t.discover([DATA / "Train"], allow_held_out=False)
    val = t.discover([DATA / "Train" / m for m in VAL], allow_held_out=False)
    val_media = {c.media.resolve() for c in val}
    training = [c for c in train if c.media.resolve() not in val_media]
    assert len(training) == 158 and len(val) == 14, "Incomplete dataset or changed split"
    assert not {c.name.split('/')[0] for c in training} & set(VAL)
    cap = cv2.VideoCapture(str(training[0].media))
    ok, frame = cap.read()
    cap.release()
    assert ok and frame.size > 0, "Video decoder failed"
    checks = []
    for name in ("tracknetv3", "wasb"):
        arch = t.ARCHS[name]
        t.check_conventions(arch)
        net, source = t.build_net(arch, "pretrained")
        net.to(device).eval()
        x = torch.zeros(1, 3 * arch.frames_in, 288, 512, device=device)
        with torch.no_grad():
            y = net(t.InputNorm(arch).to(device)(x))
        assert tuple(y.shape) == (1, arch.seq_len, 288, 512) and torch.isfinite(y).all()
        checks.append({"arch": name, "shape": list(y.shape), "weight_sha256": sha(arch.pretrained)})
        del net, x, y
    report = {"device": device, "torch": torch.__version__, "cuda": torch.version.cuda,
              "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
              "train_clips": len(training), "val_clips": len(val), "models": checks,
              "bundle_verified": manifest_path.exists()}
    dump(OUT / "preflight.json", report)
    print(json.dumps(report, indent=2), flush=True)


def worker(arch, device):
    t = trainer()
    import torch
    torch.set_num_threads(2)
    run = OUT / arch
    args = parameters(arch, device)
    baseline = run / "baseline.json"
    if not baseline.exists():
        # Only validation is needed here; avoid decoding the training set twice.
        val_args = ["--arch", arch, "--device", device,
                    "--data-root", str(DATA / "Train" / VAL[0]),
                    "--val-root", *(str(DATA / "Train" / m) for m in VAL),
                    "--cache-dir", str(OUT / "cache"), "--workers", "0", "--eval-only"]
        dump(baseline, t.main(val_args))
    ck_path = run / "last.pt"
    resume = torch.load(ck_path, map_location="cpu", weights_only=False) if ck_path.exists() else None
    a = t.resolve_defaults(t.make_parser().parse_args(args))
    # Ask the trainer to finish its current optimizer step and save last.pt.
    # The parent enforces a second hard deadline if loading/evaluation is stuck.
    def stop_requested(signum, frame):
        a.max_iters = 1
        print("Budget/stop requested; saving at the next optimizer step.", flush=True)
    signal.signal(signal.SIGTERM, stop_requested)
    signal.signal(signal.SIGINT, stop_requested)
    result = t.train(a, resume)
    dump(run / "summary.json", result)


def bounded_train(arch, device, hours):
    run = OUT / arch
    run.mkdir(parents=True, exist_ok=True)
    if (run / "selection.json").exists():
        raise SystemExit("Candidate already frozen; start a separately named research experiment to retrain.")
    budget_path = run / "budget.json"
    budget = json.loads(budget_path.read_text()) if budget_path.exists() else {"used_seconds": 0}
    if budget.get("running_since"):
        raise SystemExit("Previous supervisor did not exit cleanly. Inspect its process and budget before resuming.")
    remaining = hours * 3600 - budget["used_seconds"]
    if remaining <= 0:
        raise SystemExit("This experiment's time budget is exhausted.")
    started = time.monotonic()
    dump(budget_path, {**budget, "limit_hours": hours, "running_since": time.time()})
    command = [sys.executable, str(Path(__file__).resolve()), "worker", "--arch", arch, "--device", device]
    process = None
    try:
        process = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
        try:
            code = process.wait(timeout=remaining)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            process.terminate()
            try:
                code = process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                code = 124
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        dump(budget_path, {"used_seconds": budget["used_seconds"] + time.monotonic() - started,
                           "limit_hours": hours, "running_since": None})
    print("Training process ended. This does NOT stop instance billing; shut down in the rental console.", flush=True)
    if code:
        raise SystemExit(code)


def freeze(arch):
    import torch
    run = OUT / arch
    candidate = run / "best.pth.tar"
    ck = torch.load(candidate, map_location="cpu", weights_only=False)
    baseline = json.loads((run / "baseline.json").read_text())["val"]
    metrics = ck["shuttl"]["val"]
    improved = metrics["f1"] > baseline["f1"]
    selected = candidate if improved else trainer().ARCHS[arch].pretrained
    record = {"arch": arch, "path": str(selected.relative_to(ROOT)), "sha256": sha(selected),
              "baseline_f1": baseline["f1"], "candidate_f1": metrics["f1"],
              "choice": "fine_tuned" if improved else "pretrained",
              "rule": "Validation F1 only. Test is not a selection signal."}
    path = run / "selection.json"
    if path.exists() and json.loads(path.read_text()) != record:
        raise SystemExit("Selection is already frozen and cannot be changed.")
    dump(path, record)
    print(json.dumps(record, indent=2))


def test_once(arch, device):
    run = OUT / arch
    selection = json.loads((run / "selection.json").read_text())
    path = ROOT / selection["path"]
    assert sha(path) == selection["sha256"], "Selected checkpoint changed"
    report = run / "heldout.json"
    if report.exists():
        raise SystemExit("Held-out report already exists; do not tune against it.")
    t = trainer()
    a = t.resolve_defaults(t.make_parser().parse_args(parameters(arch, device)))
    net, _ = t.build_net(t.ARCHS[arch], str(path))
    result = t.eval_test(net, t.ARCHS[arch], a, device)
    dump(report, {"selection": selection, "heldout": result})
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preflight", "train", "freeze", "test", "worker"])
    parser.add_argument("--arch", choices=["tracknetv3", "wasb"], default="tracknetv3")
    parser.add_argument("--device", choices=["cuda", "cpu", "mps"], default="cuda")
    parser.add_argument("--hours", type=float, default=6.0)
    a = parser.parse_args()
    if not 0 < a.hours <= 12:
        parser.error("Use a budget between 0 and 12 hours per architecture.")
    if a.action == "preflight":
        preflight(a.device)
    elif a.action == "train":
        bounded_train(a.arch, a.device, a.hours)
    elif a.action == "worker":
        worker(a.arch, a.device)
    elif a.action == "freeze":
        freeze(a.arch)
    else:
        test_once(a.arch, a.device)


if __name__ == "__main__":
    main()
