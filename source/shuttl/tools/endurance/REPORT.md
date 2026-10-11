# Task 11 — long-match endurance: FINAL REPORT (2026-09-30)

All numbers are from the **v2 runs on the current packages** (driver built 2026-09-29 15:27, after B's background fix,
A's players-memory fix and C's rally/shots changes), unless marked v1 (2026-09-28 build) or v3/v4 (re-checks after C addendum 3
and A's full-disk fix). The earlier v1 report is kept in `results/REPORT-v1-1208.md`.

## Verdict

- **Every clip ran to the end with a correct result**: 10, 45 and 90 minutes of 1080p60 singles, 45 minutes in HEVC, and the
  45-minute doubles path. No crash, no empty result. Memory is bounded and grows about 4 MB per recorded minute.
- **Interruption matrix: 24 cases ran, 23 PASS + 1 KILL_MISSED, 0 FAIL** (`results/matrix-v2/`; a 25th row, diskfull-detect,
  is SETUP_MISSING and was replaced by make-mid-detect + diskfull-detect-2). Every case that ran finished byte-equal to the
  uninterrupted run. The miss was in my harness: some kills fired after the stage they targeted had already ended.
- **Two real defects found by this task, both fixed by their owners and re-run:**
  1. Resumed detect silently changed the result (a background segment was damaged in memory) → B fixed it 2026-09-29 15:02 →
     `detect-chain-A` (5 kills in detect) FAIL → PASS.
  2. On a full disk, the detect progress was deleted although the candidates had not been saved, so detect restarted from frame 0
     after the next interruption → A fixed it 2026-09-30 07:02 → re-run (v4, fresh driver): after the kill, the resume loads
     detect_partial (hit=true, next=43200) and detect takes 323 s instead of 689 s from frame 0; result byte-equal. PASS
     (`results/matrix-v4/`).
- Largest memory risk against the iPhone 16 Pro (assumption: about 3 GB usable by the app): the in-memory players array at the end of
  the players stage. Measured 535 MB peak at 90 minutes on the Mac; predicted about 0.96 GB on the phone.

## Clips (`/tmp/luna11/clips`, built by `driver/.../ClipMaker.swift`)

Built from 11 different rallies of TrackNetV2 Test/match1 (one camera), shuffled per pass, with 8-20 s of frozen dead time between
rallies. Upscaled to 1920×1080 at 60 fps (the 30 fps source → every frame shown twice). No doubles footage exists in any available
dataset, so the "doubles" run uses singles footage with `PipelineOptions(doubles: true)`.

| clip | size | frames |
|---|---|---|
| singles_10m.mp4 (H.264) | 1.18 GB | 36 000 |
| singles_30m.mp4 (H.264) | 3.53 GB | 107 999 |
| singles_45m.mp4 (H.264) | 5.31 GB | 161 999 |
| singles_45m_hevc.mov (HEVC) | 4.73 GB | 161 999 |
| singles_90m.mp4 (H.264) | 10.61 GB | 324 000 |

## Uninterrupted runs (v2; `results/uninterrupted.csv`, `results/<run>-v2/memory.png`, `results/memory-all.png`)

| run | total | detect | players | peak MB | checkpoint dir peak | archive JSON + players.bin | hits / rallies / shots | load start→end |
|---|---|---|---|---|---|---|---|---|
| 10 min | 368 s | 142 s | 219 s | 209 | 36 MB | 5.3 + 4.9 MB | 305 / 22 / 300 | 2.6→2.7 |
| 45 min | 1556 s | 636 s | 890 s | 349 | 165 MB | 23.5 + 22.2 MB | 1323 / 101 / 1295 | 8.6→3.8 * |
| 45 min HEVC | 1978 s | 668 s | 1284 s | 309 | 165 MB | 23.4 + 22.2 MB | 1336 / 103 / 1324 | 2.3→2.0 |
| 45 min doubles path | 1961 s | 663 s | 1270 s | 306 | 166 MB | 23.6 + 22.3 MB | 1323 / 101 / 1296 | 2.0→1.0 |
| 90 min | 3907 s | 1339 s | 2503 s | 535 | 331 MB | 47.1 + 44.5 MB | 2631 / 202 / 2599 | 2.3→2.5 |

\* The start load of 8.58 is just above my rule of 8, so this row's timing counts as unreliable. The v3 re-run of the same clip
(load 2.5→3.7, reliable) gives detect 647 s and players 1172 s.

Camera found in every run. Players stage time varies by ±25 % between runs of the same length (890-1284 s at 45 min) with other
agents' jobs on the machine; detect is stable (636-668 s).

**Memory over time.** Detect runs at 80-200 MB and rises slowly with length (≈ 1 MB per minute). The players stage climbs linearly
(the in-memory `[PlayerObservation]` array, ≈ 510 B per observation). At the end of players, hits and reconstruct3d hold the whole
array, which gives the run peak. The players checkpoint save no longer adds a spike: 90-min save = 0.27 s, footprint flat (v1 had
+64 MB there; A streamed the save). **Only the players array grows with match length**, at about 4.1 MB per recorded minute.

## Interruption matrix (in-process SIGKILL; `results/matrix-v2/`)

Kills are real SIGKILLs from a dedicated thread (`ENDURANCE_KILL`), placed at a progress fraction, a time after a stage start, or a time
after a checkpoint write begins. After each kill the same command is run again. The case passes when the final
`semantic-result.json` and players file are byte-equal to the uninterrupted v2 reference.

| case | kills | result |
|---|---|---|
| 10-min smoke: s-detect-chain / s-players / s-players-write / s-post-players / s-torn-partial | 2 / 1 / 1 / 2 / 0 | 5 PASS |
| detect-chain-A (progress 0.14-0.41), detect-chain-B (0.19-0.48) | 5 + 5 | PASS, PASS |
| detect-partial-write (during the detect_partial write) | 3 | PASS |
| double-resume-immediate (a second kill 4 s after the restart) | 2 | PASS |
| players-chain (10 kills in players) | 10 | PASS |
| players-write (during the 150 MB players write) | 3 | PASS |
| post-players-chain (hits, reconstruct3d, rallies, shots, score) | 50 | PASS |
| link-calibrate-chain | 14 / 24 landed | KILL_MISSED: calibrate took 1.6 s vs 2.6 s in the reference, so late kills found no calibrate; result equal |
| calibrate-chain-short (added to cover calibrate) | 10 | PASS |
| candidates-write | 3 | PASS |
| partial delete: pd-rm-candidates, pd-truncate-players (50 %), pd-garbage-camera | 0 | 3 PASS |
| torn detect progress file: pd-torn-partial-31 / 77 / 97 % | 0 | 3 PASS |
| disk full (200 MB APFS image via hdiutil, deleted after): diskfull-players (20.6 MB free), diskfull-detect-2 (5.2 MB free) | 0 / 1 | 2 PASS on the result; diskfull-detect-2 exposed defect 2 above |

Two resumes in a row: covered by the chains (detect-chain-A resumed 4 times, post-players-chain 50 times) and by double-resume-immediate.
Before B's fix (v1 build) detect-chain-A FAILED: 97 hit confidences, hit frames and rally winners differed, with track differences in
frames 108 000-115 199 (`results/matrix/pre-bgfix/`).

## Scale model and phone prediction (PREDICTION, not measured on a phone)

Linear fits over the v2 10 / 45 / 90-minute runs (M = recorded minutes, Mac M4, load ≈ 2):
detect ≈ 15.0 s × M, players ≈ 28.9 s × M − 190 s, other stages < 15 s in total, peak memory ≈ 167 MB + 4.1 MB × M.

Phone/Mac ratios come from the same 1-min 1080p60 clip measured on both (`.agent-logs/device-measure.log`, 2026-09-28):
detect 17.9 / 30.3 s = 0.59 (ANE), players 33.9 / 19.8 s = 1.72 (Vision), peak memory 398 / 222 MB = 1.79.

| match | Mac (measured) | phone (predicted) | phone peak memory (predicted) |
|---|---|---|---|
| 10 min | 6 min | ≈ 8 min | ≈ 0.37 GB |
| 45 min | 26 min | ≈ 32 min | ≈ 0.63 GB |
| 90 min | 64 min | ≈ 82-85 min | ≈ 0.96 GB |
| 90 min doubles (4 players; estimate: players time and array ×2) | — | ≈ 155 min | ≈ 1.6 GB |

Caveats: the phone ratio comes from ONE minute of video; thermal throttling ("serious" after about 5 minutes of back-to-back
analysis on the phone) will slow long matches, so treat the table as a lower bound on phone time. The largest memory risk is the
players array. Even the doubles estimate is about half of the assumed 3 GB, but it has not been measured. The only lever left is
the data layout (for example Float32 keypoints; B, optional).

## Codec sensitivity (not a robustness defect; routed to C)

Same 45-min content, H.264 vs HEVC (v2): 99 rally pairs, 61 same winner, 38 different. 37 of the 38 are flagged 不确定, plus
1 confident flip. C found the flip was a real confidence defect and fixed it (addendum 3, 2026-09-30 06:05).
Re-check on the phone path (v3, fresh driver after addendum 3, load ≈ 3): 99 pairs, 61 same, 38 different, **0 unflagged differences**
(every difference is marked 不确定 in at least one run); pairs with confidence ≥ 0.6 in both: 11, agree 11. Rally 77495: 0.5 / 0.5, both
uncertain. Uncertain rate 0.78 / 0.81. Footage is broadcast 30 fps upscaled, not a tripod iPhone recording.

## Findings and fixes (all re-verified)

| finding | severity | location | fix | re-run |
|---|---|---|---|---|
| Resumed detect silently changes results (background segment damaged in memory) | HIGH, silent wrong on the phone after any interruption | ShuttlDetector BackgroundPlan / Resume.swift | B: sealed read-only plan, per-segment digests → `backgroundChanged` (retryable, A), re-save of the loaded bytes | detect-chain-A/B, detect-partial-write, double-resume, torn-partial ×3: PASS |
| Full disk deletes detect progress | MEDIUM, lost resume only | ShuttlAnalysis AnalysisPipeline.swift:76 | A: clear only when candidates reload from the store | v4 diskfull-detect-2: resume from 43 200 frames, detect 323 s (was 689 s from 0), PASS |
| Players save memory spike (v1: 516 → 580 MB) | LOW | PlayersCodec | A: streamed save; load leak fixed 572 → 323 MB | 90-min peak 580 → 535 MB, save flat |
| Harness only: kill after stage end, missing seed snapshot | — | tools/endurance make_cases.py / matrix.py | kills ≤ 0.75 × stage time; SETUP_MISSING / KILL_MISSED labels | — |

Repro commands: `tools/endurance/repro/*/README.md`; any matrix case: `python3 tools/endurance/matrix.py <cases.json> <case>`.

## What could not be verified (needs a real iPhone)

ANE speed over a long match, thermal throttling, the jetsam memory limit (3 GB is an assumption), iOS background suspension and
lock-screen behaviour, and 4-player doubles memory (no footage). **Lock screen:** on this Mac every interruption point resumes exactly,
including SIGKILL at any stage and during every checkpoint write. So when iOS suspends or kills the app, it will continue from the
last checkpoint without a wrong result. Whether iOS lets the analysis keep running while the screen is locked has to be checked on
the phone.

## Files

`tools/endurance/`: driver/ (EnduranceDriver: analyze + in-process SIGKILL + TracingStore), run-one.sh, run-timed.sh, matrix.py,
matrix_prep.py (rm / truncate / garbage / hdiutil disk-full), make_cases.py, compare.py, plot.py, cases/, repro/, results/.
Generated clips in /tmp/luna11/clips (24 GB, listed above) are KEPT until the final gate and phone test pass, so that any repro can
be re-run without regenerating them (about 1 h). Free disk is 212 GB. Delete with `rm -rf /tmp/luna11/clips` once the monitor closes the project.
