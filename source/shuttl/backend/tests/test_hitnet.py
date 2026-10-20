"""Input semantics and unsafe-input handling, independent of trained weights."""
import numpy as np
import pytest
import torch
from app.services.tracking import hitnet
from app.services.tracking.data_types import PlayerObservation, Track2D, VideoMeta


def sample(n=12):
    t = np.arange(n, dtype=float) / 30
    return (Track2D(t, np.full((n, 2), [80., 60.]), np.ones(n),
                    np.ones(n, bool), np.zeros(n, bool)),
            VideoMeta(30., 320, 180, n, t.copy()))


def observation(frame=0, side='far', tid=1, box=None, foot=None):
    return PlayerObservation(frame, tid, np.array(box if box is not None else [10,20,30,60.]),
                             .9, side, np.array(foot) if foot is not None else None)


def test_semantic_order_and_independent_foot():
    track, meta = sample()
    players = [observation(side='near', box=[100,100,180,160], foot=[-4,1]),
               observation(side='far', box=[float('nan')]*4, foot=[4,-1])]
    raw = hitnet.raw_matrix(track, meta, players)
    assert np.isnan(raw[0,4:8]).all()
    np.testing.assert_array_equal(raw[0,12:16], [4,-1,-4,1])
    np.testing.assert_allclose(raw[0,8:12], [140/320,130/180,80/320,60/180])
    assert np.isnan(raw[1,4:]).all()


def test_hidden_coordinates_are_not_promoted_to_detections():
    track, meta = sample()
    track.visible[0] = False
    track.interpolated[0] = True
    raw = hitnet.raw_matrix(track, meta, players=[])
    assert np.isnan(raw[0,:3]).all() and raw[0,3] == 1


