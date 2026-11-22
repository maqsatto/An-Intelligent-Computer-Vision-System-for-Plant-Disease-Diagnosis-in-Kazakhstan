"""Build the Kazakhstan-agriculture crop-disease corpus (leaf classification).

Stage 1 (`fetch`): download public sources to ``data/raw`` (no dataset code is executed).
Stage 2 (`pack`): decode every image once, resize (shorter side 256, centre crop 256x256),
compute a 64-bit dHash, build near-duplicate groups (+ PlantVillage physical-leaf ids),
assign grouped train/val/test splits and write ``data/pack/images.u8`` (memmap) + ``meta.csv``.

Labels are ``crop__condition``. The crop set follows the Kazakhstan agrosector (wheat,
sunflower, maize, potato, tomato, cucumber, apple, grape).
"""

import argparse
import csv
import hashlib
import json
import multiprocessing as mp
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SIZE = 256

PV_CROPS = {"Apple": "apple", "Corn_(maize)": "maize", "Grape": "grape", "Potato": "potato", "Tomato": "tomato"}
PV_COND = {
    "Apple_scab": "scab", "Black_rot": "black_rot", "Cedar_apple_rust": "cedar_rust", "healthy": "healthy",
    "Cercospora_leaf_spot Gray_leaf_spot": "gray_leaf_spot", "Common_rust_": "common_rust",
    "Northern_Leaf_Blight": "northern_leaf_blight", "Esca_(Black_Measles)": "esca",
    "Leaf_blight_(Isariopsis_Leaf_Spot)": "leaf_blight", "Early_blight": "early_blight",
    "Late_blight": "late_blight", "Bacterial_spot": "bacterial_spot", "Leaf_Mold": "leaf_mold",
    "Septoria_leaf_spot": "septoria_leaf_spot", "Spider_mites Two-spotted_spider_mite": "spider_mites",
    "Target_Spot": "target_spot", "Tomato_Yellow_Leaf_Curl_Virus": "yellow_leaf_curl_virus",
    "Tomato_mosaic_virus": "mosaic_virus",
}
# (hf repo, label name -> (crop, condition), domain, license)
HF_SOURCES = {
    "sunflower": ("Project-AgML/sunflower_disease_classification", {
        "Downy_mildew": ("sunflower", "downy_mildew"), "Fresh_leaf": ("sunflower", "healthy"),
        "Gray_mold": ("sunflower", "gray_mold"), "Leaf_scars": ("sunflower", "leaf_scars")}, "field", "CC-BY-4.0"),
    "cucumber": ("Project-AgML/cucumber_disease_classification", {
        "Anthracnose": ("cucumber", "anthracnose"), "Bacterial_Wilt": ("cucumber", "bacterial_wilt"),
        "Downy_Mildew": ("cucumber", "downy_mildew"), "Gummy_Stem_Blight": ("cucumber", "gummy_stem_blight"),
        "Fresh_Leaf": ("cucumber", "healthy")}, "field", "see-source"),
    "potato_field": ("Project-AgML/potato_leaf_disease_classification", {
        "Healthy": ("potato", "healthy"), "Phytopthora": ("potato", "late_blight")}, "field", "CC-BY-4.0"),
    "plantdoc": ("Project-AgML/plant_doc_classification", {
        "Apple Scab Leaf": ("apple", "scab"), "Apple leaf": ("apple", "healthy"),
        "Apple rust leaf": ("apple", "cedar_rust"), "Corn Gray leaf spot": ("maize", "gray_leaf_spot"),
        "Corn leaf blight": ("maize", "northern_leaf_blight"), "Corn rust leaf": ("maize", "common_rust"),
        "Potato leaf early blight": ("potato", "early_blight"), "Potato leaf late blight": ("potato", "late_blight"),
        "Tomato Early blight leaf": ("tomato", "early_blight"), "Tomato Septoria leaf spot": ("tomato", "septoria_leaf_spot"),
        "Tomato leaf": ("tomato", "healthy"), "Tomato leaf bacterial spot": ("tomato", "bacterial_spot"),
        "Tomato leaf late blight": ("tomato", "late_blight"), "Tomato leaf mosaic virus": ("tomato", "mosaic_virus"),
        "Tomato leaf yellow virus": ("tomato", "yellow_leaf_curl_virus"), "Tomato mold leaf": ("tomato", "leaf_mold"),
        "Tomato two spotted spider mites leaf": ("tomato", "spider_mites"),
        "grape leaf": ("grape", "healthy"), "grape leaf black rot": ("grape", "black_rot"),
        "Bell_pepper leaf": ("other", "non_target"), "Bell_pepper leaf spot": ("other", "non_target"),
        "Blueberry leaf": ("other", "non_target"), "Cherry leaf": ("other", "non_target"),
        "Peach leaf": ("other", "non_target"), "Raspberry leaf": ("other", "non_target"),
        "Soyabean leaf": ("other", "non_target"), "Squash Powdery mildew leaf": ("other", "non_target"),
        "Strawberry leaf": ("other", "non_target")}, "field", "CC-BY-SA-4.0"),
}
# generic non-plant imagery (hard negatives for the rejection class)
GENERIC = {"tinyimagenet": ("zh-plus/tiny-imagenet", "train", 2400), "dtd": ("tanganke/dtd", "train", 1200)}


