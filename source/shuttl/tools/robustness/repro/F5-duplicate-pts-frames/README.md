# F5 · Duplicate PTS → Swift 130 frames vs Python 133 (EXPECTED divergence, not a bug)

Clip: real_duppts.mp4 (3 samples share a PTS; made by tools/robustness/mp4box.py duppts).

    /tmp/luna10/driver/release/RobustnessDriver analyze tools/robustness/repro/F5-duplicate-pts-frames/real_duppts.mp4

Swift/AVFoundation delivers each PTS once (130 frames, real clock); cv2/FFmpeg decodes all 133 and re-times to i/fps.
Owner (coordinator.log 2026-09-28 16:50) ruled this expected: Apple writers never produce duplicate PTS, and the
Swift behaviour is the correct one for the phone. Results otherwise agree (3 hits, 1 rally, ~64-66 km/h). No action.
