"""Training pack "wild": the base pack plus the PlantWild *dev* half (never the *test* half).

PlantWild is CC BY-NC-ND 4.0: this pack/weights are for local non-commercial research and are not distributed.
Dev-half clusters are split 90/10 into train / val (the val part is the calibration set for wild models).
"""

import hashlib
import sys

import build_dataset as B
import numpy as np
import pandas as pd


def main():
    base = B.DATA / "pack"
    out = B.DATA / (sys.argv[1] if len(sys.argv) > 1 else "pack_w")
    out.mkdir(exist_ok=True)
    meta = pd.read_csv(base / "meta.csv")
    n = int(np.load(base / "images_n.npy")[0])
    images = np.load(base / "images.npy", mmap_mode="r")
    ext = pd.read_csv(B.DATA / "pack_ext/meta.csv")
    ext = ext[(~ext.dup_of_train) & (ext.half == "dev")].reset_index(drop=True)
    ext_images = np.load(B.DATA / "pack_ext/images.npy", mmap_mode="r")
    total = n + len(ext)
    mm = np.lib.format.open_memmap(out / "images.npy", mode="w+", dtype=np.uint8, shape=(total, B.SIZE, B.SIZE, 3))
    for i in range(0, n, 2000):
        j = min(i + 2000, n)
        mm[i:j] = images[i:j]
    rows = []
    for k, r in ext.iterrows():
        arr = np.asarray(ext_images[int(r.idx)])
        mm[n + k] = arr
        crop, cond = r.label.split("__")
        val = int(hashlib.sha256(f"wildval:{r.cluster}".encode()).hexdigest(), 16) % 100 < 10
        rows.append(
            dict(
                idx=n + k, source="plantwild", domain="field", crop=crop, condition=cond, label=r.label,
                group=10_000_000 + int(r.cluster), split="val" if val else "train", sha=hashlib.sha256(arr.tobytes()).hexdigest(),
            )
        )
    mm.flush()
    full = pd.concat([meta, pd.DataFrame(rows)], ignore_index=True)
    full.to_csv(out / "meta.csv", index=False)
    np.save(out / "images_n.npy", np.array([total]))
    print(full.groupby(["source", "split"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
