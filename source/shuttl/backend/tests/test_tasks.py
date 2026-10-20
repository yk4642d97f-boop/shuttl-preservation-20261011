"""Celery worker: an analysis without rallies must end as 'failed' with a readable reason."""
from __future__ import annotations

import numpy as np
import pytest

from app.services.tracking import tasks
from app.services.tracking.data_types import Track2D, VideoMeta
from app.services.tracking.pipeline_v2 import MatchAnalysis


def _meta(n: int) -> VideoMeta:
    ts = np.arange(n) / 60.0
    return VideoMeta(fps=60.0, n_frames=n, width=1920, height=1080, timestamps=ts)


def _track(n: int, visible: int) -> Track2D:
    vis = np.zeros(n, bool)
    vis[:visible] = True
    return Track2D(t=np.arange(n) / 60.0, xy=np.zeros((n, 2)), conf=vis.astype(float),
                   visible=vis, interpolated=np.zeros(n, bool))


def test_unusable_reason_matches_app_thresholds():
    assert tasks.unusable_reason(MatchAnalysis(meta=_meta(600))) == tasks.NO_SHUTTLE_REASON
    # 30 frames or 1 % of the clip, whichever is larger (app: AnalysisOutcomePolicy.default).
    assert tasks.unusable_reason(MatchAnalysis(meta=_meta(600), track=_track(600, 29))) == tasks.NO_SHUTTLE_REASON
    assert tasks.unusable_reason(MatchAnalysis(meta=_meta(600), track=_track(600, 30))) == tasks.NO_RALLIES_REASON
    assert tasks.unusable_reason(MatchAnalysis(meta=_meta(6000), track=_track(6000, 59))) == tasks.NO_SHUTTLE_REASON
    assert tasks.unusable_reason(MatchAnalysis(meta=_meta(6000), track=_track(6000, 60))) == tasks.NO_RALLIES_REASON
    assert tasks.unusable_reason(MatchAnalysis(meta=_meta(600), rallies=[object()])) is None


@pytest.fixture
def worker(monkeypatch, tmp_path):
    video = tmp_path / "v.mov"
    video.write_bytes(b"x")
    monkeypatch.setattr(tasks, "settings", type("S", (), {"use_local_storage": True})())
    monkeypatch.setattr(tasks.local_storage, "path_for_key", lambda key: video)


def test_zero_rallies_is_a_deterministic_failure(monkeypatch, worker):
    result = MatchAnalysis(meta=_meta(600), track=_track(600, 200))
    monkeypatch.setattr(tasks, "analyze_video", lambda *a, **kw: result)
    with pytest.raises(tasks.AnalysisUnusable, match=tasks.NO_RALLIES_REASON):
        tasks.compute_analysis("videos/u/v.mov", None, lambda *a: None)


def test_no_shuttle_reason(monkeypatch, worker):
    monkeypatch.setattr(tasks, "analyze_video", lambda *a, **kw: MatchAnalysis(meta=_meta(600)))
    with pytest.raises(tasks.AnalysisUnusable, match=tasks.NO_SHUTTLE_REASON):
        tasks.compute_analysis("videos/u/v.mov", None, lambda *a: None)


def test_old_queue_message_cannot_write_unfenced_results():
    result = tasks.analyze_match.apply(args=("old-match", "videos/u/v.mov"))
    assert result.state == "FAILURE" and "旧版分析任务" in str(result.result)


def test_experimental_hitnet_flags_come_from_the_environment(monkeypatch):
    for name in ("SHUTTL_AUDIO_FUSION", "SHUTTL_HITNET_DOUBLES", "SHUTTL_DOUBLES_GAP_S"):
        monkeypatch.delenv(name, raising=False)
    off = tasks._options({"doubles": True})
    assert (off.audio_fusion, off.hitnet_doubles, off.doubles_gap_s, off.doubles) == (False, False, None, True)
    monkeypatch.setenv("SHUTTL_AUDIO_FUSION", "1")
    monkeypatch.setenv("SHUTTL_HITNET_DOUBLES", "true")
    monkeypatch.setenv("SHUTTL_DOUBLES_GAP_S", "0.2")
    on = tasks._options(None)
    assert (on.audio_fusion, on.hitnet_doubles, on.doubles_gap_s) == (True, True, 0.2)
