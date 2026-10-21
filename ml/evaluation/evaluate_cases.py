"""CPU-only, deterministic replay and illustrative case evaluation of local research bundles.

No training, threshold tuning or real OOD validation. Image/plot outputs remain
under ignored artifacts/. Aggregate reports contain no image bytes.
"""

import argparse
import hashlib
import io
import json
import platform
import resource
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ml/runtime"), str(ROOT / "server")]
from agrovision.errors import APIError  # noqa: E402
from agrovision.photos.service import normalize_image  # noqa: E402
from agrovision_runtime import (  # noqa: E402
    InputImageError,
    ResearchOnnxPredictor,
    preprocess,
    validate_image_geometry,
    validate_research_bundle,
)

OFFLINE_SOURCE_LIMIT = 50_000_000
TRANSFORMS = ("clean", "blur_radius4", "rotate90", "dark_0.15", "jpeg_quality5")


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while block := f.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def guard():
    available = (
        int(
            next(
                line.split()[1]
                for line in Path("/proc/meminfo").read_text().splitlines()
                if line.startswith("MemAvailable:")
            )
        )
        / 1024**2
    )
    if available < 3:
        raise RuntimeError(f"RAM guard: {available:.2f} GiB available, require 3 GiB")
    return available


def load_rows(directory, manifest):
    data = directory / "pilot.jsonl"
    splits = directory / "splits.jsonl"
    if sha_file(data) != manifest["provenance"]["dataset_manifest_sha256"]:
        raise ValueError("Model dataset manifest checksum mismatch")
    if sha_file(splits) != manifest["provenance"]["split_manifest_sha256"]:
        raise ValueError("Model split manifest checksum mismatch")
    rows = [json.loads(line) for line in data.read_text().splitlines()]
    return [row for row in rows if not row["exclusion_reason"] and row["split"] != "quarantine"]


def test_intersection(rows_a, rows_b):
    """Only the same SHA256 admitted to BOTH untouched test partitions."""
    test_a = {r["sha256"]: r for r in rows_a if r["split"] == "test"}
    test_b = {r["sha256"]: r for r in rows_b if r["split"] == "test"}
    common = sorted(set(test_a) & set(test_b))
    for digest in common:
        if test_a[digest]["class_id"] != test_b[digest]["class_id"]:
            raise ValueError("Conflicting paired reference labels")
        if test_a[digest]["crop_id"] not in {"potato", "tomato"}:
            raise ValueError("Unexpected crop in paired PV comparison")
    train_a = {r["sha256"] for r in rows_a if r["split"] in {"train", "validation", "calibration"}}
    train_b = {r["sha256"] for r in rows_b if r["split"] in {"train", "validation", "calibration"}}
    if set(common) & (train_a | train_b):
        raise ValueError("Paired test contains non-test file in one model")
    return common


def metrics(records, class_ids, averaging_class_ids=None):
    index = {name: i for i, name in enumerate(class_ids)}
    matrix = np.zeros((len(index), len(index)), dtype=np.int64)
    for row in records:
        matrix[index[row["expected_class_id"]], index[row["predicted_class_id"]]] += 1
    per_class = {}
    for name, i in index.items():
        tp = int(matrix[i, i])
        support = int(matrix[i].sum())
        predicted = int(matrix[:, i].sum())
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[name] = dict(precision=precision, recall=recall, f1=f1, support=support)
    count = int(matrix.sum())
    averaging_class_ids = averaging_class_ids or class_ids
    return dict(
        images=count,
        groups=len({r["split_group_id"] for r in records}),
        accuracy=float(np.trace(matrix) / count) if count else None,
        macro_f1=float(np.mean([per_class[name]["f1"] for name in averaging_class_ids])) if count else None,
        macro_f1_class_ids=averaging_class_ids,
        class_order=class_ids,
        per_class=per_class,
        confusion_matrix=matrix.tolist(),
    )


