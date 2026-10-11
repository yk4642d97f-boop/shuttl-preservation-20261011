# Robustness torture test — current handoff (2025-09-28)

## Scope

Only `tools/robustness/` plus `.agent-logs/handoff-robustness.log` were intentionally written. No existing app/package source was edited. **Caveat:** Python imports and the focused pytest run may have refreshed pre-existing `__pycache__`, Numba cache, and `.pytest_cache` artifacts under `backend/`; these were left in place (not deleted/restored), since cleanup would further modify existing files. The corpus generator uses seed 81010, OpenCV `mp4v` for synthetic MP4s, and the bundled AVFoundation generator for short H.264/HEVC MOVs with 0/90/180/270° preferred transforms. Current corpus: **45 clips** — 44 video files plus `audio_only.wav` (46 directory files including `manifest.json`). The manifest inventories filenames, bytes, and missing formats. Most clips are tiny (1–60 frames); they probe edge cases, not sustained match load.

This is a Mac-hosted check, not proof of iPhone ANE, thermal, jetsam, or hardware codec behavior. The exact app-level `MatchPipeline` was source-inspected but not built or invoked (per instruction). Its `analysisUnusable` throw is at `iOS/Sources/Services/MatchPipeline.swift:395-402`.

## Findings ranked by severity

| Severity | Classification | Input / reproduction | Evidence | Fault location / suggested action |
|---|---|---|---|---|
| Conditional integration risk; raw API observation only | SILENT-EMPTY | `repro/py-empty/empty_192x144.mp4`; see `repro/py-empty/README.md` | The Python reference returned no camera/hits/rallies and all recorded stages `ok`, with no user-facing unusable outcome. The sample used `SHUTTL_DETECTOR=motion`; it is not a full default-neural Python run. This does not prove the app marks it done. | `backend/app/services/tracking/pipeline_v2.py:139-141,157-158` returns a raw empty `MatchAnalysis`; `serialize.py:135-145` serializes empty data without an outcome. Any consumer finalizing a match must reject no-shuttle/no-rally results. Swift has an outcome gate in `MatchPipeline.swift:395-402`; app-level integration remains unverified. No fix applied. | |
| None observed in one small Swift sample | OK | `corpus/seed_valid.mp4` | The direct Swift pipeline returned the clear Chinese no-shuttle reason; 0 hits/rallies, no camera; peak sampled footprint 73.8 MB. This is AnalysisOutcome, not an app integration test. | No defect established. |
| Resolved known lead | OK (fixed in inspected revision) | `corpus/192x144.mp4`; linker test command in `repro/README.md` | `backend/app/services/tracking/linker.py:504-535` checks `if len(sk)` before indexing. `pytest tests/test_linker.py::test_weak_only_candidates` passed 3/3 for 192×144, 64×48, 1920×1080. | No patch needed against current source. |
| Unverified checkpoint lead (not yet a finding) | NOT_RUN | Driver matrix in `driver/` | A first fake-stage matrix passed injected `CancellationError`/resume signatures and verified truncated/bit-flipped/wrong-fingerprint JSON cache misses. It did **not** exercise real `Task.cancel()` or prove resume recovery after corruption. The newer randomized observer cancellation and valid-JSON mutation test have not been rebuilt/run. | `AnalysisStages.swift:134-142` checks decode + fingerprint but has no JSON value checksum. The drafted semantic mutation experiment may test whether valid-JSON corruption is accepted; do not treat as confirmed until it runs. Suggested hardening if reproduced: bind a checksum to the encoded value and treat mismatch as cache miss. |
| No conclusion | NOT_RUN | Remaining corpus clips | No complete Python+Swift sweep; `results.csv` labels untouched cells NOT_RUN. | Run `./tools/robustness/run_all.sh` when host load is safe. |

Suggested caller-side guard (illustrative; adapt the exception type and Chinese wording to the actual caller; not applied):

```diff
 analysis = pipeline_v2.analyze_video(path, opts)
+if analysis.track is None or not analysis.rallies:
+    raise AnalysisUnusable("没有看到羽毛球或没有找到完整回合，请检查视频。")
 persist_as_done(analysis)
```

## What ran

- Python 192×144, two frames: 12.437 s wall, 556.4 MB max RSS, MotionDetector. Detect/link/calibrate/players/hits/rallies/score all recorded `ok`; no camera, hits, rallies or speed; calibration reason `no_hypotheses`.
- Swift 320×180, 12 frames: 44.586 s wall (detector 38.573 s), 73.8 MB peak sampled footprint. No camera/hits/rallies; AnalysisOutcome said “没有看到羽毛球。请确认整片球场都在画面里，光线充足。”
- Linker regression test: 3 passed.
- Custom Swift driver and AVFoundation generator built with private scratch locations. One initial driver build raced concurrent source edits; retry succeeded. The later randomized cancellation / recovery additions have not been compiled.

## Corpus coverage and limitations

Current generated types: 0-byte and truncated MP4; 1/5/15/60/7/8/9-frame clips; 192×144, 640×360, 1280×720, 1920×1080, 3840×2160, 1080×1920, 1918×1078; nominal 24/25/30/50/60/120/240 fps; black/white/static court/random/shake/zoom/flicker/two-court/walking-person/far-half/upside-down; H.264 and HEVC MOVs with rotation metadata; audio-only WAV (no video track).

Not generated or verified: true HEVC 10-bit HDR, VFR, duplicate PTS, dropped-frame timestamps, timestamp jump, and MOV containing audio. The Swift MOV writer consumes 8-bit BGRA, so it is not an HDR sample. No real iPhone, ANE routing, iOS thermal pause, jetsam limit, or hardware HEVC/HDR decode was tested. Synthetic images cannot measure false court acceptance on real gyms. The short corpus cannot establish long-match memory/thermal stability.

## Rerun

```sh
cd '/Users/yangcong/Downloads/华北五省'
./tools/robustness/run_all.sh
```

The runner serializes clip jobs, scales timeouts by duration, caps Swift builds at four jobs, uses `/tmp/luna10` scratch directories, and does not use ffmpeg. Wait until shared host load is safe before launching the complete sweep.