def fetch_generic(name):
    from datasets import Image as HFImage
    from datasets import load_dataset

    repo, split, count = GENERIC[name]
    ds = load_dataset(repo, split=split).cast_column("image", HFImage(decode=False))
    step = max(1, len(ds) // count)
    out = DATA / "raw" / name
    out.mkdir(parents=True, exist_ok=True)
    for index in range(0, len(ds), step):
        (out / f"{index:06d}.img").write_bytes(ds[index]["image"]["bytes"])
    print(name, "fetched")


def fetch_hf(name):
    from datasets import Image as HFImage
    from datasets import load_dataset

    repo, mapping, _, _ = HF_SOURCES[name]
    out = DATA / "raw" / name
    ds = load_dataset(repo, split="train")
    names = ds.features["label"].names
    ds = ds.cast_column("image", HFImage(decode=False))
    for index, row in enumerate(ds):
        label = names[row["label"]]
        if label not in mapping:
            continue
        target = out / label.replace(" ", "_") / f"{index:06d}.img"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(row["image"]["bytes"])
    print(name, "fetched", len(ds))


def fetch_wheat():
    import urllib.request

    files = DATA / "raw/D05-files.json"
    files.parent.mkdir(parents=True, exist_ok=True)
    url = "https://data.mendeley.com/public-api/datasets/wgd66f8n6h/files?folder_id=root&version=1&%24start=0&%24limit=1000"
    if not files.exists():
        files.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "agrovision"}), timeout=60).read())
    info = next(x for x in json.loads(files.read_text()) if x["filename"].endswith(".rar"))
    rar = DATA / "raw/wheat_leaf.rar"
    if not rar.exists() or rar.stat().st_size != info["content_details"]["size"]:
        subprocess.run(["curl", "-L", "-sS", "--retry", "5", "-o", str(rar), info["content_details"]["download_url"]], check=True)
    digest = hashlib.sha256(rar.read_bytes() if rar.stat().st_size < 3e9 else b"").hexdigest()
    if digest != info["content_details"]["sha256_hash"]:
        raise SystemExit("D05 sha256 mismatch")
    dest = DATA / "raw/wheat"
    dest.mkdir(exist_ok=True)
    subprocess.run(["bsdtar", "-xf", str(rar), "-C", str(dest)], check=True)
    print("wheat extracted")


def dhash(img):
    small = np.asarray(img.convert("L").resize((9, 8), Image.BILINEAR), dtype=np.int16)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def load(path):
    try:
        im = Image.open(path)
        im.draft("RGB", (SIZE * 2, SIZE * 2))
        im = ImageOps.exif_transpose(im).convert("RGB")
        w, h = im.size
        if w * h > 50_000_000:
            return None
        scale = SIZE / min(w, h)
        im = im.resize((max(SIZE, round(w * scale)), max(SIZE, round(h * scale))), Image.BILINEAR)
        w, h = im.size
        left, top = (w - SIZE) // 2, (h - SIZE) // 2
        im = im.crop((left, top, left + SIZE, top + SIZE))
        return np.asarray(im, dtype=np.uint8), dhash(im), hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except Exception:
        return None


