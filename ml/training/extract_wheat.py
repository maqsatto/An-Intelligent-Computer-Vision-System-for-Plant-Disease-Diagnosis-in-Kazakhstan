"""Verify D05 provider hash, then safely extract original images only.

Supports the provider ZIP wrapper from Download All or the direct RAR obtained
by acquire.py wheat. Requires libarchive's bsdtar; no archive code is executed.
"""

import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main():
    raw = ROOT / "data/raw/D05"
    source = raw / "source.zip"
    metadata = json.loads((ROOT / "data/evidence/D05-files.json").read_text())
    info = next(item for item in metadata if item["filename"] == "wheat_leaf.rar")
    archive = raw / info["filename"]
    if not archive.exists():
        with zipfile.ZipFile(source) as wrapper:
            entries = [
                item for item in wrapper.infolist() if PurePosixPath(item.filename).name == info["filename"]
            ]
            if len(entries) != 1:
                raise ValueError("Expected exactly one provider RAR")
            temporary = archive.with_suffix(".rar.part")
            with wrapper.open(entries[0]) as original, temporary.open("wb") as out:
                shutil.copyfileobj(original, out)
            temporary.replace(archive)
    archive_hash = sha(archive)
    if archive_hash != info["content_details"]["sha256_hash"]:
        raise ValueError("Provider SHA256 mismatch: extraction refused")
    names = subprocess.check_output(["bsdtar", "-tf", str(archive)], text=True).splitlines()
    images = []
    for name in names:
        path = PurePosixPath(name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe archive member")
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}:
            images.append(name)
    destination = ROOT / "data/images/D05"
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "bsdtar",
            "-xf",
            str(archive),
            "-C",
            str(destination),
            "--no-same-owner",
            "--no-same-permissions",
            "--",
            *images,
        ],
        check=True,
    )
    for path in destination.rglob("*"):
        if path.is_symlink() or not path.resolve().is_relative_to(destination.resolve()):
            raise ValueError("Unexpected extracted symlink/path")
    report = dict(
        source_url="https://data.mendeley.com/datasets/wgd66f8n6h/1",
        archive=archive.name,
        provider_sha256=archive_hash,
        archive_size=archive.stat().st_size,
        extracted_image_count=len(images),
    )
    if source.exists() and zipfile.is_zipfile(source):
        report["zip_wrapper_sha256"] = sha(source)
    (ROOT / "data/evidence/D05-acquisition.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
