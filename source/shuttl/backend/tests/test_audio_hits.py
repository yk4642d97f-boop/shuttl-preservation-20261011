"""Impact onsets, lag estimation and container decoding on synthetic soundtracks."""
import shutil
import subprocess
import wave

import numpy as np
import pytest

from app.services.tracking import audio_hits

SR = audio_hits.SR


def soundtrack(times, dur=4.0, amp=0.5, seed=0, hum=True):
    """Quiet noise, a 300 Hz hum (voices/rumble live low) and short broadband cracks."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 0.002, int(dur * SR)).astype(np.float32)
    if hum:
        x += (0.05 * np.sin(2 * np.pi * 300 * np.arange(len(x)) / SR)).astype(np.float32)
    n = int(0.004 * SR)
    for c in times:
        i = int(round(c * SR))
        burst = rng.normal(0, 1, n) * np.exp(-np.arange(n) / (0.0008 * SR))
        burst = np.diff(np.concatenate([[0.0], burst]))          # tilt towards high frequencies
        x[i:i + n] += (amp * burst[:len(x) - i]).astype(np.float32)
    return x


def test_cracks_are_found_at_their_time():
    times = [0.5, 1.23, 2.0, 2.71, 3.4]
    curve = audio_hits.impact_curve_from_samples(soundtrack(times))
    t, z = audio_hits.onsets(curve, z_min=6)
    assert len(t) == len(times)
    assert np.max(np.abs(t - times)) < 0.01
    assert curve.diagnostics["band_hz"] == [6000.0, 16000.0]


def test_low_frequency_bursts_are_not_impacts():
    x = np.zeros(int(3 * SR), np.float32)
    t = np.arange(len(x)) / SR
    for c in (0.6, 1.4, 2.2):                       # loud 200 Hz thumps (footsteps, voice)
        m = (t >= c) & (t < c + 0.08)
        x[m] += 0.8 * np.sin(2 * np.pi * 200 * t[m])
    x += np.random.default_rng(1).normal(0, 0.002, len(x)).astype(np.float32)
    curve = audio_hits.impact_curve_from_samples(x)
    assert len(audio_hits.onsets(curve, z_min=6)[0]) == 0


def test_chunking_does_not_change_the_curve(monkeypatch):
    x = soundtrack([0.7, 1.9, 3.1])
    whole = audio_hits.impact_curve_from_samples(x)
    monkeypatch.setattr(audio_hits, "CHUNK_S", 0.37)
    pieces = audio_hits.impact_curve_from_samples(x)
    assert len(whole.z) == len(pieces.z)
    np.testing.assert_allclose(whole.z, pieces.z, atol=1e-3)


def test_stream_start_moves_the_clock():
    curve = audio_hits.impact_curve_from_samples(soundtrack([1.0]), start_s=0.25)
    t, _ = audio_hits.onsets(curve, 6)
    assert abs(t[0] - 1.25) < 0.01


def test_frame_evidence_follows_the_lag():
    curve = audio_hits.impact_curve_from_samples(soundtrack([1.0, 2.0]))
    frame_t = np.arange(0, 4, 1 / 30)
    evidence = audio_hits.frame_evidence(curve, frame_t, lag_s=0.1, tol_s=1 / 30)
    assert abs(int(np.argmax(evidence[:45])) - 27) <= 1      # audio 1.0 s ↔ video 0.9 s
    assert evidence[10] < 3


def test_lag_from_jittered_anchors_and_chance_level():
    rng = np.random.default_rng(3)
    hits = np.sort(rng.uniform(0, 600, 400))
    lag = 0.098
    onsets = np.sort(np.concatenate([hits + lag + rng.normal(0, 0.003, len(hits)),
                                     rng.uniform(0, 600, 2000)]))            # + clutter
    keep = hits[rng.random(len(hits)) > 0.1]
    # HitNet-like contact offsets (frames at 30 fps) plus 10 % spurious anchors
    jitter = rng.choice([0, 1, -1, 2, -2], len(keep), p=[.47, .32, .1, .08, .03]) / 30
    anchors = np.concatenate([keep + jitter, rng.uniform(0, 600, 40)])
    est = audio_hits.estimate_lag(onsets, anchors)
    assert abs(est.lag_s - lag) <= 0.02
    assert est.excess > 0.14 and est.anchors == len(anchors)
    unrelated = audio_hits.estimate_lag(np.sort(rng.uniform(0, 600, 2400)), anchors)
    assert unrelated.excess < 0.1


def test_loud_onsets_decide_between_two_lag_peaks():
    rng = np.random.default_rng(5)
    hits = np.sort(rng.uniform(0, 60, 25))                 # a short recording: few anchors
    loud, quiet = hits + 0.13, hits + 0.21                 # contacts vs. an echo/neighbour court
    onsets = np.concatenate([loud[:-3], quiet])           # the quiet peak even has more support
    z = np.concatenate([np.full(len(loud) - 3, 15.0), np.full(len(quiet), 4.0)])
    order = np.argsort(onsets)
    assert abs(audio_hits.estimate_lag(onsets[order], hits).lag_s - 0.21) < 0.005
    assert abs(audio_hits.estimate_lag(onsets[order], hits, z[order]).lag_s - 0.13) < 0.005


def test_lag_estimate_without_inputs():
    est = audio_hits.estimate_lag(np.zeros(0), np.array([1.0, 2.0]))
    assert est.lag_s == 0.0 and est.excess == 0.0 and est.anchors == 2


def _write_wav(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                                  reason="ffmpeg/ffprobe not installed")


@needs_ffmpeg
def test_streams_audio_from_a_video_container(tmp_path):
    wav, video = tmp_path / "a.wav", tmp_path / "v.mp4"
    _write_wav(wav, soundtrack([0.6, 1.5], dur=2.0))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=2",
                    "-i", str(wav), "-shortest", "-c:v", "mpeg4", "-c:a", "aac", "-b:a", "192k", str(video)],
                   check=True)
    curve = audio_hits.impact_curve(str(video))
    assert curve is not None
    t, _ = audio_hits.onsets(curve, 6)
    for c in (0.6, 1.5):     # AAC priming is absorbed by the stream start / lag estimate
        assert np.min(np.abs(t - c)) < 0.05


@needs_ffmpeg
def test_video_without_audio_is_none(tmp_path):
    video = tmp_path / "silent.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=1",
                    "-c:v", "mpeg4", str(video)], check=True)
    assert audio_hits.impact_curve(str(video)) is None
