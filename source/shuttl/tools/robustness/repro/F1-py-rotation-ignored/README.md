# F1 · Python/server ignores rotation metadata (PY/SWIFT DIVERGENCE, wrong result on the server path)
Clip: real_rot90.mov = real rally footage (1280x720) with a 90° preferred transform (as a portrait iPhone
recording). Also every corpus/h264_rot*.mov, hevc_rot*.mov, and real_rot180.mov (landscape-right iPhone = 180°).

```sh
cd '/Users/yangcong/Downloads/华北五省/backend'
.venv/bin/python ../tools/robustness/diag_segments.py ../tools/robustness/repro/F1-py-rotation-ignored/real_rot90.mov
# -> default_auto 0.0, meta 90, default_shape (720, 1280) [NOT rotated]; auto_on_shape (1280, 720)
```
Python reports size 1280x720 + rotation_deg 90 and analyses the stored (sideways) pixels; the phone
(VideoIO.swift:70, :189-219) analyses the upright 720x1280 frame. Same clip → Python 1 rally, Swift 0.
Fault: backend/app/services/tracking/video_io.py:15-27 (comment "already auto-rotated by OpenCV" is false:
this OpenCV 4.11 FFMPEG build has CAP_PROP_ORIENTATION_AUTO = 0), also :40, :65 and pipeline.py:115.
Fix (not applied): open every capture through one helper that enables auto-rotation.
```diff
+def _open(path):
+    cap = cv2.VideoCapture(path)
+    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)     # default is 0 in this build
+    return cap
-    cap = cv2.VideoCapture(path)            # probe / iter_frames / sample_frames
+    cap = _open(path)
```
Add a regression test that probes corpus/h264_rot90.mov and asserts (w, h) == (360, 640).
