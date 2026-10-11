#!/usr/bin/env python3
"""Read-only benchmark of adaptive zlib; never writes source or archive data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import time
import zlib

CHUNK = 64 * 1024 * 1024


def choose_level(data):
    if len(data) < 1024 * 1024:
        return 1, None
    width = 64 * 1024
    span = len(data) - width
    sample = b"".join(data[(span * i) // 3:(span * i) // 3 + width] for i in range(4))
    ratio = len(zlib.compress(sample, 1)) / len(sample)
    return (0 if ratio >= 0.99 else 1), ratio


def measure(label, data, repeats):
    baseline, adaptive = [], []
    level, ratio = choose_level(data)
    expected = hashlib.sha256(data).hexdigest()
    for _ in range(repeats):
        start = time.perf_counter()
        old = zlib.compress(data, 1)
        baseline.append(time.perf_counter() - start)
        start = time.perf_counter()
        selected, _ = choose_level(data)
        new = zlib.compress(data, selected)
        adaptive.append(time.perf_counter() - start)
        assert hashlib.sha256(zlib.decompress(new)).hexdigest() == expected
        assert hashlib.sha256(zlib.decompress(old)).hexdigest() == expected
    old_time, new_time = statistics.median(baseline), statistics.median(adaptive)
    return {"label": label, "raw_bytes": len(data), "selected_level": level, "sample_ratio": ratio,
            "level1_seconds": baseline, "adaptive_seconds_including_sample": adaptive,
            "median_speedup": old_time / new_time, "level1_stored_bytes": len(old),
            "adaptive_stored_bytes": len(new), "adaptive_MiB_per_second": len(data) / 1048576 / new_time,
            "raw_sha256": expected, "roundtrip_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    cases = []
    with args.source.open("rb") as f:
        cases.append(("actual-tar-gz-first-64MiB", f.read(CHUNK)))
        f.seek((args.source.stat().st_size // 2 // CHUNK) * CHUNK)
        cases.append(("actual-tar-gz-middle-64MiB", f.read(CHUNK)))
    cases.append(("random-64MiB", os.urandom(CHUNK)))
    cases.append(("compressible-64MiB", (b"Shuttl backup fixture\0\xff" * (CHUNK // 22 + 1))[:CHUNK]))
    results = []
    for label, data in cases:
        result = measure(label, data, args.repeats)
        results.append(result)
        print(json.dumps(result), flush=True)
    args.output.write_text(json.dumps({"source": str(args.source), "repeats": args.repeats, "results": results}, indent=2) + "\n")


if __name__ == "__main__":
    main()