def fake_model():
    model = object.__new__(hitnet.HitNet)
    model.decoder = {'thr': .4, 'gap_s': .3, 'lam': 0.}
    calls = []
    def logits(raw, fps):
        calls.append(len(raw))
        out = np.full((len(raw),2), -10.,np.float32)
        out[len(raw)//2] = [10.,10.]
        return out
    model.logits = logits
    return model, calls


def test_gap_splits_context_and_keeps_real_clock():
    track, meta = sample()
    track.t[6:] += 2
    meta.timestamps = track.t.copy()
    model, calls = fake_model()
    events = model.detect(track, meta, [observation(frame=3,tid=7)])
    assert calls == [6,6]
    assert [h.frame for h in events] == [3,9]
    assert [h.t for h in events] == [track.t[3],track.t[9]]
    assert events[0].player_track_id == 7 and events[0].hitter == 'far'


def test_doubles_and_simultaneous_players_rejected():
    track, meta = sample()
    model,_ = fake_model()
    for players, double in [([],True),([observation(tid=3),observation(tid=1)],False)]:
        with pytest.raises(ValueError, match='two players'):
            model.detect(track,meta,players,doubles=double)
    index, multiple = hitnet.player_index([observation(tid=3),observation(tid=1)])
    assert multiple and index[(0,'far')].track_id == 1
    assert not hitnet.player_index([observation(tid=1),observation(frame=1,tid=3)])[1]


def test_empty_missing_and_misaligned():
    model,calls = fake_model()
    track,meta = sample(0)
    assert model.detect(track,meta,[]) == []
    track,meta = sample()
    track.visible[:] = False
    assert model.detect(track,meta,[]) == [] and not calls
    track.t += .01
    with pytest.raises(ValueError,match='timestamps differ'):
        model.detect(track,meta,[])


def test_short_nonfinite_output_rejected():
    model = object.__new__(hitnet.HitNet)
    model.device = torch.device('cpu')
    model.net = lambda x: torch.full((1,len(x[0]),2),float('nan'))
    with pytest.raises(ValueError,match='Non-finite'):
        model.logits(np.zeros((12,16),np.float32),30.)


# ── experimental doubles pairing mode and audio fusion ──────────────────────────────────

def four_players(n, frames_far=None):
    """Partners far 2/4 (left/right), near 1/3; `frames_far` limits far observations."""
    out = []
    for f in range(n):
        if frames_far is None or f in frames_far:
            out += [observation(frame=f, side='far', tid=2, box=[10, 10, 30, 50]),
                    observation(frame=f, side='far', tid=4, box=[200, 10, 220, 50])]
        out += [observation(frame=f, side='near', tid=1, box=[10, 120, 40, 170]),
                observation(frame=f, side='near', tid=3, box=[250, 120, 280, 170])]
    return out


def pairing_model(peaks):
    """Fake HitTCN whose hit logit fires only when the named far partner is in the pairing."""
    model = object.__new__(hitnet.HitNet)
    model.decoder = {'thr': .4, 'gap_s': .3, 'lam': 0.}
    calls = []
    def logits(raw, fps):
        calls.append(len(raw))
        out = np.full((len(raw), 2), -10., np.float32)
        for frame, far_cx in peaks.items():
            if abs(raw[frame, 4] - far_cx) < 1e-6:
                out[frame] = [10., 10.]
        return out
    model.logits = logits
    return model, calls


def test_doubles_needs_the_explicit_experimental_mode():
    track, meta = sample(20)
    model, _ = pairing_model({})
    with pytest.raises(ValueError, match='two players'):
        model.detect(track, meta, four_players(20))
    with pytest.raises(ValueError, match='two players'):
        model.detect(track, meta, four_players(20), doubles=True)
    assert model.detect(track, meta, four_players(20), experimental_doubles=True) == []


def test_pairings_keep_the_per_frame_maximum_and_leave_partners_to_geometry():
    track, meta = sample(40)
    model, calls = pairing_model({10: 20 / 320, 25: 210 / 320})   # far id 2, then far id 4
    diag = {}
    hits = model.detect(track, meta, four_players(40), experimental_doubles=True, diagnostics=diag)
    assert [h.frame for h in hits] == [10, 25] and {h.hitter for h in hits} == {'far'}
    assert [h.player_track_id for h in hits] == [None, None]
    assert len(calls) == 4
    assert diag['doubles']['pairings'] == [[2, 1], [2, 3], [4, 1], [4, 3]]
    assert diag['doubles']['hitter_left_to_geometry'] == 2
    assert diag['doubles']['gap_s'] == hitnet.DOUBLES_GAP_S


def test_partner_is_named_when_only_one_is_observed():
    track, meta = sample(40)
    players = [o for o in four_players(40) if not (o.frame == 10 and o.track_id == 4)]
    model, _ = pairing_model({10: 20 / 320})
    hits = model.detect(track, meta, players, experimental_doubles=True)
    assert [(h.frame, h.player_track_id) for h in hits] == [(10, 2)]


def test_pairing_mode_gap_default_and_override():
    track, meta = sample(40)
    model, _ = pairing_model({10: 20 / 320, 18: 210 / 320})        # 8 frames = 0.267 s apart
    assert [h.frame for h in model.detect(track, meta, four_players(40), experimental_doubles=True)] == [10, 18]
    assert len(model.detect(track, meta, four_players(40), experimental_doubles=True, gap_s=.3)) == 1


def test_partner_slots_ignore_rare_track_ids():
    players = four_players(10) + [observation(frame=3, side='far', tid=9)]
    assert hitnet.partner_slots(players) == {'far': [2, 4], 'near': [1, 3]}


def test_audio_curve_threads_through_detect():
    from app.services.tracking import audio_hits, hit_fusion
    track, meta = sample(90)
    model = object.__new__(hitnet.HitNet)
    model.decoder = {'thr': .4, 'gap_s': .3, 'lam': 0.}
    def logits(raw, fps):
        out = np.full((len(raw), 2), -10., np.float32)
        out[30] = [np.log(.3 / .7), -10.]        # quiet contact, below threshold alone
        out[60] = [10., -10.]                    # confident anchor
        return out
    model.logits = logits
    z = np.zeros(int(4 / .002), np.float32)
    curve = audio_hits.ImpactCurve(t0=0., dt=.002, z=z)
    for f in (30, 60):
        curve.z[curve.index([track.t[f]])[0]] = 15.
    diag = {}
    params = hit_fusion.FusionParams(min_anchors=1, min_excess=0.)
    hits = model.detect(track, meta, [], audio_curve=curve, fusion=params, diagnostics=diag)
    assert [h.frame for h in hits] == [30, 60] and {h.hitter for h in hits} == {'near'}
    assert diag['audio']['used'] and diag['audio']['hits_changed_by_audio'] == 1
    assert [h.frame for h in model.detect(track, meta, [])] == [60]


def test_singles_default_is_the_v2_decoder_exactly():
    """Refactor guard: curves()+decode() must equal the original per-segment v2 loop."""
    from app.services.tracking import hitnet_core as core
    rng = np.random.default_rng(11)
    track, meta = sample(240)
    players = [observation(frame=f, side=s, tid=1 if s == 'near' else 2)
               for f in range(240) for s in ('near', 'far')]
    model = object.__new__(hitnet.HitNet)
    model.decoder = {'thr': .4, 'gap_s': .3, 'lam': 0.}
    table = rng.normal(-3, 3, (240, 2)).astype(np.float32)
    model.logits = lambda raw, fps: table[:len(raw)]
    expected = []
    probability, top = core.sigmoid(table[:, 0]), core.sigmoid(table[:, 1])
    for row in core.decode_nms(probability, meta.fps, .4, .3):
        expected.append((row, 'far' if top[row] > .5 else 'near', float(probability[row])))
    hits = model.detect(track, meta, players)
    assert [(h.frame, h.hitter, h.confidence) for h in hits] == expected
    assert all(h.player_track_id == (2 if h.hitter == 'far' else 1) for h in hits)
