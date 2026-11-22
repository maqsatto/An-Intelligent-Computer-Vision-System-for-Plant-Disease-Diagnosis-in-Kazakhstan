"""Per-crop breakdown of a bundle on the held-out sets (reads saved logits; no GPU needed)."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def main(bundle="bundle_final", pack="pack_w2"):
    manifest = json.loads((ROOT / bundle / "manifest.json").read_text())
    classes = manifest["classes"]
    other = manifest["thresholds"]["other_class"]
    t_other = manifest["thresholds"]["other_threshold"]
    runs = [m["file"].removesuffix(".onnx") for m in manifest["models"]]
    temps = [m["temperature"] for m in manifest["models"]]
    cid = {c: i for i, c in enumerate(classes)}
    lines = []

    def predict(logits_list):
        p = np.mean([softmax(z / t) for z, t in zip(logits_list, temps, strict=True)], axis=0)
        diag = p.copy()
        diag[:, other] = 0
        return p, diag.argmax(1)

    # PlantWild test half
    meta = pd.read_csv(ROOT / "data/pack_ext/meta.csv")
    meta = meta[~meta.dup_of_train].reset_index(drop=True)
    y = np.array([cid.get(x, -1) for x in meta.label])
    sel = ((meta.half == "test") & (meta.kind == "in_scope") & (y >= 0)).values
    p, pred = predict([np.load(ROOT / "runs" / r / "ext_logits.npy").astype(np.float32) for r in runs])
    ok = (pred == y) & (p[:, other] < t_other)
    crops = np.array([c.split("__")[0] for c in classes])
    lines += ["### PlantWild held-out half (in-the-wild web photos), per crop", "", "| Crop | Images | End-to-end acc | Crop identified | Rejected as non-target |", "|---|---:|---:|---:|---:|"]
    for crop in sorted(set(crops) - {"other"}):
        m = sel & (crops[y] == crop)
        if m.sum() == 0:
            continue
        lines.append(f"| {crop} | {m.sum()} | {ok[m].mean():.3f} | {(crops[pred[m]] == crop).mean():.3f} | {(p[m][:, other] >= t_other).mean():.3f} |")
    lines += ["", "Per condition (wheat):", "", "| Condition | Images | Acc |", "|---|---:|---:|"]
    for c in classes:
        if c.startswith("wheat__"):
            m = sel & (y == cid[c])
            if m.sum():
                lines.append(f"| {c.split('__')[1]} | {m.sum()} | {ok[m].mean():.3f} |")
    # PlantDoc field_test
    base = pd.read_csv(ROOT / "data" / pack / "meta.csv")
    for name, split in (("PlantDoc field_test (real field photographs)", "field_test"), ("Held-out test split of the training sources", "test")):
        d = np.load(ROOT / "runs" / runs[0] / f"logits_{split}.npz")
        lg = [np.load(ROOT / "runs" / r / f"logits_{split}.npz")["logits"].astype(np.float32) for r in runs]
        p2, pred2 = predict(lg)
        y2 = d["y"]
        crop2 = base.set_index("idx").loc[d["idx"]].crop.values
        ok2 = pred2 == y2
        lines += ["", f"### {name}, per crop", "", "| Crop | Images | Acc |", "|---|---:|---:|"]
        for crop in sorted(set(crop2) - {"other"}):
            m = crop2 == crop
            lines.append(f"| {crop} | {m.sum()} | {ok2[m].mean():.3f} |")
    text = "\n".join(lines)
    (ROOT / bundle / "per_crop.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main(*sys.argv[1:])
