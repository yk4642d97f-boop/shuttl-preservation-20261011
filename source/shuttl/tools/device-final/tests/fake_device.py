#!/usr/bin/env python3
"""Fake `xcrun devicectl` for the OFFLINE v5 self-test. It never calls the real xcrun.

State dir = $V5_OFFLINE (was $V4_OFFLINE in v4): clock (virtual UTC epoch, advanced by nap and by
these calls), scenario (replay | never), calls.log (every call, with the virtual time). The phone's
data comes from replay_0930.snapshot(), i.e. the saved 09-30 evidence: rows appear at their real
ingest times, whatever the script does (the drain delay is replayed faithfully).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_0930  # noqa: E402

# V5: use V5_OFFLINE, fallback to V4_OFFLINE for compatibility
STATE = Path(os.environ.get("V5_OFFLINE") or os.environ.get("V4_OFFLINE", ""))


def clock() -> float:
    return float((STATE / "clock").read_text().strip())


def advance(s: float) -> None:
    # V5_MAC_SLEEP_AT: inject a 1900 s sleep gap at this wall-clock second
    sleep_at = int(os.environ.get("V5_MAC_SLEEP_AT", "0"))
    if sleep_at and clock() < sleep_at <= clock() + s:
        (STATE / "clock").write_text(f"{int(clock() + s + 1900)}\n")
        note("MAC SLEEP INJECTED (1900 s)")
    else:
        (STATE / "clock").write_text(f"{int(clock() + s)}\n")


def note(msg: str) -> None:
    t = datetime.fromtimestamp(clock(), timezone.utc).strftime("%H:%M:%SZ")
    with open(STATE / "calls.log", "a") as f:
        f.write(f"{t} {msg}\n")


def opt(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None


def main(argv: list[str]) -> int:
    if argv[:1] != ["devicectl"]:
        note(f"UNKNOWN {argv}")
        return 99
    a = argv[1:]
    if a == ["--t-fake-probe"]:
        print("T-FAKE-DEVICE")
        return 0
    if not STATE.is_dir():
        return 98
    scenario = (STATE / "scenario").read_text().strip() if (STATE / "scenario").exists() else "replay"
    if a[:2] == ["list", "devices"]:
        print("Name        Hostname   Identifier                             State                Model")
        print("iPhone 16 Pro (fake)  -  0F92DDA9-7A87-4F05-8368-0E834177D8F3   available (paired)   iPhone17,1")
        note("list devices")
        return 0
    if a[:3] == ["device", "install", "app"]:
        note(f"install {a[-1]}")
        print("App installed:\n• bundleID: com.ycyangcong.shuttl")
        return 0
    if a[:3] == ["device", "info", "lockState"]:
        print("passcodeRequired: false\nunlockedSinceBoot: true (unlocked)")
        return 0
    if a[:3] == ["device", "info", "processes"]:
        out = opt(a, "--json-output")
        Path(out).write_text(json.dumps({"result": {"runningProcesses": [
            {"processIdentifier": 4242, "executable": "file:///private/var/containers/Bundle/Application/X/Shuttl.app/Shuttl"}]}}))
        note("info processes")
        return 0
    if a[:3] == ["device", "process", "launch"]:
        # V2: reject app arguments not after `--`, like the real devicectl
        bundle_idx = next((i for i, x in enumerate(a[3:], 3) if not x.startswith("-") and "." in x), None)
        if bundle_idx is not None:
            sep_idx = next((i for i, x in enumerate(a[bundle_idx + 1:], bundle_idx + 1) if x == "--"), None)
            app_args = [x for x in a[bundle_idx + 1:] if x.startswith("-") and x != "--"]
            if app_args and (sep_idx is None or any(a.index(x) < sep_idx for x in app_args)):
                # App argument before `--` → error like real devicectl
                bad_arg = next(x for x in app_args if sep_idx is None or a.index(x) < sep_idx)
                print(f"error: The value '{bad_arg.lstrip('-').split('=')[0] if '=' in bad_arg else 'matches'}' is invalid for '-t <seconds>'", file=sys.stderr)
                note(f"launch REJECTED (app arg {bad_arg} before --)")
                return 1
        advance(3)
        note("launch " + " ".join(a[3:]))
        return 0
    if a[:3] == ["device", "process", "signal"]:
        note(f"signal {opt(a, '--signal')} pid {opt(a, '--pid')}")
        return 0
    if a[:3] == ["device", "copy", "to"]:
        src, dst = opt(a, "--source"), opt(a, "--destination")
        advance(25 if "10min" in (src or "") else 8)
        note(f"PUSH {dst}")
        return 0
    if a[:3] == ["device", "copy", "from"]:
        src, dst = opt(a, "--source") or "", Path(opt(a, "--destination") or "")
        advance(1)
        snap = replay_0930.snapshot(clock(), dst.parent / ".fake-snap", scenario=scenario, synthetic=True)
        name = Path(src).name
        if name in ("default.store-wal", "default.store-shm"):
            dst.write_bytes(b"")
        else:
            dst.write_bytes((snap / name).read_bytes())
        for f in snap.iterdir():
            f.unlink()
        snap.rmdir()
        return 0
    note(f"UNKNOWN devicectl {a}")
    return 99


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
