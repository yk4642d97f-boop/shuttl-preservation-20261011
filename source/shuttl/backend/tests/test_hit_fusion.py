"""Audio/visual hit fusion rules on synthetic probability and impact curves."""
import numpy as np

from app.services.tracking import audio_hits, hit_fusion, hitnet_core

FPS = 30.0


def impact_curve(spikes, dur=10.0, height=12.0, seed=0):
    rng = np.random.default_rng(seed)
    dt = 0.002
    z = np.abs(rng.normal(0, 1, int(dur / dt))).astype(np.float32)
    curve = audio_hits.ImpactCurve(t0=0.0, dt=dt, z=z)
    for t in spikes:
        curve.z[curve.index([t])[0]] = height
    return curve


def test_decoder_is_identical_to_hitnet_core():
    rng = np.random.default_rng(0)
    for _ in range(50):
        p = (rng.random(300) ** 3).astype(np.float32)
        for thr, gap in ((.4, .3), (.2, .25)):
            assert hit_fusion.decode_nms(p, FPS, thr, gap) == hitnet_core.decode_nms(p, FPS, thr, gap)


def test_fuse_probability_moves_logits_both_ways():
    p = np.array([.3, .3, .9])
    ev = np.array([12.0, 0.0, 0.0])
    out = hit_fusion.fuse_probability(p, ev, beta=2.0, penalty=0.5, z0=3.0, z1=9.0)
    assert out[0] > .7 and out[1] < .3 and .8 < out[2] < .9


def test_audio_rescues_a_quiet_contact_and_drops_a_silent_peak():
    n, lag = 200, 0.1
    t = np.arange(n) / FPS
    p = np.full(n, .01, np.float32)
    p[30], p[90], p[150] = .3, .9, .45          # quiet real contact, clear contact, silent false peak
    curve = impact_curve([t[30] + lag, t[90] + lag])
    gate = hit_fusion.AudioGate(True, "ok", lag_s=lag, excess=.3, match_rate=.9, anchors=100)
    assert hit_fusion.decode_nms(p, FPS, .4, .3) == [90, 150]
    frames, fused, out_gate = hit_fusion.fuse_and_decode(p, t, FPS, curve, thr=.4, gap_s=.3, gate=gate)
    assert frames == [30, 90] and out_gate is gate
    assert fused[150] < .4


def test_gated_off_audio_changes_nothing():
    t = np.arange(100) / FPS
    p = np.zeros(100, np.float32)
    p[40] = .8
    off = hit_fusion.AudioGate(False, "audio_not_informative")
    frames, fused, _ = hit_fusion.fuse_and_decode(p, t, FPS, impact_curve([]), thr=.4, gap_s=.3, gate=off)
    assert frames == [40] and fused is not None and np.array_equal(fused, p)


def test_snap_moves_to_the_strongest_onset_once():
    frame_t = np.arange(100) / FPS
    onset_t = np.array([frame_t[41] + .05, frame_t[43] + .05])
    onset_z = np.array([7.0, 9.0])
    out = hit_fusion.snap_frames([40, 44], frame_t, onset_t, onset_z, lag_s=.05, max_shift_s=2 / FPS,
                                 priority=np.array([.9, .5]))
    assert out.tolist() == [41, 43]          # the stronger onset goes to the higher-priority hit first


def test_gate_needs_anchors_and_an_informative_soundtrack():
    rng = np.random.default_rng(1)
    n = int(120 * FPS)
    t = np.arange(n) / FPS
    hits = np.sort(rng.choice(np.arange(30, n - 30), 80, replace=False))
    hits = hits[np.concatenate([[True], np.diff(hits) > 12])]
    p = np.full(n, .01, np.float32)
    p[hits] = .95
    lag = .08
    good = impact_curve(list(t[hits] + lag) + list(rng.uniform(0, 120, 200)), dur=121.0)
    gate = hit_fusion.assess(good, t, p, FPS, .4, .3)
    assert gate.used and gate.reason == "ok" and abs(gate.lag_s - lag) <= .01
    noisy = impact_curve(list(rng.uniform(0, 120, 300)), dur=121.0, seed=2)
    assert hit_fusion.assess(noisy, t, p, FPS, .4, .3).reason == "audio_not_informative"
    few = p.copy()
    few[hits[10:]] = .01
    assert hit_fusion.assess(good, t, few, FPS, .4, .3).reason == "too_few_anchors"
    assert hit_fusion.assess(None, t, p, FPS, .4, .3).reason == "no_audio"
    assert set(gate.as_dict()) == {"used", "reason", "excess", "match_rate", "anchors", "lag_ms"}
