# Resumed detect silently changes the result: a background segment is overwritten after resume (SILENT-WRONG)

Found by the 45-min SIGKILL matrix, case detect-chain-A (5 kills in detect, then finish): FAIL.
vs the uninterrupted base-45m (same driver build 13:51, same clip): hits 1323 = 1323 but hit frames differ, 97 hit
confidences differ (max 0.82), rally winners differ; track differs in 2036 frames, all but 2 in 108000-115199.
Control: base-45m-doublespath (uninterrupted, same detect) is byte-identical in track → detect itself is deterministic.

Cause (proved from the saved checkpoint, no rerun needed):
detect_partial.bin (snapshot /tmp/luna11/snapshots/late-detect, next=115200) holds TWO background records.
Record 1 was written by attempt 1 (fresh run, bgData = the plan it estimated). Record 2 was written by attempt 3, which
resumed at 43200: `detectFrames` re-serialises `usedPlan` on its first checkpoint after a resume (Resume.swift:109,
bgData == nil). Between the two, segment 15 (frames 108000-115199) CHANGED in memory: 3.7 % of pixels, rows 96-106
all zero, the picture shifted down ~11 rows (seg15_before_after.png: left = record 1, right = record 2). Every other
segment is bit-identical. Frames 108000-115199 were then detected against the damaged background → different
candidates → different track/hits/winners. The app shows "分析完成" — nothing flags it.

Likely fault: the deserialised BackgroundPlan images alias memory that is later written during detection — e.g. a
NetImage from `BackgroundPlan.deserialize` (Resume.swift:54-56) or `medianImage` sharing a buffer with
NetImagePool / the mirror pool (`mirror($0, flipPool)` HeatmapDetector.swift ~210) or the warp target. Owner (B,
ShuttlDetector) to confirm with ASan/TSan; E did not modify code.

Suggested fix (not applied): (1) give every BackgroundPlan image its own freshly allocated, never-pooled storage and
never pass plan images to a pool or as a write target; (2) serialise the background ONCE when estimated and on resume
keep the loaded bytes (bgData = r.background) instead of re-serialising the in-memory plan; (3) add a test: resume
from a checkpoint, run N windows, assert plan images are bit-identical to the loaded ones.

Repro (≈ 3 × 2-4 min on this Mac, via the queue):
    /tmp/heavy.sh T11-k-repro-bg tools/endurance/repro/bg-corrupt-after-resume/run.sh
  uses /tmp/luna11/repro-bg/detect_partial.bin = clean 43200-frame prefix of the snapshot (record 1 only) and
  /tmp/luna11/clips/singles_45m.mp4; check.py prints the segments that changed vs the clean plan.
Offline check of the existing evidence (instant):
    backend/.venv/bin/python tools/endurance/repro/bg-corrupt-after-resume/check.py \
      /tmp/luna11/repro-bg/detect_partial.bin /tmp/luna11/snapshots/late-detect/detect_partial.bin
    # -> segments changed vs clean plan: [15] seg 15: 3.704% px, zero rows [96, 97, 98]..

## Live repro result (2026-09-29 11:27-11:37): NOT reproduced in 3/3 trials → intermittent
Each trial resumed from the clean 43200-frame checkpoint and was killed 1 s after the next save (next=50400).
All 3: "bg records in resumed file: 1; segments changed vs clean plan: []" (no second background record, plan intact).
In the matrix run the damage appeared in attempt 3 between load (23.5 s) and its first save (55.0 s) under heavy
machine load. So it is timing/concurrency dependent (a data race or a use-after-reuse of pooled memory), not a
deterministic function of the resume point. Implications for the fix: (a) prove it with ASan/TSan and a stress test
(many resumes, parallel load), not a single resume; (b) the check "segments changed vs clean plan" must be []
across repeated trials; (c) E will re-run every detect-resuming 45m matrix case after the fix, as the monitor asked.
Note the second record in the matrix file exists only because the in-memory plan no longer matched the loaded bytes
(DetectPartial.swift:36 appends a background record when c.background != p.background) — a cheap runtime tripwire:
on resume, compare usedPlan.serialized() with r.background before each save and log/abort if they differ.
