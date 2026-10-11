# Task 10 — robustness torture test: FINAL REPORT (2026-09-30)

Every number below was measured on the tree as of 2026-09-29/30, after all owner fixes, unless marked "pre-fix".
Earlier handoff versions are kept in `raw_1638/REPORT-1215.md` and `raw_1638/报告-1213.txt`.

## Verdict

- **55 / 55 corpus inputs are OK on both engines** (Swift app path and Python server path; `results.csv`).
  No CRASH, HANG, OOM, SILENT-EMPTY or IMPLAUSIBLE result remains.
- **Cancel / resume / checkpoint matrix: 91 / 91 green on one build** (`matrix_live.jsonl`, driver rebuilt 2026-09-29 15:05):
  2 identical reference runs, 27 real `Task.cancel()` cases across all 9 stages, 2 cancels after a detect-partial save,
  1 double interruption, and 57 checkpoint mutations. Every one resumed to a result equal to the uninterrupted run.
- **Every non-OK finding was fixed by its owner, and each reproducer was re-run afterwards** (table below).

## Findings, ranked by severity (all FIXED and re-verified)

| # | Severity | Finding | Fault location | Fix (owner, time) | Re-run evidence |
|---|---|---|---|---|---|
| 1 | CRASH on phone, repeats at every launch | A `track.json` checkpoint whose arrays differ in length makes resume trap (SIGTRAP "Index out of range"). `resumePending()` runs at launch and on every return to the foreground. | `Track2D.init(from:)` ShuttlCore/DataTypes.swift:73-81 (no length check); trap in `Hits.preferRaw` ShuttlHits/Observations.swift:30 | B 09-28 23:41: `Track2D.inconsistency` → DecodingError → cache miss; C: preferRaw guard | `repro/track-len-mismatch`: exit 133 → 0, signature = reference; also with a valid sha256 (`store-v2`), so B's check works on its own |
| 2 | CRASH (trap), latent | A structurally wrong `camera.json` hits `precondition` in `simd_double3x3(rowMajor:)` | ShuttlCore Camera.swift:129-130, LinearAlgebra.swift:114 | Shape checks in Camera.swift (09-28 19:01) + CameraDecodeTests (B) | matrix mutate: `valid_json_K_two_rows`, `t_two_values`, `K_nan` → EQUAL |
| 3 | SILENT-WRONG after corruption | A checkpoint with a valid shape but flipped bits or edited values is accepted, so the result changes while the app says "done" (9 of 57 mutations pre-fix) | ShuttlAnalysis AnalysisStages.swift: no value checksum | A 09-29 10:19: `{"fingerprint","sha256","value"}` layout, digest over the stored value bytes (AnalysisStages.swift:173-205) | mutate 57 / 57 EQUAL (pre-fix 47 EQUAL + 9 DIFFERENT + 1 CRASH; pre-fix rows in `raw_1638/matrix_live-2045.jsonl`) |
| 4 | SILENT-EMPTY on server mode | 0 rallies stored as status "done" by the backend, and the app server path set `.done` without an outcome check | backend tasks.py; iOS MatchPipeline.swift fetchResults | A: MatchPipeline throws `analysisUnusable(.noRallies)` (09-28 19:13); tasks.py `unusable_reason` → `AnalysisUnusable`, status failed, never retried (09-29 10:01) | Python sweep: 41 clips → "没有看到羽毛球…", 1 → "没有找到完整的回合", 13 done; `repro/F2-server-silent-empty` |
| 5 | IMPLAUSIBLE (F3) | One 5.03 s PTS jump → a landing at (-11.1, -0.3) m, 4.4 m behind the near baseline, still decides a point; "分析完成。" on both engines | no plausibility gate on the 3-D landing; fits across the gap | A LandingGuard (result level), C 3-D landing gate in rally.py + ShuttlRally (09-29 23:32), B reconstruct3d never fits across a PTS gap | `repro/F3-timestamp-jump-landing`: implausible [] on both engines. Residual: rallies Swift 2 / Python 1 (accepted by the monitor 00:12) |
| 6 | Wrong speed (F4) | One 13-frame drop: Swift 29.9 km/h, Python 7.9, vs 65.8 without the gap. The smash contact is the first frame after the gap. | ShuttlHits / hits.py: no hit emitted at a gap contact | C addendum 2 (09-30 01:49): `gap_contacts`, `HitEvent.source = "gap_contact"` | `repro/F4-dropped-frames-speed`: both engines hits [50, 61, 100], 63.7 / 64.2 km/h (no-gap control 65.8 / 65.9) |
| 7 | PY/SWIFT DIVERGENCE (F1) | The Python/server path ignored rotation metadata, so the same clip gave Python 1 rally and Swift 0 | backend video_io.py | B 09-29 09:57: frames rotated upright like VideoIO.swift | `repro/F1-py-rotation-ignored`: both engines size 720×1280, hits [73, 111], 0 rallies, same Chinese message |
| — | Expected, not a bug (F5) | Duplicate PTS: Swift 130 frames vs Python 133 | AVFoundation delivers each PTS once | coordinator 09-28 16:50: Apple writers never produce duplicate PTS | unchanged; same hits and rally |

