"""Convert a public four-player annotation sample without inventing missing labels.

This is an ingestion/audit adapter, not a complete hit-training dataset. Raw status
codes have no assumed semantics, missing shuttle coordinates are unlabelled, and
player IDs are scoped to this clip. No files are uploaded or redistributed.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def convert(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        rows = list(reader)
    required = {"frame", "shuttle_x", "shuttle_y", "status"}
    required |= {f"p{p}{axis}_output{corner}" for p in range(1, 5) for axis in "xy" for corner in range(4)}
    if not rows or not required <= set(columns or []):
        raise ValueError("Missing four-player polygon annotation columns or empty CSV")
    frame_values = np.array([float(r["frame"]) for r in rows])
    if not np.isfinite(frame_values).all() or not np.array_equal(frame_values, frame_values.astype(np.int64)):
        raise ValueError("Frame IDs must be finite integers")
    frames = frame_values.astype(np.int64)
    if len(set(frames)) != len(frames) or (frames < 0).any():
        raise ValueError("Duplicate or negative frame IDs")
    boxes = np.full((len(rows), 4, 4), np.nan, np.float32)
    valid = np.zeros((len(rows), 4), bool)
    for i, row in enumerate(rows):
        for p in range(1, 5):
            polygon = np.array([[float(row[f"p{p}x_output{c}"]), float(row[f"p{p}y_output{c}"])]
                                for c in range(4)], np.float32)
            if not np.isfinite(polygon).all() or (polygon < 0).any():
                continue
            lo, hi = polygon.min(0), polygon.max(0)
            if (hi > lo).all():
                boxes[i, p - 1] = [*lo, *hi]
                valid[i, p - 1] = True
    shuttle = np.array([[float(r["shuttle_x"]), float(r["shuttle_y"])] for r in rows], np.float32)
    labelled = np.isfinite(shuttle).all(1) & (shuttle >= 0).all(1)
    shuttle[~labelled] = np.nan
    status = np.array([r["status"] for r in rows], dtype="U32")
    metadata = {
        "source_file": source.name, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "coordinate_units": "source video pixels; width/height not provided by CSV",
        "fps": None, "fps_note": "README says 30 fps; verify actual paired video before training",
        "track_id_scope": "1..4 within this clip; cross-clip identities and teams not verified",
        "shuttle_missing_semantics": "unlabelled, not an invisible/background negative",
        "status_semantics": "unverified raw source codes; do not convert to hit/non-hit labels",
        "missing_labels": ["complete_hit_frames", "hitter_player_id", "stroke_type", "court_calibration"],
        "license": "not verified; research sample only, excluded from distributable cloud bundle",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(destination, frame=frames, player_ids=np.arange(1, 5),
                        player_box_xyxy=boxes, player_box_labelled=valid,
                        shuttle_xy=shuttle, shuttle_labelled=labelled, status_raw=status,
                        metadata_json=np.array(json.dumps(metadata)))
    report = {**metadata, "frames": len(frames), "frame_min": int(frames.min()), "frame_max": int(frames.max()),
              "four_players_labelled_frames": int(valid.all(1).sum()),
              "player_boxes": int(valid.sum()), "labelled_shuttle_frames": int(labelled.sum()),
              "unlabelled_shuttle_frames": int((~labelled).sum()), "status_counts": dict(Counter(status.tolist())),
              "output_sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}
    destination.with_suffix(".audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    with np.load(destination, allow_pickle=False) as check:
        assert np.array_equal(check["frame"], frames)
        assert np.isnan(check["shuttle_xy"][~check["shuttle_labelled"]]).all()
        assert check["player_box_xyxy"].shape == (len(rows), 4, 4)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(convert(args.source, args.destination), indent=2, ensure_ascii=False))
