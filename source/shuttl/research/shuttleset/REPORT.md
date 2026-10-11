# ShuttleSet acquisition report (2026-10-05)

## Labels (`labels/`, CoachAI-Projects commit 45517f7d)
- ShuttleSet has 44 matches and 36,484 strokes; the README says 36,492. There is one CSV per set with 30 columns, including:
  - hit frame `frame_num`
  - stroke type
  - around-head and backhand flags
  - landing point
  - player positions in 1280×720 pixels
- There are 19 stroke classes in the data. The README omits 未知球種 (1,407 strokes), and passive drop is spelled 過度切球.
- `frame_num` counts from the start of the video. Matches 1–20 are 25 fps and matches 21–44 are 30 fps. Per-match details are in `labels_summary.json`.
- ShuttleSet22 has 58 matches and 52,356 strokes. 8 matches overlap ShuttleSet with identical labels. It has **no video URLs**, so its 50 new matches would have to be found on YouTube by title.
- Match 12 has no URL.

## Video download
- From the Seoul server, every direct yt-dlp attempt fails with "Sign in to confirm you're not a bot", whatever client, token or runtime is used.
- What works is an anonymous Cloudflare WARP registration run as a userspace `wireproxy` SOCKS proxy (`/root/work/shuttleset/warp`). It needs no account and no cookies, and it does not change the server's routing.
- Videos are 720p, and their fps matches the label fps.

## Alignment
- I spot-checked 8 labelled hits in match 3 (25 fps) and match 21 (30 fps). The frames are in `frames/`.
- Contact is within about ±1–2 frames, and there is no drift from the first rally to the last.

## Speeds and size
| Leg | Speed | Time / size |
|---|---|---|
| Server download | about 5.3 MB/s | about 70 min for everything |
| Server→Mac | about 0.3–0.47 MB/s with 8 parallel streams | **about 14 h for everything; the bottleneck** |

The total is about 21.8 GB for 43 matches.

## Operating the fetcher
- Manifest: `manifest.csv`. Log: `fetch.log`.
- Resume:
  ```bash
  cd research/shuttleset && nohup python3 scripts/fetch_all.py --streams 8 --retry-failed >> fetch.log 2>&1 &
  ```
- Stop (about 10 min to drain):
  ```bash
  pkill -TERM -f scripts/fetch_all.py
  ```
- The fetcher keeps the server under 15 GB and verifies each file before deleting it on the server.
