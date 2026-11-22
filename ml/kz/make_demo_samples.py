"""Pick a few held-out (test / field_test) photos as demo samples, without looking at model outcomes.

Selection is deterministic (lowest SHA256 per label+source among held-out rows). Originals are downsized
to <= 720 px for the repository; sources, licences and attribution go to samples.json.
"""

import json
import sys
from pathlib import Path

import build_dataset as B
import pandas as pd
from PIL import Image, ImageOps

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else B.ROOT / "demo_samples")
WANT = [
    ("wheat__stripe_rust", "wheat_jic_field"), ("wheat__brown_rust", "wheat_jic_field"),
    ("wheat__septoria", "wheat_jic_field"), ("wheat__powdery_mildew", "wheat_jic_field"),
    ("wheat__healthy", "wheat_jic_field"), ("sunflower__downy_mildew", "sunflower"),
    ("sunflower__gray_mold", "sunflower"), ("potato__late_blight", "plantdoc"),
    ("tomato__late_blight", "plantdoc"), ("maize__common_rust", "plantdoc"), ("apple__scab", "plantdoc"),
    ("grape__black_rot", "plantvillage"), ("tomato__yellow_leaf_curl_virus", "plantvillage"),
    ("other__non_target", "tinyimagenet"),
]
SOURCE_INFO = {
    "wheat_jic_field": ("Long et al. 2023, Wheat disease images (small dataset), John Innes Centre, Zenodo 7573133", "CC-BY-4.0"),
    "sunflower": ("Sunflower disease classification (Project-AgML)", "CC-BY-4.0"),
    "plantdoc": ("PlantDoc: Singh et al. 2020 (field photographs)", "CC-BY-SA-4.0"),
    "plantvillage": ("PlantVillage: Hughes & Salathe 2015; Mohanty et al. 2016", "CC-BY-SA-3.0"),
    "tinyimagenet": ("Tiny ImageNet (non-plant negative example)", "research use"),
}


def main():
    meta = pd.read_csv(B.DATA / "pack/meta.csv")
    paths = {}
    import hashlib

    for r in B.collect():
        paths[hashlib.sha256(Path(r["path"]).read_bytes()).hexdigest()] = r["path"]
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    held = meta[meta.split.isin(["test", "field_test"])]
    for label, source in WANT:
        rows = held[(held.label == label) & (held.source == source)].sort_values("sha")
        if rows.empty:
            continue
        row = rows.iloc[0]
        src = Path(paths[row.sha])
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        im.thumbnail((720, 720))
        name = f"{label}.jpg"
        im.save(OUT / name, "JPEG", quality=86)
        manifest.append(dict(file=name, label=label, source=SOURCE_INFO[source][0], license=SOURCE_INFO[source][1], split=row.split))
    (OUT / "samples.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(len(manifest), "samples")


if __name__ == "__main__":
    main()