Linker lead from the task (`_weak_unsupported` IndexError on 192×144): already fixed before this task (linker.py:504-535).
`pytest tests/test_linker.py::test_weak_only_candidates` passed 3/3. 192×144 is OK on both engines.

## Corpus (55 inputs, `generate.py`, seed 81010, 26 MB; `corpus/manifest.json`)

| Group | Inputs | Result (Swift app / Python server) |
|---|---|---|
| Corrupt / empty | empty.mp4 (0 B), cut_moov, cut_mdat | clear failure "AI 分析失败：cannot open video" on both |
| No video track | audio_only.wav, real_audioonly.mov | clear failure "no video track" on both |
| Length | one_frame, five_frames, half_second, two_seconds, one_window, window_minus, window_plus | clear no-shuttle failure on both |
| Resolution / orientation | 192x144, 640x360, 1280x720, 1920x1080, 4k, portrait 1080x1920, odd 1918x1078 | clear failure on both; 4K Swift peak 192.7 MB |
| Rotation metadata | h264_rot0/90/180/270, hevc_rot0/90/180/270, real_rot90 | clear failure; real_rot90 identical on both after F1 |
| Frame rate | 24 / 25 / 30 / 50 / 60 / 120 / 240 fps | clear failure on both |
| Codec / container | real_hdr10 (HEVC 10-bit HLG, BT.2020), real_longgop (B-frames), real_audio (MOV + audio) | done: 3 hits, 1 rally, 71.2 / 64.1 / 65.8 km/h (Swift) |
| Timing | real_vfr (87 irregular frames), real_drop (13-frame gap), real_duppts (3 duplicate PTS), real_jump (5.03 s jump) | done; F3 / F4 / F5 above |
| Content (synthetic) | black, white, static court, random scene, shake, zoom, flicker, two courts, person in front, far half only, upside down | clear Chinese failure; black / white / random / shake / zoom → "拍的时候手机在晃…" (camera-motion guard); the rest → "没有看到羽毛球…". No camera accepted on a non-court scene. |
| Real baseline | real_reencode (TrackNetV2 Test match1/1_09_06, 133 frames) | done: 2 hits (Swift) / 3 (Python), 1 rally, 65.8 / 65.9 km/h |

Largest Swift peak footprint: 192.7 MB (4k.mp4). Largest Python max RSS: 1419 MB (4k.mp4, server only).
Slowest clip: Swift 5.3 s (seed_valid), Python 17.2 s (two_seconds).

## Cancellation / resume / corruption matrix (Swift app path)

Driver `driver/` = LiveStages + AnalysisPipeline + the app's FileCheckpointStore (same fingerprint), cancelled with a
real `Task.cancel()` from another task. Clip: `corpus/real_reencode.mp4`. Reference signature 4153712aaa88cb07.

| Phase | Cases | Result |
|---|---|---|
| Reference ×2 | 1 | DETERMINISTIC |
| Cancel in each of 9 stages at 3 offsets | 27 | 27 EQUAL; cancel latency in detect 0.00-0.06 s |
| Cancel after the 1st / 2nd detect_partial save | 2 | 2 EQUAL (resume offered at frame 32 / 64) |
| Double interruption (partial → partial → players) | 1 | EQUAL |
| Mutations: truncate, empty, 4 bit flips, wrong fingerprint, wrong type per file; valid-JSON edits; players.bin count; directory in place | 57 | 57 EQUAL (damaged value → cache miss → recompute) |

## What could not be verified here

Real iPhone behaviour: ANE routing and speed, hardware HEVC / HDR decode, thermal pauses, jetsam limits, background
suspension. Real-gym false court acceptance (synthetic images only). Long-match stability is Task 11 (`tools/endurance/REPORT.md`).

## Rerun

    cd '/Users/yangcong/Downloads/华北五省'
    ./tools/robustness/run_all.sh          # builds, regenerates the corpus, sweeps both engines, both matrices, merges

Every heavy step goes through `/tmp/heavy.sh`. Each repro folder `repro/<id>/README.md` has its own 3-line command.
