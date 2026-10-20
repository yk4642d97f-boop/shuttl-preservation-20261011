"""Evaluation data loaders for the audio impact study (public datasets only).

kwyoke/Badminton-hit-detection: amateur rally clips (30 fps) with per-frame hit labels
  (player_hit 1=near, 2=far). Audio present for am_doubles/{match_china,match_clementi}
  and am_singles/{match_china2,match_yewtee}.
iLearn-Lab/Finebadminton-20K (Apache-2.0): broadcast singles; each hit's start_frame is
  the contact frame (end_frame of hit i == start_frame of hit i+1), with hit types.
Hit times are taken from each video's own packet PTS (several broadcasts are VFR).
"""
from __future__ import annotations
import csv, glob, json, os, subprocess, wave
from dataclasses import dataclass, field
import numpy as np

DATA = os.environ.get("AUDIO_STUDY_DATA", "/home/user/workspace/data")


@dataclass
class Clip:
    name: str
    group: str            # venue / match used for grouped splits
    kind: str             # 'amateur' | 'broadcast'
    wav: str
    pts: np.ndarray       # video frame presentation times (s)
    audio_start: float    # audio stream start_time relative to video t=0 (s)
    hits_t: np.ndarray    # labeled contact times (s, video clock)
    hits_type: list[str] = field(default_factory=list)
    hits_side: list[str] = field(default_factory=list)
    windows: list[tuple[float, float]] = field(default_factory=list)  # evaluated spans (s)
    fps: float = 30.0


def read_wav(path):
    with wave.open(path) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0
    return x, sr


def _audio_start(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                          "stream=start_time", "-of", "csv=p=0", video],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def kwyoke_clips():
    clips = []
    for video in sorted(glob.glob(f"{DATA}/kwyoke/am_*/match_*/rally_video/*.mp4")):
        parts = video.split("/")
        kind, match, base = parts[-4], parts[-3], os.path.splitext(parts[-1])[0]
        tag = f"kw_{kind}_{match}_{base}"
        wav = f"{DATA}/audio/{tag}.wav"
        if not os.path.exists(wav):
            continue
        pts = np.loadtxt(f"{DATA}/pts/{tag}.txt", ndmin=1)
        rows = list(csv.DictReader(open(f"{DATA}/kwyoke/{kind}/{match}/player_hit/{base}.mp4_player_hit.csv")))
        frames = [int(r["frame"]) for r in rows if r["player_hit"] != "0"]
        sides = ["near" if r["player_hit"] == "1" else "far" for r in rows if r["player_hit"] != "0"]
        frames = [f for f in frames if f < len(pts)]
        clips.append(Clip(tag, f"kw_{match.replace('china2', 'china')}", "amateur", wav, pts,
                          _audio_start(video), pts[frames], ["?"] * len(frames), sides[:len(frames)],
                          [(0.0, float(pts[-1]))], 30.0))
    return clips


def fineb_clips():
    clips = []
    for ann in sorted(glob.glob(f"{DATA}/fineb/00*.json")):
        vid = os.path.basename(ann)[:4]
        wav = f"{DATA}/audio/fineb_{vid}.wav"
        if not os.path.exists(wav):
            continue
        pts = np.loadtxt(f"{DATA}/pts/fineb_{vid}.txt", ndmin=1)
        rallies = json.load(open(ann))
        t, types, sides, windows = [], [], [], []
        fps = float(rallies[0].get("fps", 25.0)) if rallies else 25.0
        for r in rallies:
            hs = r.get("hitting") or []
            if not hs:
                continue
            for h in hs:
                f = int(h["start_frame"])
                if f >= len(pts):
                    continue
                fa = h.get("Foundational Actions Level", {})
                sub = fa.get("subtype") or []
                typ = fa.get("hit type", "?")
                if typ == "serve" and sub:
                    typ = sub[0]
                t.append(pts[f]); types.append(typ); sides.append(fa.get("hitter", "?"))
            a = int(r.get("start_frame", hs[0]["start_frame"]))
            b = int(r.get("end_frame", hs[-1]["end_frame"]))
            a, b = max(0, a), min(len(pts) - 1, b)
            windows.append((float(pts[a]) - 0.5, float(pts[b]) + 0.5))
        video = f"{DATA}/fineb/{vid}.mp4"
        start = _audio_start(video) if os.path.exists(video) else 0.0
        clips.append(Clip(f"fineb_{vid}", f"fineb_{vid}", "broadcast", wav, pts, start,
                          np.asarray(t), types, sides, windows, fps))
    return clips


def all_clips():
    return kwyoke_clips() + fineb_clips()