def jpeg(image, quality=95, subsampling=0):
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=quality, subsampling=subsampling)
    return stream.getvalue()


def mobile_surrogate(source):
    """Offline PIL analogue: longest side2048/JPEG90; NOT Expo codec parity."""
    with Image.open(io.BytesIO(source)) as original:
        from PIL import ImageOps

        image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((2048, 2048), Image.Resampling.BILINEAR)
        return jpeg(image, 90, 2)


def transform(data, name):
    if name == "clean":
        return data
    with Image.open(io.BytesIO(data)) as original:
        image = original.convert("RGB")
        if name == "blur_radius4":
            image = image.filter(ImageFilter.GaussianBlur(4))
        elif name == "rotate90":
            image = image.transpose(Image.Transpose.ROTATE_90)
        elif name == "dark_0.15":
            image = ImageEnhance.Brightness(image).enhance(0.15)
        elif name == "jpeg_quality5":
            return jpeg(image, 5, 2)
        else:
            raise ValueError(f"Unknown transformation {name}")
        return jpeg(image)


class Model:
    def __init__(self, directory):
        self.directory = directory.resolve()
        self.bundle = validate_research_bundle(self.directory)
        self.manifest = self.bundle.manifest
        self.labels = self.manifest["labels"]
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        artifact = (self.directory / self.manifest["artifact"]["file"]).read_bytes()
        if sha_bytes(artifact) != self.manifest["artifact"]["sha256"]:
            raise ValueError("Artifact changed since validation")
        self.session = ort.InferenceSession(
            artifact, sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.public = ResearchOnnxPredictor(self.bundle)
        self.public.session = self.session  # same checked model, bounded evaluation thread setting
        self.rows = load_rows(self.directory, self.manifest)
        self.records = []

    def global_scores(self, content, *, offline=False):
        values = preprocess(
            content,
            self.manifest["preprocessing"],
            max_source_pixels=OFFLINE_SOURCE_LIMIT if offline else 20_000_000,
        )
        output = self.session.run(
            [self.manifest["output"]["name"]], {self.manifest["input"]["name"]: values}
        )[0][0]
        if not np.isfinite(output).all():
            raise ValueError("Nonfinite inference")
        scores = np.exp(output.astype(np.float64) - output.max())
        scores /= scores.sum()
        return scores

    def replay(self):
        for index, row in enumerate(
            sorted((r for r in self.rows if r["split"] == "test"), key=lambda r: r["sha256"])
        ):
            guard()
            path = ROOT / row["relative_path"]
            data = path.read_bytes()
            if sha_bytes(data) != row["sha256"]:
                raise ValueError("Test image checksum mismatch")
            scores = self.global_scores(data, offline=True)
            best = int(scores.argmax())
            try:
                validate_image_geometry(row["width_px"], row["height_px"])
                admitted = True
            except InputImageError:
                admitted = False
            self.records.append(
                dict(
                    sha256=row["sha256"],
                    image_id=row["image_id"],
                    split_group_id=row["split_group_id"],
                    expected_class_id=row["class_id"],
                    crop_id=row["crop_id"],
                    predicted_class_id=self.labels[best]["class_id"],
                    correct=self.labels[best]["class_id"] == row["class_id"],
                    top_score=float(scores[best]),
                    global_scores={
                        label["class_id"]: float(scores[i]) for i, label in enumerate(self.labels)
                    },
                    raw_serving_geometry_admitted=admitted,
                )
            )
            if index % 40 == 0:
                print(f"{self.manifest['version']} replay {index}", flush=True)
        return metrics(self.records, [label["class_id"] for label in self.labels])

    def public_case(self, content, crop):
        result = self.public.predict(content, crop)
        if (
            result["outcome"] != "inconclusive"
            or result["prediction"] is not None
            or "research_model_unvalidated" not in result["reason_codes"]
        ):
            raise AssertionError("Research abstention contract violated")
        scores = self.global_scores(content)
        by_class = {label["class_id"]: float(scores[i]) for i, label in enumerate(self.labels)}
        for candidate in result["candidates"]:
            if candidate["score_space"] != "global_joint" or candidate["score_kind"] != "model_score":
                raise AssertionError("Score contract violation")
            np.testing.assert_allclose(
                candidate["score"], by_class[candidate["class_id"]], rtol=0, atol=1e-12
            )
        return dict(
            outcome=result["outcome"],
            prediction=result["prediction"],
            reason_codes=result["reason_codes"],
            candidates=result["candidates"],
            selected_crop_mass=sum(
                float(scores[i]) for i, label in enumerate(self.labels) if label["crop_id"] == crop
            ),
            global_top_class_id=self.labels[int(scores.argmax())]["class_id"],
            global_top_score=float(scores.max()),
        )


def case_selection(model):
    selected = []
    for label in model.labels:
        eligible = sorted(
            (r for r in model.records if r["expected_class_id"] == label["class_id"]),
            key=lambda r: r["sha256"],
        )
        if eligible:
            selected.append(
                dict(
                    sha256=eligible[0]["sha256"],
                    class_id=label["class_id"],
                    selection="predeclared_min_sha_per_class",
                )
            )
    return selected


def control_images():
    rng = np.random.default_rng(17)
    checker = (np.indices((224, 224)).sum(axis=0) // 16 % 2 * 255).astype(np.uint8)
    return dict(
        uniform_gray=Image.new("RGB", (224, 224), (128, 128, 128)),
        uniform_green=Image.new("RGB", (224, 224), (20, 160, 40)),
        checkerboard=Image.fromarray(checker).convert("RGB"),
        seed17_noise=Image.fromarray(rng.integers(0, 256, (224, 224, 3), dtype=np.uint8)),
    )


def confusion_plot(report, path):
    names = report["class_order"]
    size = len(names)
    cell = 48
    margin = 270
    image = Image.new("RGB", (margin + size * cell, 100 + size * cell), "white")
    draw = ImageDraw.Draw(image)
    maximum = max(max(row) for row in report["confusion_matrix"]) or 1
    for i, name in enumerate(names):
        draw.text((2, 100 + i * cell + 15), name, fill="black")
        draw.text((margin + i * cell + 5, 60), str(i), fill="black")
        for j, count in enumerate(report["confusion_matrix"][i]):
            shade = 255 - int(180 * count / maximum)
            box = (margin + j * cell, 100 + i * cell, margin + (j + 1) * cell - 1, 100 + (i + 1) * cell - 1)
            draw.rectangle(box, fill=(shade, shade, 255), outline="gray")
            draw.text((box[0] + 15, box[1] + 15), str(count), fill="black")
    draw.text(
        (2, 5), "Rows=true source label; columns=raw global top1. Column IDs follow row order.", fill="black"
    )
    image.save(path)


def contact_sheet(items, path, cols=4):
    canvas = Image.new("RGB", (cols * 288, ((len(items) + cols - 1) // cols) * 340), "white")
    draw = ImageDraw.Draw(canvas)
    for i, item in enumerate(items):
        with Image.open(item["path"]) as original:
            image = original.convert("RGB")
            image.thumbnail((280, 224))
        x, y = i % cols * 288, i // cols * 340
        canvas.paste(image, (x, y))
        for line, text in enumerate(textwrap.wrap(item["caption"], 42)[:8]):
            draw.text((x + 2, y + 226 + line * 13), text, fill="black")
    canvas.save(path)


def build_cases(model, output):
    chosen = case_selection(model)
    rows = {r["sha256"]: r for r in model.rows}
    variants = []
    wrong = []
    normalisation = []
    gallery = []
    folder = output / "case_images"
    folder.mkdir(exist_ok=True)
    for seed in chosen:
        guard()
        row = rows[seed["sha256"]]
        raw = (ROOT / row["relative_path"]).read_bytes()
        try:
            api_bytes, _, _ = normalize_image(raw, 20_000_000)
            direct_api = dict(
                status="admitted",
                sha256=sha_bytes(api_bytes),
                result=model.public_case(api_bytes, row["crop_id"]),
            )
        except APIError as exc:
            direct_api = dict(status="rejected", code=exc.code)
        mobile = mobile_surrogate(raw)
        clean, width, height = normalize_image(mobile, 20_000_000)
        normalisation.append(
            dict(
                source_sha256=row["sha256"],
                original_width=row["width_px"],
                original_height=row["height_px"],
                direct_api=direct_api,
                mobile_surrogate_sha256=sha_bytes(mobile),
                normalized_sha256=sha_bytes(clean),
                normalized_width=width,
                normalized_height=height,
            )
        )
        for name in TRANSFORMS:
            transformed = transform(clean, name)
            normalized, _, _ = normalize_image(transformed, 20_000_000)
            result = model.public_case(normalized, row["crop_id"])
            top = result["candidates"][0]["class_id"]
            file = folder / f"{row['class_id']}-{name}-{row['sha256'][:8]}.jpg"
            file.write_bytes(normalized)
            case = dict(
                source_sha256=row["sha256"],
                class_id=row["class_id"],
                transform=name,
                selection=seed["selection"],
                input_sha256=sha_bytes(normalized),
                correct_selected_crop_top1=top == row["class_id"],
                result=result,
            )
            variants.append(case)
            gallery.append(
                dict(
                    path=file,
                    caption=f"{row['class_id']} / {name}; crop top1={top}; global score={result['candidates'][0]['score']:.3f}; inconclusive",
                )
            )
        crops = sorted({label["crop_id"] for label in model.labels})
        crop = crops[(crops.index(row["crop_id"]) + 1) % len(crops)]
        wrong.append(
            dict(
                source_sha256=row["sha256"],
                true_crop=row["crop_id"],
                selected_crop=crop,
                result=model.public_case(clean, crop),
            )
        )
    contact_sheet(gallery, output / "degraded_cases.png", 5)
    # Both successes and failures selected deterministically AFTER full replay;
    # explicitly illustrative, never the quantitative benchmark cohort.
    exemplars = []
    example_gallery = []
    for label in model.labels:
        for correct in (True, False):
            eligible = sorted(
                (
                    r
                    for r in model.records
                    if r["expected_class_id"] == label["class_id"] and r["correct"] == correct
                ),
                key=lambda r: r["sha256"],
            )
            if eligible:
                record = eligible[0]
                row = rows[record["sha256"]]
                file = folder / f"example-{row['sha256'][:12]}.jpg"
                file.write_bytes(mobile_surrogate((ROOT / row["relative_path"]).read_bytes()))
                exemplars.append(
                    dict(
                        **record, selection="posthoc_min_sha_success" if correct else "posthoc_min_sha_error"
                    )
                )
                gallery_item = dict(
                    path=file,
                    caption=f"{'SUCCESS' if correct else 'ERROR'} true={row['class_id']}; global top1={record['predicted_class_id']}; score={record['top_score']:.3f}; always inconclusive",
                )
                example_gallery.append(gallery_item)
    contact_sheet(example_gallery, output / "successes_and_errors.png")
    synthetic = []
    controls = []
    for name, image in control_images().items():
        content = jpeg(image)
        file = folder / f"control-{name}.jpg"
        file.write_bytes(content)
        for crop in sorted({label["crop_id"] for label in model.labels}):
            result = model.public_case(content, crop)
            synthetic.append(
                dict(
                    name=name,
                    crop_id=crop,
                    input_sha256=sha_bytes(content),
                    reference_label=None,
                    result=result,
                )
            )
        controls.append(
            dict(
                path=file,
                caption=f"SYNTHETIC CONTROL: {name}. No real OOD reference label or OOD-validation claim.",
            )
        )
    contact_sheet(controls, output / "synthetic_controls.png")
    bad = []
    skinny = io.BytesIO()
    Image.new("RGB", (10, 60000), "green").save(skinny, format="JPEG")
    for name, content in [("invalid_bytes", b"not an image"), ("skinny_jpeg", skinny.getvalue())]:
        try:
            model.public.predict(content, "wheat")
        except (InputImageError, OSError, ValueError) as exc:
            bad.append(dict(name=name, rejected=True, error_type=type(exc).__name__))
        else:
            raise AssertionError("Invalid image was not rejected")
    return dict(
        selection=chosen,
        normalisation=normalisation,
        variants=variants,
        wrong_crop=wrong,
        synthetic_controls=synthetic,
        invalid_inputs=bad,
        unsupported_crop=model.public.predict(jpeg(Image.new("RGB", (224, 224))), "maize"),
        illustrative_successes_and_errors=exemplars,
        caveat="Synthetic controls are not real OOD validation. Transformations are illustrative input perturbations, not independent plants or verified quality tests.",
    )


def provenance(model):
    return dict(
        version=model.manifest["version"],
        artifact_sha256=model.manifest["artifact"]["sha256"],
        manifest_sha256=sha_file(model.directory / "manifest.json"),
        data_manifest_sha256=sha_file(model.directory / "pilot.jsonl"),
        split_manifest_sha256=sha_file(model.directory / "splits.jsonl"),
        historical_evaluation_sha256=sha_file(model.directory / "evaluation.json"),
        preprocessing=model.manifest["preprocessing"],
        labels=model.labels,
    )


def run(args):
    start = time.monotonic()
    minimum = guard()
    output = ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    joint = Model(ROOT / args.joint)
    pv = Model(ROOT / args.pv)
    joint_metrics = joint.replay()
    pv_metrics = pv.replay()
    for model, actual in [(joint, joint_metrics), (pv, pv_metrics)]:
        expected = json.loads((model.directory / "evaluation.json").read_text())["classification"]["test"]
        if (
            actual["images"] != expected["images"]
            or not np.isclose(actual["macro_f1"], expected["macro_f1"], rtol=0, atol=1e-12)
            or actual["confusion_matrix"] != expected["confusion_matrix"]
        ):
            raise AssertionError("Historical heldout classification replay mismatch")
    common = test_intersection(joint.rows, pv.rows)
    jmap = {r["sha256"]: r for r in joint.records}
    pmap = {r["sha256"]: r for r in pv.records}
    paired_joint = [jmap[h] for h in common]
    paired_pv = [pmap[h] for h in common]
    pairs = dict(
        images=len(common),
        groups=len({jmap[h]["split_group_id"] for h in common}),
        selection_sha256=sha_bytes(canonical(common)),
        joint=metrics(
            paired_joint,
            [label["class_id"] for label in joint.labels],
            [label["class_id"] for label in pv.labels],
        ),
        pv=metrics(paired_pv, [label["class_id"] for label in pv.labels]),
        both_correct=sum(jmap[h]["correct"] and pmap[h]["correct"] for h in common),
        joint_only_correct=sum(jmap[h]["correct"] and not pmap[h]["correct"] for h in common),
        pv_only_correct=sum(not jmap[h]["correct"] and pmap[h]["correct"] for h in common),
        both_wrong=sum(not jmap[h]["correct"] and not pmap[h]["correct"] for h in common),
        caveat="Same heldout bytes, but joint has9 output classes and PV6; global softmax scales are not calibrated or directly comparable. Images within author leaf groups are correlated; no image-independent significance claim.",
    )
    cases = build_cases(joint, output)
    summary = {
        name: dict(
            images=len([v for v in cases["variants"] if v["transform"] == name]),
            correct=sum(v["correct_selected_crop_top1"] for v in cases["variants"] if v["transform"] == name),
        )
        for name in TRANSFORMS
    }
    confusion_plot(joint_metrics, output / "joint_confusion.png")
    confusion_plot(pv_metrics, output / "pv_confusion.png")
    report = dict(
        status="measured_research_cases_not_diagnostic_release",
        joint=joint_metrics,
        pv=pv_metrics,
        paired=pairs,
        variants_summary=summary,
        cases=cases,
        synthetic_control_count=len(cases["synthetic_controls"]),
        synthetic_max_global_score=max(v["result"]["global_top_score"] for v in cases["synthetic_controls"]),
        raw_joint_serving_geometry_rejected=sum(
            not r["raw_serving_geometry_admitted"] for r in joint.records
        ),
        provenance=dict(
            joint=provenance(joint),
            pv=provenance(pv),
            script_sha256=sha_file(Path(__file__)),
            runtime_sha256=sha_file(ROOT / "ml/runtime/agrovision_runtime/__init__.py"),
            api_normalizer_sha256=sha_file(ROOT / "server/agrovision/photos/service.py"),
            git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            code_dirty=bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain", "--", "ml/evaluation"], cwd=ROOT, text=True
                ).strip()
            ),
            joint_test_selection_sha256=sha_bytes(canonical(sorted(r["sha256"] for r in joint.records))),
            pv_test_selection_sha256=sha_bytes(canonical(sorted(r["sha256"] for r in pv.records))),
        ),
        environment=dict(
            python=sys.version,
            onnxruntime=ort.__version__,
            numpy=np.__version__,
            platform=platform.platform(),
            threads=2,
            provider="CPUExecutionProvider",
            offline_source_pixel_limit=OFFLINE_SOURCE_LIMIT,
            serving_source_pixel_limit=20_000_000,
            minimum_mem_available_gib=min(minimum, guard()),
            peak_process_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            elapsed_seconds=time.monotonic() - start,
        ),
        limitations=[
            "Wheat groups are dedup proxies, not verified independent biological plants/sessions.",
            "No Kazakhstan/source-heldout/real OOD/unknown-condition/quality-policy validation.",
            "Always abstains by research-mode design, not measured unknown detection.",
            "Degraded cohort is predeclared minimumSHA one per class (n9), not robust accuracy estimate.",
            "Posthoc success/error examples are labeled illustrative and not used for metrics.",
            "Mobile surrogate uses PIL2048/JPEG90 plus actual API normalization; not Expo device-codec parity.",
        ],
    )
    raw = dict(joint=joint.records, pv=pv.records, paired_sha256=common)
    (output / "raw_predictions.json").write_text(json.dumps(raw, indent=2))
    (output / "report.json").write_text(json.dumps(report, indent=2))
    compact = {k: v for k, v in report.items() if k != "cases"}
    compact["case_selection"] = cases["selection"]
    compact["invalid_inputs"] = cases["invalid_inputs"]
    compact["always_abstains_checked"] = True
    compact["raw_predictions_sha256"] = sha_file(output / "raw_predictions.json")
    compact["report_sha256"] = sha_file(output / "report.json")
    compact["plot_sha256"] = {p.name: sha_file(p) for p in sorted(output.glob("*.png"))}
    if args.publish:
        destination = ROOT / "docs/evaluation"
        destination.mkdir(exist_ok=True)
        (destination / "MEASURED_CASES.json").write_text(json.dumps(compact, indent=2))
    print(
        json.dumps(
            {
                k: v
                for k, v in compact.items()
                if k
                in [
                    "variants_summary",
                    "synthetic_max_global_score",
                    "environment",
                    "raw_joint_serving_geometry_rejected",
                ]
            },
            indent=2,
        )
    )
    print("Paired", json.dumps({k: v for k, v in pairs.items() if k not in ["joint", "pv"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--joint", default="artifacts/pilot-joint-efficientnet-b0-seed17")
    parser.add_argument("--pv", default="artifacts/pilot-pv-efficientnet-b0-seed17")
    parser.add_argument("--output", default="artifacts/evaluation/model-cases-v1")
    parser.add_argument("--publish", action="store_true")
    run(parser.parse_args())
