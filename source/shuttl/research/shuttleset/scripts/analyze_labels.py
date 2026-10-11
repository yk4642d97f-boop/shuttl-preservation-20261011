#!/usr/bin/env python3
"""Summarise ShuttleSet / ShuttleSet22 labels: row counts, class counts, per-match fps implied
by frame_num vs the `time` column (time is given to whole seconds, so fps = least-squares slope).
Writes labels_summary.json next to labels/."""
import csv, glob, json, os, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETS = {
    "ShuttleSet": os.path.join(ROOT, "labels/ShuttleSet/set"),
    "ShuttleSet22": os.path.join(ROOT, "labels/CoachAI-Challenge-IJCAI2023/ShuttleSet22/set"),
}
EN = {"放小球": "net shot", "擋小球": "return net", "殺球": "smash", "點扣": "wrist smash", "挑球": "lob",
      "防守回挑": "defensive return lob", "長球": "clear", "平球": "drive", "小平球": "driven flight",
      "後場抽平球": "back-court drive", "切球": "drop", "過渡切球": "passive drop", "推球": "push",
      "撲球": "rush", "防守回抽": "defensive return drive", "勾球": "cross-court net shot",
      "發短球": "short service", "發長球": "long service"}


def tsec(s):
    p = [float(x) for x in s.split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2]


def fit(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return b, my - b * mx


out = {}
for name, d in SETS.items():
    matches = list(csv.DictReader(open(os.path.join(d, "match.csv"), encoding="utf-8")))
    types, ah, bh = Counter(), Counter(), Counter()
    per = []
    total = 0
    for m in matches:
        folder = os.path.join(d, m["video"])
        files = sorted(glob.glob(os.path.join(folder, "set*.csv")))
        n = 0; info = {"id": m["id"], "video": m["video"], "url": m.get("url", ""), "sets": []}
        for f in files:
            rows = list(csv.DictReader(open(f, encoding="utf-8")))
            xs = [tsec(r["time"]) for r in rows if r["time"] and r["frame_num"]]
            ys = [float(r["frame_num"]) for r in rows if r["time"] and r["frame_num"]]
            b, a = fit(xs, ys) if len(xs) > 2 else (None, None)
            info["sets"].append({"file": os.path.basename(f), "strokes": len(rows),
                                 "fps_fit": round(b, 3) if b else None,
                                 "offset_frames": round(a, 1) if a is not None else None,
                                 "first_frame": ys[0] if ys else None, "last_frame": ys[-1] if ys else None,
                                 "first_time": rows[0]["time"], "last_time": rows[-1]["time"]})
            for r in rows:
                types[r["type"]] += 1
                ah[r.get("aroundhead", "")] += 1
                bh[r.get("backhand", "")] += 1
            n += len(rows)
        info["strokes"] = n
        fpss = [s["fps_fit"] for s in info["sets"] if s["fps_fit"]]
        info["fps_fit_mean"] = round(sum(fpss) / len(fpss), 3) if fpss else None
        total += n
        per.append(info)
    out[name] = {"matches": len(matches), "strokes": total,
                 "types": {k: [EN.get(k, "?"), v] for k, v in types.most_common()},
                 "aroundhead": dict(ah), "backhand": dict(bh), "per_match": per}

json.dump(out, open(os.path.join(ROOT, "labels_summary.json"), "w"), ensure_ascii=False, indent=1)
for name, o in out.items():
    print(f"== {name}: {o['matches']} matches, {o['strokes']} strokes")
    for k, (en, v) in o["types"].items():
        print(f"  {k}\t{en}\t{v}")
    print("  aroundhead", o["aroundhead"], "backhand", o["backhand"])
    fc = Counter(round(p["fps_fit_mean"]) if p["fps_fit_mean"] else None for p in o["per_match"])
    print("  fps (rounded) per match:", dict(fc))
    for p in o["per_match"]:
        print("   ", p["id"], p["fps_fit_mean"], p["strokes"], p["video"][:60],
              [ (s["fps_fit"], s["offset_frames"]) for s in p["sets"]])
