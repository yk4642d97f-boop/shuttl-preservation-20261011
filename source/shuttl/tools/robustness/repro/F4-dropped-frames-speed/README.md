# F4 · Dropped frames (one 13-frame gap) → Python and Swift disagree on speed (PY/SWIFT DIVERGENCE)

Clips: real_drop.mov (one gap of 13 frame-times) and its source real_reencode.mp4 (same footage, no gap).

    /tmp/luna10/driver/release/RobustnessDriver analyze tools/robustness/repro/F4-dropped-frames-speed/real_drop.mov
    /tmp/luna10/driver/release/RobustnessDriver analyze tools/robustness/repro/F4-dropped-frames-speed/real_reencode.mp4

16:38 sweep: Swift 1 hit, 1 rally, 29.9 km/h vs no-gap 65.8 km/h; Python 2 hits, 7.9 km/h. Python re-times frames
to i/fps (video_io.probe) so the gap disappears in time; Swift keeps the real clock (correct). The max speed drops
because the fastest segment spans the gap. Not a crash; the app reports done with a lower speed.
Real-phone likelihood: LOW (iPhone camera drops are rare and short). Severity: accuracy, not safety. Owner: C.
