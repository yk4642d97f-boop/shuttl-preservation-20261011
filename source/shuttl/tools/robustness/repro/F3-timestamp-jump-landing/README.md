# F3 · Timestamp jump → landing outside the hall, app still says "分析完成。" (IMPLAUSIBLE, both engines)

Clip: real_jump.mov = real TrackNetV2 rally (Test/match1/1_09_06.mp4) re-encoded with ONE 5.03 s gap in the PTS
(`tools/robustness/gen` RobustnessGen retime ... jump). 133 frames, mean fps 14.1 (should be 30).

    /tmp/luna10/driver/release/RobustnessDriver analyze tools/robustness/repro/F3-timestamp-jump-landing/real_jump.mov
    # -> camera yes, 3 hits, 2 rallies, implausible: "landing (-11.1, -0.3) m outside hall", app_done true
    cd backend && .venv/bin/python ../tools/robustness/python_one.py ../tools/robustness/repro/F3-timestamp-jump-landing/real_jump.mov

Cause: VideoIO keeps real PTS; reconstruct/landing uses per-frame dt, and one huge dt makes the fitted flight extrapolate
11 m outside the court. No plausibility gate on landing position before the rally is scored.
Where: 3-D landing/outcome (ShuttlReconstruct / ShuttlRally landing -> outcome_source '3d'); Python rally.py analogue.
Court frame (backend/app/services/tracking/court_model.py:5-30): origin = court centre under the net, +x along the
length, |x| <= 6.70 m, |y| <= 3.05 m. x = -11.1 m is 4.4 m behind the near baseline — physically impossible for a
landing that is scored. The driver's hall check is |x| <= 10.7, |y| <= 6.05 (Summary.swift:42).
Fix (not applied): treat a landing with |x| > 6.70 + 1 or |y| > 3.05 + 1 m as unknown (outcome uncertain, no winner
from it); and split tracks at PTS gaps > 0.5 s (no interpolation or fitting across a gap).
Real-phone likelihood: LOW — iPhone recordings do not contain PTS jumps; a paused/edited clip could.
