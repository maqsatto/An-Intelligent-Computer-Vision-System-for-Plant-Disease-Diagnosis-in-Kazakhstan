"""Build immutable pilot manifests and conservative independent-group splits.

Exact SHA256 and conservative 64-bit dHash near duplicates are unioned BEFORE
split. PlantVillage author's physical-leaf groups are additionally unioned.
D05 does not publish plant/session IDs: groups are dedup proxies only; biological
independence is NOT established. Conflicting class groups are quarantined.
"""

import collections
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
MAPPINGS = {
    "Potato___Early_blight": ("potato", "early_blight"),
    "Potato___Late_blight": ("potato", "late_blight"),
    "Potato___healthy": ("potato", "healthy_appearance"),
    "Tomato___Early_blight": ("tomato", "early_blight"),
    "Tomato___Late_blight": ("tomato", "late_blight"),
    "Tomato___healthy": ("tomato", "healthy_appearance"),
}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def main():
    images = ROOT / "data/images"
    leaf_map_file = ROOT / "data/evidence/D01-leaf-map.json"
    leaf_map = json.loads(leaf_map_file.read_text()) if leaf_map_file.exists() else {}
    pv_commit = json.loads((ROOT / "data/evidence/D01-commit.json").read_text())["sha"]
    rows = []
    errors = []
    for path in sorted(images.rglob("*")):
        if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"):
            continue
        dataset = path.relative_to(images).parts[0]
        source_label = path.parent.name
        if dataset == "D01":
            if source_label not in MAPPINGS:
                continue
            crop, condition = MAPPINGS[source_label]
            key = path.stem.split("___")[-1].lower()
            leaf_ids = leaf_map.get(key, [])
            license_id = "CC-BY-SA-3.0"
            country = None
            source_url = "https://huggingface.co/datasets/mohanty/PlantVillage"
        elif dataset == "D05":
            normalized = str(path.relative_to(images / dataset)).lower()
            crop = "wheat"
            if "healthy" in normalized:
                condition = "healthy_appearance"
            elif "septoria" in normalized:
                condition = "septoria_source_label"
            elif "rust" in normalized:
                condition = "stripe_rust"
            else:
                errors.append({"path": str(path), "reason": "unmapped_source_label"})
                continue
            leaf_ids = []
            license_id = "CC-BY-4.0"
            country = "Ethiopia"
            source_url = "https://data.mendeley.com/datasets/wgd66f8n6h/1"
        else:
            errors.append({"path": str(path), "reason": "source_not_admitted"})
            continue
        raw = path.read_bytes()
        try:
            with Image.open(path) as original:
                original.load()
                image = ImageOps.exif_transpose(original).convert("RGB")
                width, height = image.size
                small = list(image.convert("L").resize((9, 8), Image.Resampling.BILINEAR).getdata())
                bits = [small[y * 9 + x] > small[y * 9 + x + 1] for y in range(8) for x in range(8)]
                dhash = sum(int(value) << index for index, value in enumerate(bits))
        except Exception as exc:
            errors.append({"path": str(path), "reason": str(exc)})
            continue
        sha = digest(raw)
        rows.append(
            dict(
                image_id=digest((dataset + ":" + str(path.relative_to(images))).encode()),
                case_id=None,
                relative_path=str(path.relative_to(ROOT)),
                sha256=sha,
                source_dataset=dataset,
                source_version="1" if dataset == "D05" else pv_commit,
                source_image_id=path.name,
                source_url=source_url,
                downloaded_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                license_id=license_id,
                license_evidence_ref=f"data/evidence/{dataset}-source.html"
                if dataset == "D05"
                else "data/evidence/D01-license.md",
                allowed_use_status="admitted_academic_research",
                width_px=width,
                height_px=height,
                file_format=path.suffix.lower(),
                modality="RGB",
                country=country,
                plant_id=None,
                leaf_id=leaf_ids[0] if len(leaf_ids) == 1 else None,
                leaf_group_ids=leaf_ids,
                capture_session_id=None,
                unknown_context_reason="source does not publish plant/session identifiers",
                parent_image_id=None,
                crop_id=crop,
                condition_id=condition,
                class_id=f"{crop}__{condition}",
                organ="leaf",
                ontology_version="pilot-source-labels-v1",
                source_label=source_label,
                label_method="original_dataset_label",
                label_status="source_not_independently_verified",
                quality_status="decoded_not_expert_assessed",
                dhash=f"{dhash:016x}",
                exclusion_reason="missing_author_leaf_group" if dataset == "D01" and not leaf_ids else None,
            )
        )
    parents = list(range(len(rows)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(a, b):
        a, b = find(a), find(b)
        parents[max(a, b)] = min(a, b)

    groups = {}
    for index, row in enumerate(rows):
        for key in ["sha:" + row["sha256"]] + ["leaf:" + x for x in row["leaf_group_ids"]]:
            if key in groups:
                union(index, groups[key])
            else:
                groups[key] = index
    near_pairs = []
    for i, row in enumerate(rows):
        for j in range(i):
            if (int(row["dhash"], 16) ^ int(rows[j]["dhash"], 16)).bit_count() <= 4:
                union(i, j)
                near_pairs.append([row["image_id"], rows[j]["image_id"]])
    members = collections.defaultdict(list)
    for i in range(len(rows)):
        members[find(i)].append(i)
    seen_sha = set()
    for indices in members.values():
        group_id = digest("|".join(sorted({rows[i]["sha256"] for i in indices})).encode())
        conflict = len({rows[i]["class_id"] for i in indices}) > 1
        fraction = int(digest(("17:" + group_id).encode())[:12], 16) / 16**12
        split = (
            "train"
            if fraction < 0.70
            else "validation"
            if fraction < 0.80
            else "calibration"
            if fraction < 0.85
            else "test"
        )
        for i in indices:
            row = rows[i]
            row["dedup_cluster_id"] = group_id
            row["split_group_id"] = group_id
            row["split"] = "quarantine" if conflict or row["exclusion_reason"] else split
            row["split_protocol_id"] = "group-hash17-70-10-5-15-v1"
            if conflict:
                row["exclusion_reason"] = "conflicting_labels_in_related_group"
            elif row["sha256"] in seen_sha:
                row["exclusion_reason"] = "exact_duplicate"
            seen_sha.add(row["sha256"])
    output = ROOT / "data/manifests"
    output.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    (output / "pilot.jsonl").write_text(payload)
    split_payload = "".join(
        json.dumps(
            {k: row[k] for k in ("image_id", "split_group_id", "split", "exclusion_reason")}, sort_keys=True
        )
        + "\n"
        for row in rows
    )
    (output / "splits.jsonl").write_text(split_payload)
    labels = sorted(
        {
            (r["class_id"], r["crop_id"], r["condition_id"])
            for r in rows
            if not r["exclusion_reason"] and r["split"] != "quarantine"
        }
    )
    (output / "labels.json").write_text(
        json.dumps(
            [dict(class_id=c, crop_id=p, condition_id=d, organ="leaf") for c, p, d in labels], indent=2
        )
    )
    report = dict(
        images=len(rows),
        groups=len(members),
        near_duplicate_pairs=len(near_pairs),
        decode_or_mapping_errors=errors,
        split_counts=dict(collections.Counter(r["split"] for r in rows if not r["exclusion_reason"])),
        class_counts=dict(collections.Counter(r["class_id"] for r in rows)),
        exclusions=dict(collections.Counter(r["exclusion_reason"] for r in rows if r["exclusion_reason"])),
        source_evidence_sha256={
            name: digest((ROOT / "data/evidence" / name).read_bytes())
            for name in (
                "D01-leaf-map.json",
                "D01-license.md",
                "D01-commit.json",
                "D05-files.json",
                "D05-source.html",
                "D05-acquisition.json",
            )
            if (ROOT / "data/evidence" / name).exists()
        },
        dataset_manifest_sha256=digest(payload.encode()),
        split_manifest_sha256=digest(split_payload.encode()),
        limitations=[
            "D05 biological plant/session independence unverified",
            "dHash is a conservative proxy, not exhaustive near-duplicate validation",
            "No Kazakhstan or unseen-condition/negative/OOD evaluation",
        ],
    )
    (output / "audit.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
