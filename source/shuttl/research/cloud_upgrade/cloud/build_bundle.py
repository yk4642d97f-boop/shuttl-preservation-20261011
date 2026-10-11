"""Build an allowlisted, checksummed training archive; never copy a whole project."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        raise SystemExit("Output exists; use a new archive filename.")
    paths = [
        "backend/app/__init__.py", "backend/app/services/__init__.py",
        "backend/app/services/tracking/__init__.py",
        "backend/app/services/tracking/data_types.py",
        "backend/app/services/tracking/video_io.py",
        "backend/app/services/tracking/detector.py",
        "backend/ml/train_detector.py", "backend/ml/export_coreml.py",
        "backend/ml/weights/ckpts/TrackNet_best.pt",
        "backend/ml/weights/wasb_badminton_best.pth.tar",
        "research/hitnet/common.py", "research/hitnet/infer.py", "research/hits/score.py",
        "research/cloud_upgrade/comparison.json", "research/cloud_upgrade/side_audit.json",
        "research/cloud_upgrade/MODEL_CARD.md", "research/cloud_upgrade/MODEL_SURVEY.md",
        "research/cloud_upgrade/CLOUD_PLAN.md",
        "research/cloud_upgrade/cloud/local_smoke.json",
        "research/cloud_upgrade/artifacts/hitnet_single_v2.pt",
        "research/cloud_upgrade/artifacts/hitnet_single_v2.json",
        "research/cloud_upgrade/runs/expanded_serve35_40ep_s20261007/best.pt",
        "research/cloud_upgrade/runs/expanded_serve35_40ep_s20261007/config.json",
        "research/cloud_upgrade/runs/expanded_serve35_40ep_s20261007/trainer_snapshot.py",
    ]
    paths += [str(p.relative_to(ROOT)) for p in HERE.iterdir()
              if p.is_file() and p.suffix in {".py", ".sh", ".txt", ".md"}]
    data = ROOT / "backend/ml/data/raw/shuttlecock_trajectory"
    for sub in ("TrackNetV2/Train", "TrackNetV2/Test", "corrected"):
        paths += [str(p.relative_to(ROOT)) for p in (data / sub).rglob("*")
                  if p.is_file() and p.suffix in {".mp4", ".csv", ".json"}]
    files = []
    for rel in sorted(set(paths)):
        p = ROOT / rel
        if not p.resolve().is_relative_to(ROOT) or p.is_symlink():
            raise SystemExit(f"Refusing external/symlink input: {rel}")
        if not p.is_file():
            raise SystemExit(f"Required input missing: {rel}")
        files.append({"path": rel, "bytes": p.stat().st_size, "sha256": digest(p)})
    manifest = {"version": 1, "scope": "Detector training + frozen singles HitNet candidate, not the app server",
                "files": files, "total_bytes": sum(f["bytes"] for f in files)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".partial")
    with tarfile.open(temporary, "w:gz", compresslevel=1) as archive:
        for item in files:
            archive.add(ROOT / item["path"], arcname="shuttl-cloud/" + item["path"], recursive=False)
        encoded = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
        entry = tarfile.TarInfo("shuttl-cloud/BUNDLE_MANIFEST.json")
        entry.size = len(encoded)
        archive.addfile(entry, io.BytesIO(encoded))
    temporary.replace(args.output)
    checksum = digest(args.output)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(checksum + "  " + args.output.name + "\n")
    args.output.with_suffix(args.output.suffix + ".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({"archive": str(args.output.resolve()), "files": len(files),
                      "bytes": args.output.stat().st_size, "sha256": checksum}, indent=2))


if __name__ == "__main__":
    main()
