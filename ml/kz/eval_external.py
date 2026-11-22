"""Evaluate run checkpoints on the external PlantWild field set (dedup'd against training)."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import timm
import torch
from sklearn.metrics import accuracy_score, f1_score

ROOT = Path(__file__).resolve().parents[2]


@torch.no_grad()
def logits_for(run, images, idx, tta=False):
    rep = json.loads((run / "report.json").read_text())
    classes = json.loads((run / "classes.json").read_text())
    kwargs = {"img_size": 224} if "dinov2" in rep["model"] else {}
    model = timm.create_model(rep["model"], pretrained=False, num_classes=len(classes), **kwargs)
    model.load_state_dict(torch.load(run / "best.pt", map_location="cpu"))
    model = model.cuda().eval()
    mean = torch.tensor(rep["mean"], device="cuda").view(1, 3, 1, 1)
    std = torch.tensor(rep["std"], device="cuda").view(1, 3, 1, 1)
    out = []
    for i in range(0, len(idx), 128):
        x = torch.from_numpy(images[idx[i : i + 128]]).cuda().permute(0, 3, 1, 2).float() / 255
        x = x[:, :, 16:240, 16:240]
        x = (x - mean) / std
        with torch.autocast("cuda", dtype=torch.bfloat16):
            lg = model(x).float()
            if tta:
                lg = (lg.softmax(1) + model(x.flip(3)).float().softmax(1)).log()
        out.append(lg.cpu())
    return torch.cat(out).numpy(), classes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    meta = pd.read_csv(ROOT / "data/pack_ext/meta.csv")
    meta = meta[~meta.dup_of_train].reset_index(drop=True)
    images = np.load(ROOT / "data/pack_ext/images.npy", mmap_mode="r")
    idx = meta.idx.values
    test = (meta.half == "test").values
    results = {}
    for name in a.runs:
        run = ROOT / "runs" / name
        lg, classes = logits_for(run, images, idx)
        np.save(run / "ext_logits.npy", lg.astype(np.float16))  # all non-duplicate rows (dev+test), meta order
        cid = {c: i for i, c in enumerate(classes)}
        pred = lg.argmax(1)
        y = np.array([cid.get(label, -1) for label in meta.label])
        other = cid["other__non_target"]
        kind = meta.kind.values
        crops = np.array([c.split("__")[0] for c in classes])

        def block(mask):
            inscope = mask & (kind == "in_scope") & (y >= 0)
            masked = lg.copy()
            for row in np.where(inscope)[0]:
                masked[row, crops != classes[y[row]].split("__")[0]] = -1e9
            others = mask & (kind == "other_plant")
            return dict(
                n_in_scope=int(inscope.sum()),
                acc=float(accuracy_score(y[inscope], pred[inscope])),
                acc_with_crop_hint=float((masked[inscope].argmax(1) == y[inscope]).mean()),
                macro_f1=float(f1_score(y[inscope], pred[inscope], average="macro")),
                crop_acc=float(np.mean([crops[p] == crops[t] for p, t in zip(pred[inscope], y[inscope], strict=True)])),
                n_other=int(others.sum()),
                other_rejected=float((pred[others] == other).mean()),
                in_scope_wrongly_rejected=float((pred[inscope] == other).mean()),
            )

        res = block(test)  # headline: held-out PlantWild test half, every class this model supports
        res["legacy_classes"] = block(test & meta.legacy.values)  # the 23 original classes only (comparable across models)
        results[name] = res
        print(name, json.dumps({k: res[k] for k in ("n_in_scope", "acc", "acc_with_crop_hint", "crop_acc", "other_rejected")}), "legacy acc",
              round(res["legacy_classes"]["acc"], 4), flush=True)
        (run / "external.json").write_text(json.dumps(res, indent=1))
    return results


if __name__ == "__main__":
    main()
