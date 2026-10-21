"""Download admitted research pilot sources; never executes dataset code.

D05: Hawi Getachew, Wheat Leaf Dataset v1, CC BY 4.0,
https://doi.org/10.17632/wgd66f8n6h.1.
D01: Mohanty et al., PlantVillage (2016), CC BY-SA 3.0.
No image redistribution is performed by this repository.
"""

import argparse
import concurrent.futures
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADERS = {"User-Agent": "AgroVision-academic-pilot/0.1"}


def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(4):
        try:
            with (
                urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as response,
                temporary.open("wb") as out,
            ):
                while block := response.read(1024 * 1024):
                    out.write(block)
            temporary.replace(destination)
            return
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2**attempt)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def download_ranges(url, destination, size, expected_sha256, workers):
    """Parallel immutable byte ranges, validated before atomic installation."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and sha(destination) == expected_sha256:
        return

    def fetch(index):
        start, end = index * size // workers, (index + 1) * size // workers - 1
        part = destination.with_suffix(destination.suffix + f".range-{index}.part")
        if not part.exists() or part.stat().st_size != end - start + 1:
            request = urllib.request.Request(url, headers={**HEADERS, "Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(request, timeout=60) as response, part.open("wb") as stream:
                if (
                    response.status != 206
                    or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}"
                ):
                    raise ValueError("Provider did not honor exact byte range")
                while block := response.read(1024 * 1024):
                    stream.write(block)
        if part.stat().st_size != end - start + 1:
            raise ValueError("Range length mismatch")
        return part

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        parts = list(pool.map(fetch, range(workers)))
    temporary = destination.with_suffix(destination.suffix + ".part")
    with temporary.open("wb") as stream:
        for part in parts:
            with part.open("rb") as original:
                while block := original.read(1024 * 1024):
                    stream.write(block)
    if sha(temporary) != expected_sha256:
        raise ValueError("Provider SHA256 mismatch")
    temporary.replace(destination)
    for part in parts:
        part.unlink()


def wheat(workers=1):
    evidence = ROOT / "data/evidence/D05-files.json"
    download(
        "https://data.mendeley.com/public-api/datasets/wgd66f8n6h/files?folder_id=root&version=1&%24start=0&%24limit=1000",
        evidence,
    )
    files = json.loads(evidence.read_text())
    for file in files:
        target = ROOT / "data/raw/D05" / Path(file["filename"]).name
        if workers > 1:
            download_ranges(
                file["content_details"]["download_url"],
                target,
                file["content_details"]["size"],
                file["content_details"]["sha256_hash"],
                workers,
            )
        else:
            download(file["content_details"]["download_url"], target)
        if sha(target) != file["content_details"]["sha256_hash"]:
            raise ValueError("D05 published SHA256 mismatch")
    print("D05 verified against provider SHA256; run ml/training/extract_wheat.py")


def plantvillage(per_class):
    evidence = ROOT / "data/evidence"
    commit_file = evidence / "D01-commit.json"
    download("https://api.github.com/repos/spMohanty/PlantVillage-Dataset/commits/master", commit_file)
    commit = json.loads(commit_file.read_text())["sha"]
    download(
        f"https://raw.githubusercontent.com/spMohanty/PlantVillage-Dataset/{commit}/leaf_grouping/leaf-map.json",
        evidence / "D01-leaf-map.json",
    )
    tasks = []
    for crop in ("Potato", "Tomato"):
        for condition in ("Early_blight", "Late_blight", "healthy"):
            label = f"{crop}___{condition}"
            listing = evidence / f"D01-{label}.json"
            download(
                f"https://api.github.com/repos/spMohanty/PlantVillage-Dataset/contents/raw/color/{label}?ref={commit}",
                listing,
            )
            entries = sorted(
                json.loads(listing.read_text()), key=lambda x: hashlib.sha256(x["name"].encode()).hexdigest()
            )[:per_class]
            for entry in entries:
                url = (
                    "https://raw.githubusercontent.com/spMohanty/PlantVillage-Dataset/"
                    + commit
                    + "/"
                    + urllib.parse.quote(entry["path"])
                )
                tasks.append((url, ROOT / "data/images/D01" / label / entry["name"]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda args: download(*args), tasks))
    print(f"D01: downloaded {len(tasks)} original color images at commit {commit}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=["wheat", "plantvillage"])
    parser.add_argument("--per-class", type=int, default=120)
    parser.add_argument("--workers", type=int, default=1, choices=range(1, 9))
    args = parser.parse_args()
    if args.source == "wheat":
        wheat(args.workers)
    else:
        plantvillage(args.per_class)
