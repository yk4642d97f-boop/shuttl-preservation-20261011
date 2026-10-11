"""Inventory downloaded annotations without mistaking singles for doubles."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent / "data"


def main():
    fine = {"videos": [], "source": "https://huggingface.co/datasets/Moujuruo/Finebadminton-20K"}
    player_counts, hitter_counts = Counter(), Counter()
    total_rallies = total_hits = 0
    for path in sorted((ROOT / "finebadminton_annotations").glob("*.json")):
        rallies = json.loads(path.read_text())
        total_rallies += len(rallies)
        players = set()
        for rally in rallies:
            player_counts[len(rally.get("playerList", []))] += 1
            players.update(p.get("name", "") for p in rally.get("playerList", []))
            for hit in rally.get("hitting", []):
                total_hits += 1
                hitter_counts[str(hit.get("Foundational Actions Level", {}).get("hitter"))] += 1
        fine["videos"].append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                               "rallies": len(rallies), "players": sorted(players)})
    fine.update(files=len(fine["videos"]), rallies=total_rallies, hits=total_hits,
                player_count=dict(player_counts), hitter=dict(hitter_counts),
                suitability="Two-player singles annotations; no verified doubles training labels")
    (ROOT / "finebadminton_inventory.json").write_text(json.dumps(fine, ensure_ascii=False, indent=2))

    matches = defaultdict(lambda: {"players": set(), "sides": set(), "shots": Counter(),
                                   "samples": 0, "shards": set(), "rallies": set()})
    headers = set()
    for row in pq.read_table(ROOT / "bfmd_metadata.parquet").to_pylist():
        payload = json.loads(row["sample_payload"])
        meta = payload["metadata"]
        match = matches[meta["match_name"]]
        match["samples"] += 1
        match["players"].add(meta.get("player"))
        match["sides"].add(meta.get("side"))
        match["shots"][meta.get("shot_type")] += 1
        match["shards"].add(row["shard_name"])
        match["rallies"].add((meta.get("game"), meta.get("rally")))
        headers.add(row["header"])
    result = {"source": "https://huggingface.co/datasets/OpenSportsLab/bfmd-captions",
              "headers": [json.loads(h) for h in sorted(headers)],
              "suitability": "Public captions subset has 12 two-player matches; full BFMD is manually gated",
              "matches": {name: {k: sorted(v) if isinstance(v, set) else v for k, v in m.items()}
                          for name, m in matches.items()}}
    (ROOT / "bfmd_inventory.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({"finebadminton": {k: v for k, v in fine.items() if k != "videos"},
                      "bfmd_matches": len(matches), "bfmd_samples": sum(m["samples"] for m in matches.values())},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
