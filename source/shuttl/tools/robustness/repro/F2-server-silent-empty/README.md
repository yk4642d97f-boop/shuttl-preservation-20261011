# F2 · Server path marks a match with no shuttle / no rallies as "done" (SILENT-EMPTY)
Clip: seed_valid.mp4 (court drawing, no shuttle). Same for 37 other synthetic clips in results.csv.
```sh
cd '/Users/yangcong/Downloads/华北五省/backend'
.venv/bin/python ../tools/robustness/python_one.py ../tools/robustness/repro/F2-server-silent-empty/seed_valid.mp4
# -> "status": "returned", "rallies": 0, stage_failures [], "server_empty_done": true
```
On-device (default, OnDeviceAnalysis.swift:61) this is OK: MatchPipeline.swift:395-402 throws
analysisUnusable("没有看到羽毛球。…") — verified by the driver's app-gate mirror for all 38 clips.
Server mode (DEBUG opt-in via UserDefaults "shuttl.analyzeOnDevice" = false, OnDeviceAnalysis.swift:55-63): backend/app/services/tracking/tasks.py:71-79 writes
status 'done' for any returned analysis, and the app's server path MatchPipeline.swift:482-484 → :519-524
(fetchResults) sets .done without looking at the rallies → an empty "done" match.
Fix (not applied), server side:
```diff
         res = analyze_video(video_path, _options(calibration), progress=...)
+        if res.track is None or not res.rallies:
+            _update_status(match_id, "failed")
+            return {"match_id": match_id, "status": "failed",
+                    "reason": "没有看到羽毛球或没有找到完整回合。请确认整片球场都在画面里，光线充足。"}
         doc = serialize.to_dict(res)
```
and/or app side in fetchResults: throw analysisUnusable when the fetched document has 0 rallies.
