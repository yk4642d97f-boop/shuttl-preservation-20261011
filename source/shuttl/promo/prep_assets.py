"""Copy the approved app screenshots + icon into promo/assets and bake the paper grain."""
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
PROJ = ROOT.parent
OUT = ROOT / "assets"
SHOTS = PROJ / "screenshots" / "review-1644-final"

PICK = {
    "detail": "03_detail_calibrated.png",
    "matches": "01_matches.png",
    "analyzing": "12_detail_analyzing.png",
    "rec_upright": "15_record_upright_rotate.png",
    "rec_search": "17_record_land_searching.png",
    "rec_candidate": "18_record_land_candidate.png",
    "rec_locked": "19_record_land_locked.png",
    "rec_recording": "20_record_land_recording.png",
    "replay": "22_replay_landscape.png",
    "court": "08_results_court.png",
    "rallies": "09_results_rallies.png",
    "stats": "07_stats.png",
}


def grain(w=1080, h=1920, seed=7):
    """Uncoated-stock speckle: fine noise plus sparse darker fibres, as a multiply layer."""
    rng = np.random.default_rng(seed)
    fine = rng.normal(0, 1, (h, w))
    specks = (rng.random((h, w)) > 0.9965) * rng.uniform(0.35, 1.0, (h, w))
    v = 1.0 - np.clip(0.035 * np.abs(fine) + 0.22 * specks, 0, 0.5)
    rgb = np.stack([v * 255, v * 250, v * 244], -1).astype(np.uint8)
    Image.fromarray(rgb).save(OUT / "grain.png", optimize=True)


def main():
    (OUT / "shots").mkdir(parents=True, exist_ok=True)
    for name, src in PICK.items():
        shutil.copyfile(SHOTS / src, OUT / "shots" / f"{name}.png")
    icon = PROJ / "iOS/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon-Light.png"
    Image.open(icon).convert("RGB").resize((512, 512), Image.LANCZOS).save(OUT / "icon.png")
    grain()
    print("assets ready:", sorted(p.name for p in (OUT / "shots").iterdir()))


if __name__ == "__main__":
    main()