def collect():
    rows = []
    leaf_map = json.loads((DATA / "pv/leaf_grouping/leaf-map.json").read_text())
    for folder in sorted((DATA / "pv/raw/color").iterdir()):
        crop_raw, cond_raw = folder.name.split("___")
        if crop_raw not in PV_CROPS:
            # unsupported plants become the explicit "other__non_target" rejection class
            files = sorted(
                (p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")),
                key=lambda p: hashlib.sha256(p.name.encode()).hexdigest(),
            )[:220]
            for p in files:
                leaf = leaf_map.get(p.stem.split("___")[-1].lower(), [])
                rows.append(dict(path=p, source="plantvillage_other", domain="lab", crop="other", condition="non_target", leaf=leaf[0] if leaf else ""))
            continue
        crop, cond = PV_CROPS[crop_raw], PV_COND[cond_raw]
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            leaf = leaf_map.get(p.stem.split("___")[-1].lower(), [])
            rows.append(dict(path=p, source="plantvillage", domain="lab", crop=crop, condition=cond, leaf=leaf[0] if leaf else ""))
    for name, (_, mapping, domain, _) in HF_SOURCES.items():
        for label, (crop, cond) in mapping.items():
            for p in sorted((DATA / "raw" / name / label.replace(" ", "_")).glob("*.img")):
                rows.append(dict(path=p, source=name, domain=domain, crop=crop, condition=cond, leaf=""))
    for name in GENERIC:
        for p in sorted((DATA / "raw" / name).glob("*.img")):
            rows.append(dict(path=p, source=name, domain="generic", crop="other", condition="non_target", leaf=""))
    for p in sorted((DATA / "raw/wheat").rglob("*")):
        if p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        low = str(p).lower()
        cond = "healthy" if "healthy" in low else "septoria" if "septoria" in low else "stripe_rust" if "rust" in low else None
        if cond:
            rows.append(dict(path=p, source="wheat_leaf_mendeley", domain="field", crop="wheat", condition=cond, leaf=""))
    for p in sorted((DATA / "raw/wheat_jic").rglob("*")):
        if p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        low = p.name.lower()
        cond = (
            "stripe_rust" if "yellow" in low
            else "brown_rust" if "brown" in low
            else "powdery_mildew" if "mildew" in low
            else "septoria" if "septoria" in low
            else "healthy" if "healthy" in low
            else None
        )
        if cond:
            rows.append(dict(path=p, source="wheat_jic_field", domain="field", crop="wheat", condition=cond, leaf=""))
    return rows


class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def pack():
    rows = collect()
    print("candidates", len(rows), flush=True)
    out = DATA / "pack"
    out.mkdir(exist_ok=True)
    mm = np.lib.format.open_memmap(out / "images.npy", mode="w+", dtype=np.uint8, shape=(len(rows), SIZE, SIZE, 3))
    keep = []
    with mp.Pool(14) as pool:
        for i, res in enumerate(pool.imap(load, [str(r["path"]) for r in rows], chunksize=16)):
            if res is None:
                continue
            arr, h, sha = res
            idx = len(keep)
            mm[idx] = arr
            rows[i].update(dhash=h, sha=sha)
            keep.append(rows[i])
            if i % 5000 == 0:
                print("packed", i, flush=True)
    mm.flush()
    n = len(keep)
    dsu = DSU(n)
    first = {}
    for i, r in enumerate(keep):
        for k in (("sha", r["sha"]), ("leaf", r["leaf"]) if r["leaf"] else None):
            if k is None:
                continue
            if k in first:
                dsu.union(i, first[k])
            else:
                first[k] = i
    # near-duplicates: dHash Hamming <= 4 via 4 x 16-bit bands (pigeonhole)
    hashes = [r["dhash"] for r in keep]
    for band in range(4):
        buckets = {}
        for i, h in enumerate(hashes):
            buckets.setdefault((h >> (16 * band)) & 0xFFFF, []).append(i)
        for members in buckets.values():
            if len(members) > 400:
                continue
            for a in range(len(members)):
                for b in range(a + 1, len(members)):
                    if bin(hashes[members[a]] ^ hashes[members[b]]).count("1") <= 4 and keep[members[a]]["crop"] == keep[members[b]]["crop"]:
                        dsu.union(members[a], members[b])
    groups = {}
    for i in range(n):
        groups.setdefault(dsu.find(i), []).append(i)
    print("groups", len(groups), "images", n, flush=True)

    def bucket(root, label):
        v = int(hashlib.sha256(f"17:{root}".encode()).hexdigest(), 16) % 1000 / 1000
        return v

    for root, members in groups.items():
        labs = {(keep[m]["crop"], keep[m]["condition"]) for m in members}
        v = bucket(root, "")
        # PlantDoc is the field benchmark: 50% of its groups form the held-out field test.
        field_src = {keep[m]["source"] for m in members} == {"plantdoc"}
        if field_src:
            split = "field_test" if v < 0.5 else "train"
        else:
            split = "train" if v < 0.78 else "val" if v < 0.86 else "test"
        for m in members:
            keep[m]["split"] = split if len(labs) == 1 else "quarantine"
            keep[m]["group"] = root
    # compact the memmap to kept rows is already contiguous (idx == position in keep)
    arr = np.load(out / "images.npy", mmap_mode="r+")
    np.save(out / "images_n.npy", np.array([n]))
    with (out / "meta.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx", "source", "domain", "crop", "condition", "label", "group", "split", "sha"])
        for i, r in enumerate(keep):
            w.writerow([i, r["source"], r["domain"], r["crop"], r["condition"], f'{r["crop"]}__{r["condition"]}', r["group"], r["split"], r["sha"]])
    del arr
    print("done", n)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["fetch", "pack"])
    ap.add_argument("--only")
    a = ap.parse_args()
    if a.stage == "fetch":
        names = [a.only] if a.only else list(HF_SOURCES) + list(GENERIC) + ["wheat"]
        for name in names:
            if name == "wheat":
                fetch_wheat()
            elif name in GENERIC:
                fetch_generic(name)
            else:
                fetch_hf(name)
    else:
        pack()
