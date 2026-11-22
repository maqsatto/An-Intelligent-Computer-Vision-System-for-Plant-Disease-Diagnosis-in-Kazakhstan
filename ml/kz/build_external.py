"""In-the-wild set from PlantWild v1 (CC BY-NC-ND 4.0; non-commercial research use, weights never published).

Images that are near-duplicates (dHash <= 4) of any image in the training corpus are dropped so the
benchmark is not inflated by PlantDoc/PlantWild web-image overlap. Remaining images are clustered (dHash <= 4)
and the clusters are assigned to a ``dev`` half (may be used for training / calibration of "wild" models)
and a ``test`` half that is never used for training, model selection or calibration by any model.
"""

import hashlib
import multiprocessing as mp

import build_dataset as B
import numpy as np
import pandas as pd
from PIL import Image

IMG = B.DATA / "raw/plantwild/plantwild/images"
IMG2 = B.DATA / "raw/plantwild/v2/plantwild_v2"
MAP = {
    "apple black rot": "apple__black_rot", "apple leaf": "apple__healthy", "apple rust": "apple__cedar_rust",
    "apple scab": "apple__scab", "corn gray leaf spot": "maize__gray_leaf_spot", "corn leaf": "maize__healthy",
    "corn northern leaf blight": "maize__northern_leaf_blight", "corn rust": "maize__common_rust",
    "cucumber bacterial wilt": "cucumber__bacterial_wilt", "cucumber leaf": "cucumber__healthy",
    "grape black rot": "grape__black_rot", "grape leaf": "grape__healthy",
    "potato early blight": "potato__early_blight", "potato late blight": "potato__late_blight", "potato leaf": "potato__healthy",
    "tomato bacterial leaf spot": "tomato__bacterial_spot", "tomato early blight": "tomato__early_blight",
    "tomato late blight": "tomato__late_blight", "tomato leaf": "tomato__healthy", "tomato leaf mold": "tomato__leaf_mold",
    "tomato mosaic virus": "tomato__mosaic_virus", "tomato septoria leaf spot": "tomato__septoria_leaf_spot",
    "tomato yellow leaf curl virus": "tomato__yellow_leaf_curl_virus",
}
# conditions that exist only in PlantWild (no lab data): extra classes for the "wild" model
EXTRA = {
    "cucumber powdery mildew": "cucumber__powdery_mildew", "cucumber angular leaf spot": "cucumber__angular_leaf_spot",
    "grape downy mildew": "grape__downy_mildew", "grape leaf spot": "grape__leaf_blight",
    "corn smut": "maize__smut", "apple mosaic virus": "apple__mosaic_virus",
}
# PlantWild v2 additions (wheat in the field, extra maize/cucumber/grape conditions); legacy=False
V2_MAP = {
    "wheat leaf rust": "wheat__brown_rust", "wheat stripe rust": "wheat__stripe_rust", "wheat powdery mildew": "wheat__powdery_mildew",
    "wheat septoria blotch": "wheat__septoria", "wheat stem rust": "wheat__stem_rust", "wheat head scab": "wheat__head_scab",
    "wheat loose smut": "wheat__loose_smut",
    "apple black rot": "apple__black_rot", "apple mosaic virus": "apple__mosaic_virus", "apple rust": "apple__cedar_rust",
    "apple scab": "apple__scab", "corn gray leaf spot": "maize__gray_leaf_spot", "corn northern leaf blight": "maize__northern_leaf_blight",
    "corn rust": "maize__common_rust", "corn smut": "maize__smut", "cucumber angular leaf spot": "cucumber__angular_leaf_spot",
    "cucumber bacterial wilt": "cucumber__bacterial_wilt", "cucumber powdery mildew": "cucumber__powdery_mildew",
    "grape black rot": "grape__black_rot", "grape downy mildew": "grape__downy_mildew", "grape leaf spot": "grape__leaf_blight",
    "potato early blight": "potato__early_blight", "potato late blight": "potato__late_blight",
    "tomato bacterial leaf spot": "tomato__bacterial_spot", "tomato early blight": "tomato__early_blight",
    "tomato late blight": "tomato__late_blight", "tomato leaf mold": "tomato__leaf_mold", "tomato mosaic virus": "tomato__mosaic_virus",
    "tomato septoria leaf spot": "tomato__septoria_leaf_spot", "tomato yellow leaf curl virus": "tomato__yellow_leaf_curl_virus",
}
# v2 classes of crops/conditions we deliberately do not model; supported crops' other diseases are skipped, not "other"
V2_OTHER_CROPS = (
    "banana", "basil", "bean", "bell pepper", "blueberry", "broccoli", "cabbage", "carrot", "cauliflower", "celery", "cherry",
    "citrus", "coffee", "eggplant", "garlic", "ginger", "lettuce", "maple", "peach", "plum", "raspberry", "rice", "soybean",
    "squash", "strawberry", "tobacco", "zucchini",
)
OTHER = [
    "banana leaf", "basil leaf", "bean leaf", "bell pepper leaf", "blueberry leaf", "broccoli leaf", "cabbage leaf",
    "cauliflower leaf", "celery leaf", "cherry leaf", "coffee leaf", "eggplant leaf", "garlic leaf", "ginger leaf",
    "lettuce leaf", "maple leaf", "peach leaf", "plum leaf", "raspberry leaf", "rice leaf", "soybean leaf", "squash leaf",
    "strawberry leaf", "tobacco leaf",
]


