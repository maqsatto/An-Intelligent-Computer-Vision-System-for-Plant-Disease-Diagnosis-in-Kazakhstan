"""Leaf foreground masks for PlantVillage rows (from the author's segmented images, black background).

Writes data/pack/masks.npy (N,256,256 uint8, 1 = leaf) and data/pack/has_mask.npy (N bool), aligned with
images.npy through the image SHA256. Used for background-replacement augmentation (lab -> field transfer).
"""

import hashlib
import multiprocessing as mp
from pathlib import Path

import build_dataset as B
import numpy as np
import pandas as pd
from PIL import Image

SIZE = B.SIZE


def job(args):
    path, seg = args
    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    try:
        im = Image.open(seg).convert("RGB")
        w, h = im.size
        scale = SIZE / min(w, h)
        im = im.resize((max(SIZE, round(w * scale)), max(SIZE, round(h * scale))), Image.BILINEAR)
        w, h = im.size
        left, top = (w - SIZE) // 2, (h - SIZE) // 2
        im = im.crop((left, top, left + SIZE, top + SIZE))
        arr = np.asarray(im)
        mask = (arr.max(axis=2) > 12).astype(np.uint8)
        return sha, mask
    except Exception:
        return sha, None


def main():
    meta = pd.read_csv(B.DATA / "pack/meta.csv")
    by_sha = {}
    for i, s in zip(meta.idx, meta.sha):
        by_sha.setdefault(s, []).append(i)
    rows = [r for r in B.collect() if r["source"] == "plantvillage"]
    tasks = []
    for r in rows:
        p = Path(r["path"])
        seg = p.parents[2] / "segmented" / p.parent.name / (p.stem + "_final_masked.jpg")
        tasks.append((str(p), str(seg)))
    n = len(meta)
    masks = np.lib.format.open_memmap(B.DATA / "pack/masks.npy", mode="w+", dtype=np.uint8, shape=(n, SIZE, SIZE))
    has = np.zeros(n, dtype=bool)
    with mp.Pool(14) as pool:
        for k, (sha, mask) in enumerate(pool.imap(job, tasks, chunksize=32)):
            if mask is None or sha not in by_sha:
                continue
            frac = mask.mean()
            if frac < 0.15 or frac > 0.97:  # failed / degenerate segmentation
                continue
            for i in by_sha[sha]:
                masks[i] = mask
                has[i] = True
            if k % 5000 == 0:
                print("masks", k, flush=True)
    masks.flush()
    np.save(B.DATA / "pack/has_mask.npy", has)
    print("masks available for", int(has.sum()), "of", n)


if __name__ == "__main__":
    main()
