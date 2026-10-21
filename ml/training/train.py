"""Reproducible frozen EfficientNet-B0 head baseline; RESEARCH ONLY.

No release policy is guessed. Output cannot activate the production runtime.
This bounded MVP experiment uses deterministic center-crop feature extraction,
then trains the classification head; it is not the full planned finetune study.
"""

import argparse
import copy
import hashlib
import importlib.metadata
import json
import platform
import random
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from torch import nn
from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/runtime"))
from agrovision_runtime import preprocess  # noqa: E402

PREPROCESSING = dict(
    version="common-rgb224-v1",
    resize_shorter_side=256,
    center_crop=224,
    interpolation="bilinear",
    color_mode="RGB",
    apply_exif_orientation=True,
    mean=[0.485, 0.456, 0.406],
    std=[0.229, 0.224, 0.225],
)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def available_memory_gib():
    fields = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    return int(fields["MemAvailable"].split()[0]) / 1024**2


def guard_memory(minimum_gib):
    available = available_memory_gib()
    if available < minimum_gib:
        raise RuntimeError(f"RAM guard: {available:.2f} GiB available, require {minimum_gib:.2f} GiB")
    return available


def main(args):
    started = time.monotonic()
    minimum_available = guard_memory(args.min_available_gib)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    random.seed(17)
    np.random.seed(17)
    torch.manual_seed(17)
    torch.cuda.manual_seed_all(17)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    output = ROOT / "artifacts" / args.run
    output.mkdir(parents=True, exist_ok=True)
    manifests = ROOT / "data/manifests"
    rows = [json.loads(line) for line in (manifests / "pilot.jsonl").read_text().splitlines()]
    rows = [r for r in rows if not r["exclusion_reason"] and r["split"] != "quarantine"]
    groups = {}
    for r in rows:
        if r["split_group_id"] in groups and groups[r["split_group_id"]] != r["split"]:
            raise ValueError("split group leakage")
        groups[r["split_group_id"]] = r["split"]
    labels = json.loads((manifests / "labels.json").read_text())
    audit = json.loads((manifests / "audit.json").read_text())
    for name in ("pilot.jsonl", "splits.jsonl", "labels.json", "audit.json"):
        shutil.copyfile(manifests / name, output / name)
    label_ids = {label["class_id"]: i for i, label in enumerate(labels)}
    model = efficientnet_b0(weights=EfficientNet_B0_Weights.IMAGENET1K_V1)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(labels))
    for p in model.parameters():
        p.requires_grad = False
    for p in model.classifier.parameters():
        p.requires_grad = True
    model.to(device).eval()
    parity_indices = set(np.linspace(0, len(rows) - 1, min(100, len(rows)), dtype=int).tolist())
    features = []
    tensors = []
    targets = []
    batch_size = args.batch_size
    torch.cuda.reset_peak_memory_stats() if device.type == "cuda" else None
    feature_start = time.monotonic()
    for start in range(0, len(rows), batch_size):
        minimum_available = min(minimum_available, guard_memory(args.min_available_gib))
        batch = rows[start : start + batch_size]
        batch_np = np.concatenate(
            [preprocess((ROOT / r["relative_path"]).read_bytes(), PREPROCESSING) for r in batch]
        )
        tensor = torch.from_numpy(batch_np)
        with torch.no_grad():
            encoded = model.avgpool(model.features(tensor.to(device))).flatten(1)
        features.append(encoded.cpu())
        targets.extend(label_ids[r["class_id"]] for r in batch)
        tensors.extend(
            value for index, value in enumerate(tensor.unbind(0), start=start) if index in parity_indices
        )
        if start % 80 == 0:
            print(f"features {start}/{len(rows)}", flush=True)
    x = torch.cat(features).to(device)
    y = torch.tensor(targets, device=device)
    masks = {
        name: torch.tensor([r["split"] == name for r in rows], device=device)
        for name in ["train", "validation", "calibration", "test"]
    }
    feature_seconds = time.monotonic() - feature_start
    optimizer = torch.optim.AdamW(model.classifier.parameters(), lr=0.001, weight_decay=0.0001)
    history = []
    best_f1 = -1.0
    best_state = None
    updates = 0
    train_indices = torch.where(masks["train"])[0]
    if not len(train_indices) or not masks["validation"].sum():
        raise ValueError("empty training/validation partition")
    for epoch in range(args.epochs):
        minimum_available = min(minimum_available, guard_memory(args.min_available_gib))
        model.classifier.train()
        losses = []
        shuffled = train_indices[torch.randperm(len(train_indices), device=device)]
        for chunk in shuffled.split(32):
            optimizer.zero_grad(set_to_none=True)
            logits = model.classifier(x[chunk])
            loss = nn.functional.cross_entropy(logits, y[chunk])
            if not torch.isfinite(loss):
                raise ValueError("nonfinite loss")
            loss.backward()
            optimizer.step()
            updates += 1
            losses.append(float(loss.detach()))
        model.classifier.eval()
        with torch.no_grad():
            pred = model.classifier(x[masks["validation"]]).argmax(1).cpu().numpy()
            truth = y[masks["validation"]].cpu().numpy()
        score = float(
            f1_score(truth, pred, labels=list(range(len(labels))), average="macro", zero_division=0)
        )
        record = dict(epoch=epoch + 1, train_loss=float(np.mean(losses)), validation_macro_f1=score)
        history.append(record)
        print(json.dumps(record), flush=True)
        if score > best_f1:
            best_f1 = score
            best_state = copy.deepcopy(model.state_dict())
        if time.monotonic() - started > args.max_minutes * 60:
            break
    model.load_state_dict(best_state)
    model.eval()
    torch.save(
        {
            "model": best_state,
            "labels": labels,
            "preprocessing": PREPROCESSING,
            "seed": 17,
            "history": history,
        },
        output / "checkpoint.pt",
    )
    restored = efficientnet_b0(weights=None)
    restored.classifier[1] = nn.Linear(restored.classifier[1].in_features, len(labels))
    restored.load_state_dict(
        torch.load(output / "checkpoint.pt", map_location="cpu", weights_only=True)["model"]
    )
    restored.eval()
    reports = {}
    for split, mask in masks.items():
        if not mask.sum():
            continue
        with torch.no_grad():
            pred = model.classifier(x[mask]).argmax(1).cpu().numpy()
            truth = y[mask].cpu().numpy()
        reports[split] = dict(
            images=int(mask.sum()),
            groups=len({r["split_group_id"] for r in rows if r["split"] == split}),
            macro_f1=float(
                f1_score(truth, pred, labels=list(range(len(labels))), average="macro", zero_division=0)
            ),
            accuracy=float(accuracy_score(truth, pred)),
            classification_report=classification_report(
                truth,
                pred,
                labels=list(range(len(labels))),
                target_names=list(label_ids),
                output_dict=True,
                zero_division=0,
            ),
            confusion_matrix=confusion_matrix(truth, pred, labels=list(range(len(labels)))).tolist(),
        )
    artifact = output / "model.onnx"
    torch.onnx.export(
        restored,
        tensors[0][None],
        str(artifact),
        input_names=["images"],
        output_names=["scores"],
        opset_version=17,
        dynamo=False,
    )
    digest = hashlib.sha256(json.dumps(labels, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    preprocessing_digest = hashlib.sha256(
        json.dumps(PREPROCESSING, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    exported = onnx.load(artifact)
    onnx.helper.set_model_props(
        exported,
        {
            "labels_sha256": digest,
            "preprocessing_version": PREPROCESSING["version"],
            "preprocessing_sha256": preprocessing_digest,
        },
    )
    onnx.checker.check_model(exported)
    onnx.save(exported, artifact)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    cold_start = time.perf_counter()
    session = ort.InferenceSession(str(artifact), sess_options=options, providers=["CPUExecutionProvider"])
    cold_start_ms = (time.perf_counter() - cold_start) * 1000
    errors = []
    top1_changes = 0
    for tensor in tensors:
        minimum_available = min(minimum_available, guard_memory(args.min_available_gib))
        with torch.no_grad():
            expected = restored(tensor[None]).numpy()
        actual = session.run(["scores"], {"images": tensor[None].numpy()})[0]
        np.testing.assert_allclose(actual, expected, rtol=0.001, atol=0.0001)
        errors.append(float(np.abs(actual - expected).max()))
        top1_changes += int(actual.argmax() != expected.argmax())
    parity = dict(
        images=len(tensors),
        max_absolute_logit_error=max(errors),
        top1_changes=top1_changes,
        rtol=0.001,
        atol=0.0001,
        passed=True,
    )
    bench = tensors[0][None].numpy()
    for _ in range(20):
        session.run(["scores"], {"images": bench})
    durations = []
    for _ in range(200):
        t = time.perf_counter()
        session.run(["scores"], {"images": bench})
        durations.append((time.perf_counter() - t) * 1000)
    image_bytes = (ROOT / rows[0]["relative_path"]).read_bytes()
    end_to_end = []
    for _ in range(200):
        t = time.perf_counter()
        values = preprocess(image_bytes, PREPROCESSING)
        session.run(["scores"], {"images": values})
        end_to_end.append((time.perf_counter() - t) * 1000)
    cpu_name = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        platform.processor(),
    )
    benchmark = dict(
        model_only_p50_ms=float(np.percentile(durations, 50)),
        model_only_p95_ms=float(np.percentile(durations, 95)),
        warmup_iterations=20,
        measured_iterations=200,
        intra_op_threads=4,
        inter_op_threads=1,
        cpu=cpu_name,
        cold_start_ms=cold_start_ms,
        end_to_end_p50_ms=float(np.percentile(end_to_end, 50)),
        end_to_end_p95_ms=float(np.percentile(end_to_end, 95)),
        peak_process_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        platform=platform.platform(),
        end_to_end_input={
            "width_px": rows[0]["width_px"],
            "height_px": rows[0]["height_px"],
            "bytes": len(image_bytes),
            "source_dataset": rows[0]["source_dataset"],
            "sha256": rows[0]["sha256"],
        },
        artifact_bytes=artifact.stat().st_size,
    )
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except subprocess.CalledProcessError:
        commit = "uncommitted-initial-development"
    code_dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain", "--", "ml"], cwd=ROOT, text=True).strip()
    )
    code_snapshot = {
        str(path.relative_to(ROOT)): sha(path)
        for path in sorted((ROOT / "ml").rglob("*.py"))
        if ".venv" not in path.parts
    }
    code_snapshot_sha256 = hashlib.sha256(
        json.dumps(code_snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest = dict(
        version=args.run,
        artifact={"file": "model.onnx", "sha256": sha(artifact)},
        labels=labels,
        labels_sha256=digest,
        input={"name": "images", "shape": [1, 3, 224, 224], "dtype": "float32"},
        output={"name": "scores", "shape": [1, len(labels)], "semantics": "logits"},
        preprocessing=PREPROCESSING,
        preprocessing_sha256=preprocessing_digest,
        score_space="global_joint",
        policy={
            "version": "pending",
            "status": "unvalidated",
            "joint_score_threshold": None,
            "selected_crop_mass_threshold": None,
        },
        calibration={"kind": "none"},
        provenance={
            "dataset_manifest_sha256": audit["dataset_manifest_sha256"],
            "split_manifest_sha256": audit["split_manifest_sha256"],
            "code_commit": commit,
            "code_dirty": code_dirty,
            "code_snapshot_sha256": code_snapshot_sha256,
            "evaluation_report": "evaluation.json",
        },
        release_status="research",
    )
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    weights_file = Path(torch.hub.get_dir()) / "checkpoints/efficientnet_b0_rwightman-7f5810bc.pth"
    result = dict(
        run=args.run,
        status="research_not_diagnostic_release",
        architecture="torchvision.efficientnet_b0",
        code_commit=commit,
        code_dirty=code_dirty,
        code_snapshot_sha256=code_snapshot_sha256,
        code_snapshot=code_snapshot,
        training_script_sha256=sha(Path(__file__)),
        runtime_script_sha256=sha(ROOT / "ml/runtime/agrovision_runtime/__init__.py"),
        training="frozen pretrained ImageNet backbone; classification head AdamW, no image augmentation",
        pretrained_weights="EfficientNet_B0_Weights.IMAGENET1K_V1",
        pretrained_weights_sha256=sha(weights_file),
        dependencies={
            name: importlib.metadata.version(name)
            for name in ("torch", "torchvision", "numpy", "pillow", "onnx", "onnxruntime", "scikit-learn")
        },
        training_lockfile_sha256=sha(ROOT / "ml/training/uv.lock"),
        torch=torch.__version__,
        cuda=torch.version.cuda,
        device=str(device),
        gpu=torch.cuda.get_device_name() if device.type == "cuda" else None,
        gpu_compute_capability=list(torch.cuda.get_device_capability()) if device.type == "cuda" else None,
        gpu_total_vram_mib=torch.cuda.get_device_properties(device).total_memory / 1024**2
        if device.type == "cuda"
        else None,
        minimum_mem_available_gib=minimum_available,
        memory_guard_minimum_gib=args.min_available_gib,
        dataloader_workers=0,
        physical_feature_batch=batch_size,
        head_batch=32,
        optimizer_updates=updates,
        seed=17,
        epochs=len(history),
        peak_cuda_allocated_mib=torch.cuda.max_memory_allocated() / 1024**2
        if device.type == "cuda"
        else None,
        feature_extraction_seconds=feature_seconds,
        total_seconds=time.monotonic() - started,
        history=history,
        classification=reports,
        parity=parity,
        cpu_benchmark=benchmark,
        limitations=[
            "One seed only; no seed variation/confidence intervals",
            "No local Kazakhstan, source-held-out or OOD evaluation",
            "D05 biological independence unverified",
            "No calibrated rejection thresholds; NEVER activate as diagnostic release",
            "Legacy torch ONNX exporter used, opset17; validated parity is recorded",
            "Frozen deterministic feature baseline, no partial finetuning or augmentations",
        ],
    )
    (output / "evaluation.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k not in ["history", "classification"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="pilot-efficientnet-b0-seed17")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-minutes", type=float, default=25)
    parser.add_argument("--min-available-gib", type=float, default=3.0)
    main(parser.parse_args())