def job(path):
    r = B.load(path)
    return None if r is None else (r[0], r[1])


def main():
    rows = []
    for cls, label in MAP.items():
        rows += [(p, label, cls, "in_scope", True) for p in sorted((IMG / cls).glob("*"))]
    for cls, label in EXTRA.items():
        rows += [(p, label, cls, "in_scope", False) for p in sorted((IMG / cls).glob("*"))]
    for cls in OTHER:
        rows += [(p, "other__non_target", cls, "other_plant", True) for p in sorted((IMG / cls).glob("*"))]
    if IMG2.exists():
        for cls, label in V2_MAP.items():
            rows += [(p, label, cls, "in_scope", False) for p in sorted((IMG2 / cls).glob("*"))]
        for d in sorted(IMG2.iterdir()):
            if d.name.startswith(V2_OTHER_CROPS):
                rows += [(p, "other__non_target", d.name, "other_plant", False) for p in sorted(d.glob("*"))]
    keep, hashes = [], []
    out = B.DATA / "pack_ext"
    out.mkdir(exist_ok=True)
    arr = np.lib.format.open_memmap(out / "images.npy", mode="w+", dtype=np.uint8, shape=(len(rows), 256, 256, 3))
    with mp.Pool(10) as pool:
        for row, res in zip(rows, pool.imap(job, [str(r[0]) for r in rows], chunksize=16)):
            if res is None:
                continue
            arr[len(keep)] = res[0]
            hashes.append(res[1])
            keep.append(row)
    arr.flush()
    # near-duplicate screen against the training corpus
    images = np.load(B.DATA / "pack/images.npy", mmap_mode="r")
    meta = pd.read_csv(B.DATA / "pack/meta.csv")
    train_h = {}
    for i in meta.idx.values:
        train_h[i] = B.dhash(Image.fromarray(np.asarray(images[i])))
    bands = [{} for _ in range(4)]
    for i, h in train_h.items():
        for b in range(4):
            bands[b].setdefault((h >> (16 * b)) & 0xFFFF, []).append(h)
    dup = []
    for h in hashes:
        d = False
        for b in range(4):
            for other in bands[b].get((h >> (16 * b)) & 0xFFFF, []):
                if bin(h ^ other).count("1") <= 4:
                    d = True
                    break
            if d:
                break
        dup.append(d)
    # clusters inside the external set -> dev/test halves (no near-duplicate straddles the halves)
    n = len(keep)
    parent = list(range(n))
    dup_within = [False] * n

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for band in range(4):
        buckets = {}
        for i, h in enumerate(hashes):
            buckets.setdefault((h >> (16 * band)) & 0xFFFF, []).append(i)
        for members in buckets.values():
            if len(members) > 300:
                continue
            for x in range(len(members)):
                for y in range(x + 1, len(members)):
                    dist = bin(hashes[members[x]] ^ hashes[members[y]]).count("1")
                    if dist <= 4:
                        parent[find(members[x])] = find(members[y])
                    if dist <= 2:  # same photo appearing twice (e.g. in PlantWild v1 and v2): keep the earlier row
                        dup_within[max(members[x], members[y])] = True
    root = [find(i) for i in range(n)]
    half = ["dev" if int(hashlib.sha256(f"wild:{r}".encode()).hexdigest(), 16) % 100 < 50 else "test" for r in root]
    pd.DataFrame(
        {
            "idx": range(n), "label": [k[1] for k in keep], "source_class": [k[2] for k in keep],
            "kind": [k[3] for k in keep], "legacy": [k[4] for k in keep], "dup_of_train": [a or b for a, b in zip(dup, dup_within, strict=True)], "cluster": root, "half": half,
        }
    ).to_csv(out / "meta.csv", index=False)
    print("external images", len(keep), "near-duplicates of training", sum(dup))


if __name__ == "__main__":
    main()
