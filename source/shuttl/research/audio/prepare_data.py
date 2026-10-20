#!/usr/bin/env python
"""Rebuild the public evaluation data for research/audio and research/doubles (not redistributed).

  pip install gdown numpy scipy          # + ffmpeg/ffprobe on PATH
  AUDIO_STUDY_DATA=~/shuttl-audio-data python prepare_data.py

Layout under $AUDIO_STUDY_DATA: kwyoke/ (am_doubles, am_singles, domain_probs), fineb/ (FineBadminton
json + mp4), s2d/ (S2Doubles labels), audio/*.wav (32 kHz mono PCM), pts/*.txt (video packet PTS,
sorted — several broadcasts are VFR), cache/ (impact curves, written by common.curve).

Licenses — check before any reuse:
  * iLearn-Lab/Finebadminton-20K: Apache-2.0.
  * kwyoke/Badminton-hit-detection: no license file. Private evaluation only; do not ship or train
    a released model on it. Google Drive ids below are the ones linked from its README.
  * HuangYuHsien/S2DoublesDataset: labels only; videos are BWF YouTube broadcasts (not downloaded).
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import urllib.request
import zipfile

DATA = os.environ.get("AUDIO_STUDY_DATA", "/home/user/workspace/data")
KWYOKE = {"am_doubles": "14FOLegDDxgJi5WWeBs0Ok8VQvdZYbZJx",
          "am_singles": "1oXeQhJmD5UfBElHVwIsgwlLZ6kFJuZTh",
          "domain_probs": "1bDKClbteaC8kGiWjfCOz5PHagzBNvXhz"}
FINEB = ["0013", "0015", "0018", "0025", "0044", "0045", "0046", "0047"]   # broadcasts with an audio stream
HF = "https://huggingface.co/datasets/iLearn-Lab/Finebadminton-20K/resolve/main"
S2D = "https://github.com/HuangYuHsien/S2DoublesDataset"


def run(*cmd: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=True, capture_output=True, text=True, **kw)


def has_audio(video: str) -> bool:
    out = run("ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
              "-of", "csv=p=0", video).stdout
    return bool(out.strip())


def wav_and_pts(video: str, tag: str) -> None:
    wav, pts = f"{DATA}/audio/{tag}.wav", f"{DATA}/pts/{tag}.txt"
    if not os.path.exists(wav):
        run("ffmpeg", "-v", "error", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "32000", "-c:a", "pcm_s16le", wav)
    if not os.path.exists(pts):
        out = run("ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                  "-of", "csv=p=0", video).stdout
        times = sorted(float(v) for v in out.split() if v.strip() not in ("", "N/A"))
        with open(pts, "w") as f:
            f.write("\n".join(f"{t:.6f}" for t in times) + "\n")


def kwyoke() -> None:
    os.makedirs(f"{DATA}/kwyoke", exist_ok=True)
    for name, drive_id in KWYOKE.items():
        archive = f"{DATA}/kwyoke/{name}.zip"
        if not os.path.exists(archive):
            run(sys.executable, "-m", "gdown", drive_id, "-O", archive)
        if not os.path.isdir(f"{DATA}/kwyoke/{name}"):
            zipfile.ZipFile(archive).extractall(f"{DATA}/kwyoke")
    for video in sorted(glob.glob(f"{DATA}/kwyoke/am_*/match_*/rally_video/*.mp4")):
        parts = video.split("/")
        if has_audio(video):     # china, clementi, china2, yewtee carry audio
            wav_and_pts(video, f"kw_{parts[-4]}_{parts[-3]}_{os.path.splitext(parts[-1])[0]}")


def fineb() -> None:
    os.makedirs(f"{DATA}/fineb", exist_ok=True)
    for vid in FINEB:
        for url, out in ((f"{HF}/finebadminton-20K/{vid}_updated.json", f"{DATA}/fineb/{vid}.json"),
                         (f"{HF}/videos/{vid}.mp4", f"{DATA}/fineb/{vid}.mp4")):
            if not os.path.exists(out):
                urllib.request.urlretrieve(url, out)
        wav_and_pts(f"{DATA}/fineb/{vid}.mp4", f"fineb_{vid}")


def s2doubles() -> None:
    if not os.path.isdir(f"{DATA}/s2d"):
        run("git", "clone", "-q", "--depth", "1", S2D, f"{DATA}/s2d")


if __name__ == "__main__":
    for sub in ("audio", "pts", "cache"):
        os.makedirs(f"{DATA}/{sub}", exist_ok=True)
    kwyoke()
    fineb()
    s2doubles()
    print("ready:", DATA, len(glob.glob(f"{DATA}/audio/*.wav")), "soundtracks")
