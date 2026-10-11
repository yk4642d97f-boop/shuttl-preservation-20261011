# track-len-mismatch — CRASH (SIGTRAP "Index out of range") on resume from a corrupted track.json

Severity: CRASH ON PHONE, repeating. The app calls `resumePending()` at launch and on every return to
foreground (iOS/Sources/App/ContentView.swift:38,41), so one bad track.json checkpoint traps the app every
time it opens until the checkpoint is removed.

`store/` = a real checkpoint store from `corpus/real_reencode.mp4` (RobustnessDriver, 2026-09-28 20:36 build).
Only change: in track.json, `value.xy` has 132 entries while t / conf / visible / interpolated / raw_xy have 133.
Still valid JSON, fingerprint untouched, so FileCheckpointStore accepts it as a cache hit.

Reproduce (from the project root; the driver builds with `cd tools/robustness/driver && swift build -c release --scratch-path /tmp/luna10/driver`):

    rm -rf /tmp/tlm && cp -R tools/robustness/repro/track-len-mismatch/store /tmp/tlm
    /tmp/luna10/driver/release/RobustnessDriver analyze tools/robustness/corpus/real_reencode.mp4 --store /tmp/tlm
    echo $?    # 133 = SIGTRAP; crash log ~/Library/Logs/DiagnosticReports/RobustnessDriver-2026-09-28-204409.ips

Stack: `Hits.preferRaw(_:)` ShuttlHits/Sources/ShuttlHits/Observations.swift:30 (`xy[i] = raw[i]`)
<- `detectHits` Hits.swift:21 <- `PortedStages.hits` <- `LiveStages.detectHits` LiveStages.swift:154.
`preferRaw` checks `raw.count == track.n` (n = t.count) but not `xy.count`.

Root cause: `Track2D.init(from:)` iOS/Packages/ShuttlCore/Sources/ShuttlCore/DataTypes.swift:73-81 accepts
per-frame arrays of different lengths. Suggested fix (NOT applied) — throw, so the store treats it as a cache miss:

```diff
         rawXY = try c.decodeNaNableRows(forKey: .rawXY)?.map(SIMD2.init(row:))
+        let n = t.count
+        guard xy.count == n, conf.count == n, visible.count == n, interpolated.count == n,
+              rawXY.map({ $0.count == n }) ?? true else {
+            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath,
+                debugDescription: "Track2D arrays differ in length (t \(n), xy \(xy.count))"))
+        }
     }
```

Verify after the fix: the same command returns normally and the result signature equals the uninterrupted
reference (`python tools/robustness/matrix_live.py mutate` row `track.json valid_json_len_mismatch` → EQUAL).

## Fix verification (2026-09-29 00:05, driver rebuilt on current sources)
- `store/` (old layout, no sha256): exit 0, signature 4153712aaa88cb07 = reference. Now a miss because of A's value digest.
- `store-v2/` (current layout `{"fingerprint","sha256","value"}` with the digest RE-COMPUTED over the shortened value, so only
  B's length check can reject it): exit 0, track stage recomputed (not resumed), signature 4153712aaa88cb07 = reference.
  → B's Track2D.inconsistency check (DataTypes.swift, 23:41) is confirmed on its own. FIXED.
