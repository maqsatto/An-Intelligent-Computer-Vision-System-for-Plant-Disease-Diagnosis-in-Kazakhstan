"""Metadata-only PlantDoc feasibility audit: never fetches images or trains.

Default reads previously fetched metadata. --fetch obtains only allowlisted
GitHub JSON, README/LICENSE and annotation CSV files from the author repositories.
The fetch resolves the current master commit for each repository and pins each
file to that commit; it does not reproduce a previously retained snapshot.
checked_on records the audit run date, not the original acquisition date.
"""

import argparse
import csv
import hashlib
import json
import math
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPOSITORIES = ("PlantDoc-Dataset", "PlantDoc-Object-Detection-Dataset")
CORE_MAPPING = {
    "Potato leaf early blight": "potato.early_blight",
    "Potato leaf late blight": "potato.late_blight",
    "Tomato Early blight leaf": "tomato.early_blight",
    "Tomato leaf late blight": "tomato.late_blight",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_metadata(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for repo in REPOSITORIES:
        request = urllib.request.Request(
            f"https://api.github.com/repos/pratikkayal/{repo}/commits/master",
            headers={"User-Agent": "AgroVision-metadata-audit"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            (destination / f"{repo}-commit.json").write_bytes(response.read())
        commit_metadata = json.loads((destination / f"{repo}-commit.json").read_text())
        commit = commit_metadata["sha"]
        tree_sha = commit_metadata["commit"]["tree"]["sha"]
        request = urllib.request.Request(
            f"https://api.github.com/repos/pratikkayal/{repo}/git/trees/{tree_sha}?recursive=1",
            headers={"User-Agent": "AgroVision-metadata-audit"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            (destination / f"{repo}-tree.json").write_bytes(response.read())
        names = ["README.md", "LICENSE.txt"]
        if "Object-Detection" in repo:
            names += ["train_labels.csv", "test_labels.csv"]
        for name in names:
            with urllib.request.urlopen(
                f"https://raw.githubusercontent.com/pratikkayal/{repo}/{commit}/{name}", timeout=30
            ) as response:
                (destination / f"{repo}-{name}").write_bytes(response.read())


def valid_box(row):
    try:
        w, h, x1, y1, x2, y2 = (
            float(row[key]) for key in ("width", "height", "xmin", "ymin", "xmax", "ymax")
        )
        return (
            all(math.isfinite(v) for v in (w, h, x1, y1, x2, y2))
            and w > 0
            and h > 0
            and 0 <= x1 < x2 <= w
            and 0 <= y1 < y2 <= h
        )
    except (ValueError, KeyError):
        return False


def validate_tree_binding(commit_metadata, tree_metadata):
    # GitHub may identify a resolved treeish by commit or tree SHA; both must
    # come from this exact pinned commit, never a separately fetched master.
    permitted = {commit_metadata["sha"], commit_metadata["commit"]["tree"]["sha"]}
    if tree_metadata.get("sha") not in permitted:
        raise ValueError("Tree metadata is not bound to the pinned commit")
    if tree_metadata.get("truncated"):
        raise ValueError("Truncated metadata tree cannot prove class availability")


def audit(evidence):
    repositories = {}
    for repo in REPOSITORIES:
        commit_metadata = json.loads((evidence / f"{repo}-commit.json").read_text())
        commit = commit_metadata["sha"]
        tree = json.loads((evidence / f"{repo}-tree.json").read_text())
        validate_tree_binding(commit_metadata, tree)
        repositories[repo] = dict(
            commit=commit,
            declared_license=None,
            license_sha256=digest(evidence / f"{repo}-LICENSE.txt"),
            primary_url=f"https://github.com/pratikkayal/{repo}",
            tree_truncated=False,
        )
    classification = Counter()
    tree = json.loads((evidence / "PlantDoc-Dataset-tree.json").read_text())["tree"]
    for item in tree:
        parts = item["path"].split("/")
        if (
            item["type"] == "blob"
            and len(parts) >= 3
            and parts[0] in {"train", "test"}
            and parts[1] in CORE_MAPPING
            and Path(parts[-1]).suffix.lower() in {".jpg", ".jpeg", ".png"}
        ):
            classification[(CORE_MAPPING[parts[1]], parts[0])] += 1
    annotations = defaultdict(list)
    total_rows = {}
    for split in ("train", "test"):
        with (evidence / f"PlantDoc-Object-Detection-Dataset-{split}_labels.csv").open(
            encoding="utf-8", newline=""
        ) as csv_file:
            rows = list(csv.DictReader(csv_file))
        total_rows[split] = len(rows)
        for row in rows:
            if row["class"] in CORE_MAPPING:
                annotations[CORE_MAPPING[row["class"]]].append((split, row))
    classes = {}
    for raw, canonical in CORE_MAPPING.items():
        entries = annotations[canonical]
        valid = [(split, row) for split, row in entries if valid_box(row)]
        unique = {
            (
                row["filename"],
                row["class"],
                row["xmin"],
                row["ymin"],
                row["xmax"],
                row["ymax"],
                row["width"],
                row["height"],
            )
            for _, row in valid
        }
        parents = {row["filename"] for _, row in valid}
        classes[canonical] = dict(
            raw_label=raw,
            classification_repository_image_entries={
                split: classification[(canonical, split)] for split in ("train", "test")
            },
            annotation_rows_by_provider_split=dict(Counter(split for split, _ in entries)),
            raw_annotation_rows=len(entries),
            invalid_geometry_rows=len(entries) - len(valid),
            distinct_valid_box_rows=len(unique),
            distinct_parent_filename_proxies=len(parents),
            parent_proxy_is_verified_independent_plant=False,
        )
    report = dict(
        status="metadata_only_not_image_admission",
        checked_on=date.today().isoformat(),
        images_downloaded=0,
        training_performed=False,
        repositories=repositories,
        core_classes=classes,
        all_four_raw_labels_present=all(annotations[c] for c in CORE_MAPPING.values()),
        detection_csv_total_rows=total_rows,
        paper_reported_boxes=9216,
        discrepancy="Current author CSV row totals and classification tree are version-specific metadata, not the paper count and not decoded crop counts.",
        evidence_sha256={p.name: digest(p) for p in sorted(evidence.iterdir()) if p.is_file()},
        experiment_go_no_go="NO_GO_PENDING_IMAGE_RIGHTS_PARENT_DEDUP_AUDIT",
        remaining_gates=[
            "image decoding and bbox-to-original resolution validation",
            "source label and rights acceptance review",
            "original-parent/leaf/session linkage and cross-source exact/near duplicate audit",
            "all four eligible class group counts, frozen splits and manifest hashes",
        ],
        limitations=[
            "License file and third-party web-image rights require independent review.",
            "Distinct filenames and boxes are not independent plants or verified dedup groups.",
            "No held-out image predictions or target-based tuning were generated.",
        ],
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--evidence", default="data/evidence/scientific-protocol")
    parser.add_argument("--output", default="docs/data/PLANTDOC_METADATA_AUDIT.json")
    args = parser.parse_args()
    evidence = ROOT / args.evidence
    if args.fetch:
        fetch_metadata(evidence)
    report = audit(evidence)
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "all_four_raw_labels_present",
                    "core_classes",
                    "detection_csv_total_rows",
                    "experiment_go_no_go",
                ]
            },
            indent=2,
        )
    )
