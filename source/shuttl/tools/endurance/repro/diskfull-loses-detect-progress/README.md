# Disk full during detect → all detect progress is deleted, so the next interruption restarts detect from frame 0 (LOST RESUME, no wrong result)

Found by the v2 45-min matrix, case diskfull-detect-2 (tools/endurance/results/matrix-v2/matrix-45m-extra/diskfull-detect-2.json).
The result is CORRECT (byte-equal to base-45m v2); what is lost is the ability to resume.

What happened (attempt-0.log):
- Resumed from a 21600-frame detect_partial on a 200 MB APFS image with 5.2 MB free.
- Every detect_partial append after 43200 frames failed silently: the file stayed at 11,461,979 bytes (next=43200) while
  detect continued to frame 158400 (DetectPartial.swift:55 "Best effort", no signal).
- At the end of detect, `candidates.json` could NOT be written (save_end candidates bytes=0: FileCheckpointStore.save
  swallows the error), yet AnalysisPipeline.swift:76 `if candidates != nil { partial?.clearDetectPartial() }` deleted the
  detect_partial file anyway. "candidates != nil" means detect RAN, not that its checkpoint was SAVED.
- Then track / camera / camera_motion saves also failed (bytes=0). SIGKILL in players.
- attempt-1 (disk freed): load_end candidates hit=false, detect_partial hit=false next=-1 → detect re-ran from frame 0
  (689 s of detect on this Mac). camera / camera_motion loaded as hits because their small files still fit; the event's "bytes=0" is
  my driver reporting the size of a store directory it could not list, so it does not prove those writes failed.
  candidates.json (27 MB) and the new detect_partial appends are the writes that could not fit. Final result byte-equal.

Phone impact: a nearly full phone (common!) + any interruption after detect = the whole detect (≈ 11 min for 45 min on
this Mac, more on the phone) is repeated, even though 43200 frames of progress existed on disk. Not a crash, not a wrong
result. StorageGuard should keep the phone from getting this full, but it does not guard against the disk filling during
analysis.

Fault: iOS/Packages/ShuttlAnalysis/Sources/ShuttlAnalysis/AnalysisPipeline.swift:75-76 clears detect_partial without checking
that "candidates" was persisted. Suggested fix (not applied), owner A:

```diff
-        // "candidates" is saved (or was restored): the partial progress is obsolete.
-        if candidates != nil { partial?.clearDetectPartial() }
+        // Only drop the partial progress once "candidates" is actually on disk (a full disk makes save a no-op).
+        if candidates != nil, checkpoints.load([[ShuttleCandidate]].self, key: "candidates") != nil {
+            partial?.clearDetectPartial()
+        }
```
(or make CheckpointStore.save return Bool / throw and branch on it; the load re-reads ~27 MB once, cheap). Optional:
surface a "storage full" warning when a checkpoint save fails, so the user learns why resume will be slow.

Reproduce (≈ 40 min, via the queue):
    ENDURANCE_DRIVER=/tmp/luna11/v2/driver/release/EnduranceDriver ENDURANCE_RUNS=/tmp/luna11/v2/runs ENDURANCE_WORK=/tmp/luna11/v2/matrix \
    ENDURANCE_SNAP=/tmp/luna11/v2/snapshots ENDURANCE_OUT=tools/endurance/results/matrix-v2 \
      python3 tools/endurance/matrix.py /tmp/luna11/v2/matrix-45m-extra.json diskfull-detect-2
    grep -E "save_end (detect_partial|candidates)|clear detect_partial|load_end (candidates|detect_partial)" /tmp/luna11/v2/matrix/diskfull-detect-2/attempt-*.log

## Fix verification (2026-09-30 08:16, v4 driver on current packages, after A 07:02)
Same case (diskfull-detect-2): attempt-0 again cannot save candidates (bytes=0), but attempt-1 now shows
`load_end detect_partial hit=true next=43200` and detect takes 323 s (was 689 s from frame 0). Result byte-equal to v3 base-45m. FIXED.
