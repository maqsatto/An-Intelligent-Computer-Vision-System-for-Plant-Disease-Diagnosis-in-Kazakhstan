"""Export trained checkpoint(s) to an ONNX bundle for the web demo.

* normalisation is baked into the graph (input: float32 NCHW RGB in [0,1], 224x224)
* temperature scaling is fitted on the *val* split only
* decision thresholds are chosen on *val* only; test / field_test are then reported unchanged
* PyTorch <-> ONNX parity is checked on real validation images
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import timm
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[2]


def cam_weights(model):
    """Class-activation-map weights for GAP(+LayerNorm)+linear CNN heads; None for other families."""
    if hasattr(model, "classifier") and isinstance(model.classifier, nn.Linear) and hasattr(model, "conv_head"):
        return model.classifier.weight.detach()
    head = getattr(model, "head", None)
    if head is not None and hasattr(head, "fc") and isinstance(head.fc, nn.Linear) and hasattr(model, "stages"):
        w = head.fc.weight.detach()
        norm = getattr(head, "norm", None)
        if norm is not None and getattr(norm, "weight", None) is not None:
            w = w * norm.weight.detach().view(1, -1)
        return w
    return None


class Wrapped(nn.Module):
    def __init__(self, model, mean, std, with_cam=False):
        super().__init__()
        self.with_cam = with_cam and cam_weights(model) is not None
        if self.with_cam:
            self.register_buffer("cam_w", cam_weights(model))
        self.model = model
        self.register_buffer("mean", torch.tensor(mean).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(std).view(1, 3, 1, 1))

    def forward(self, x):
        z = (x - self.mean) / self.std
        if not self.with_cam:
            return self.model(z)
        f = self.model.forward_features(z)
        logits = self.model.forward_head(f)
        return logits, torch.einsum("kc,bchw->bkhw", self.cam_w, f)


def fit_temperature(logits, y):
    z = torch.tensor(logits, dtype=torch.float32)
    t = torch.tensor(y)
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = nn.functional.cross_entropy(z / log_t.exp(), t)
        loss.backward()
        return loss

    opt.step(closure)
    return float(log_t.exp())


def softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def load_logits(run, split):
    d = np.load(run / f"logits_{split}.npz")
    return d["idx"], d["logits"].astype(np.float32), d["y"]


def export_one(run: Path, out: Path, name: str):
    report = json.loads((run / "report.json").read_text())
    classes = json.loads((run / "classes.json").read_text())
    kwargs = {"img_size": 224} if "dinov2" in report["model"] else {}
    model = timm.create_model(report["model"], pretrained=False, num_classes=len(classes), **kwargs)
    model.load_state_dict(torch.load(run / "best.pt", map_location="cpu"))
    model.eval()
    wrapped = Wrapped(model, report["mean"], report["std"], with_cam=True).eval()
    dummy = torch.rand(2, 3, 224, 224)
    path = out / f"{name}.onnx"
    torch.onnx.export(
        wrapped, dummy, str(path), input_names=["image"],
        output_names=["logits", "cam"] if wrapped.with_cam else ["logits"],
        dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}, **({"cam": {0: "batch"}} if wrapped.with_cam else {})},
        opset_version=17, dynamo=False,
    )
    # parity on real validation photos
    import onnxruntime as ort

    meta = pd.read_csv(ROOT / "data/pack/meta.csv")
    images = np.load(ROOT / "data/pack/images.npy", mmap_mode="r")
    idx = np.sort(meta[meta.split == "val"].idx.values[::40][:64])
    x = np.ascontiguousarray(images[idx][:, 16:240, 16:240, :]).astype(np.float32).transpose(0, 3, 1, 2) / 255.0
    with torch.no_grad():
        ref = wrapped(torch.from_numpy(x))
        ref = (ref[0] if wrapped.with_cam else ref).numpy()
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    got = session.run(None, {"image": x})[0]
    parity = dict(cam=bool(wrapped.with_cam), max_abs_logit_diff=float(np.abs(ref - got).max()), top1_changes=int((ref.argmax(1) != got.argmax(1)).sum()), images=len(idx))
    return report, classes, parity, path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True, help="run directory names under runs/ (ensemble members)")
    ap.add_argument("--out", default="bundle")
    ap.add_argument("--name", default="AgroVision KZ")
    ap.add_argument("--version", default="1.0")
    ap.add_argument("--calib", choices=["val+wilddev", "val"], default="val+wilddev",
                    help="val+wilddev for models that never saw PlantWild; val for models trained on the PlantWild dev half")
    ap.add_argument("--trained-on", default=None)
    ap.add_argument("--pack", default="pack", help="pack the runs were trained on (pack | pack_w)")
    a = ap.parse_args()
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    parities, reports = [], []
    classes = None
    for r in a.runs:
        run = ROOT / "runs" / r
        report, cls, parity, path = export_one(run, out, r)
        classes = classes or cls
        assert classes == cls
        reports.append(report)
        parities.append(parity)
    other = classes.index("other__non_target") if "other__non_target" in classes else -1
    cid = {c: i for i, c in enumerate(classes)}
    # --- data for calibration: val + external dev half (PlantWild rows with even index); test = odd rows
    ext_meta = pd.read_csv(ROOT / "data/pack_ext/meta.csv")
    ext_meta = ext_meta[~ext_meta.dup_of_train].reset_index(drop=True)
    ext_y = np.array([cid.get(x, -1) for x in ext_meta.label])
    ext_dev = (ext_meta.half.values == "dev")
    ext_logits = [np.load(ROOT / "runs" / r / "ext_logits.npy").astype(np.float32) for r in a.runs]
    val = [load_logits(ROOT / "runs" / r, "val") for r in a.runs]
    yv = val[0][2]
    temps = []
    use_dev = a.calib == "val+wilddev"
    for k in range(len(a.runs)):
        z = np.concatenate([val[k][1], ext_logits[k][ext_dev & (ext_y >= 0)]]) if use_dev else val[k][1]
        y = np.concatenate([yv, ext_y[ext_dev & (ext_y >= 0)]]) if use_dev else yv
        temps.append(fit_temperature(z, y))
    probs = {"val": (np.mean([softmax(v[1] / t) for v, t in zip(val, temps)], axis=0), yv)}
    for split in ("test", "field_test"):
        ls = [load_logits(ROOT / "runs" / r, split) for r in a.runs]
        probs[split] = (np.mean([softmax(v[1] / t) for v, t in zip(ls, temps)], axis=0), ls[0][2])
    pe = np.mean([softmax(z / t) for z, t in zip(ext_logits, temps)], axis=0)
    dev_ok = ext_dev & (ext_y >= 0)
    test_ok = ~ext_dev & (ext_y >= 0)
    probs["ext_dev"] = (pe[dev_ok], ext_y[dev_ok])
    probs["ext_test"] = (pe[test_ok], ext_y[test_ok])
    ext_kind = ext_meta.kind.values
    from sklearn.metrics import accuracy_score, f1_score

    def decide(p, t):
        """Mirror of webapp.inference.Classifier.predict (no crop hint)."""
        diag = p.copy()
        if other >= 0:
            diag[:, other] = 0.0
        order = np.sort(diag, axis=1)
        p1, p2 = order[:, -1], order[:, -2]
        p_other = p[:, other] if other >= 0 else np.zeros(len(p))
        pred = diag.argmax(1)
        unrec = p_other >= t.get("other_threshold", 0.5)
        conf = ~unrec & (p1 >= t["confident"]) & ((p1 - p2) >= t["margin"])
        unc = ~unrec & ~conf & (p1 >= t["uncertain"])
        return pred, np.where(conf, 2, np.where(unc, 1, 0))

    # decision thresholds are tuned on field-like photos only (PlantWild dev half / PlantWild val part)
    if use_dev:
        dev_p, dev_y = probs["ext_dev"]
    else:
        src = pd.read_csv(ROOT / "data" / a.pack / "meta.csv").set_index("idx").source
        wild_val = (src.loc[val[0][0]].values == "plantwild")
        dev_p, dev_y = probs["val"][0][wild_val], probs["val"][1][wild_val]
    print("threshold dev set:", len(dev_y), flush=True)

    def pick(target, lo, hi, level):
        for c in np.arange(lo, hi, 0.01):
            t = dict(confident=c, uncertain=c, margin=0.1, **thresholds_probe)
            pred, status = decide(dev_p, t)
            m = status >= level
            if m.sum() >= 120 and (pred[m] == dev_y[m]).mean() >= target:
                return float(round(c, 2))
        return float(hi)

    # rejection-class threshold: balance "other plant rejected" against "target leaf wrongly rejected" on the dev set
    if other >= 0:
        in_dev = dev_y != other
        best_t, best_score = 0.5, -1.0
        for cand in np.arange(0.3, 0.96, 0.02):
            rejected = dev_p[:, other] >= cand
            score = 0.5 * rejected[~in_dev].mean() + 0.5 * (1 - rejected[in_dev].mean())
            if score > best_score:
                best_t, best_score = float(round(cand, 2)), float(score)
        other_t = best_t
    else:
        other_t = 0.5
    thresholds_probe = dict(other_threshold=other_t)
    conf_t = pick(0.90, 0.5, 0.98, 2)
    unc_t = min(pick(0.65, 0.3, 0.9, 1), conf_t - 0.1)
    thresholds = dict(confident=conf_t, uncertain=max(unc_t, 0.3), margin=0.1, evidence=0.0, evidence_low=0.0, other_class=other, other_threshold=other_t)

    def metrics(split):
        p, y = probs[split]
        pred = p.argmax(1)
        res = dict(n=int(len(y)), acc=float(accuracy_score(y, pred)), macro_f1=float(f1_score(y, pred, average="macro")))
        d_pred, status = decide(p, thresholds)
        acc_mask = status == 2
        res["confident_coverage"] = float(acc_mask.mean())
        res["confident_accuracy"] = float((d_pred[acc_mask] == y[acc_mask]).mean()) if acc_mask.any() else None
        return res

    metrics_out = {k: metrics(k) for k in ("val", "test", "field_test")}
    p, y = probs["ext_test"]
    kind = ext_kind[test_ok]
    ins = kind == "in_scope"
    pred = p.argmax(1)
    d_pred, status = decide(p, thresholds)
    metrics_out["wild_test"] = dict(
        n=int(ins.sum()), acc=float(accuracy_score(y[ins], pred[ins])), macro_f1=float(f1_score(y[ins], pred[ins], average="macro")),
        crop_acc=float(np.mean([classes[a_].split("__")[0] == classes[b_].split("__")[0] for a_, b_ in zip(pred[ins], y[ins])])),
        other_plants_rejected=float((p[~ins][:, other] >= other_t).mean()), other_n=int((~ins).sum()),
        in_scope_wrongly_rejected=float((p[ins][:, other] >= other_t).mean()),
        accepted_accuracy=float((d_pred[ins][p[ins][:, other] < other_t] == y[ins][p[ins][:, other] < other_t]).mean()),
        end_to_end_accuracy=float(((d_pred[ins] == y[ins]) & (p[ins][:, other] < other_t)).mean()),
        confident_coverage=float((status[ins] == 2).mean()),
        confident_accuracy=float((d_pred[ins][status[ins] == 2] == y[ins][status[ins] == 2]).mean()) if (status[ins] == 2).any() else None,
        false_confident_rate_on_other_plants=float((status[~ins] == 2).mean()),
    )

    summary = ROOT / "runs/benchmark_summary.json"
    benchmark = []
    if summary.exists():
        for row in json.loads(summary.read_text()):
            benchmark.append({k: row.get(k) for k in ("run", "model", "variant", "params_m", "test_f1", "field_acc", "wild_acc", "wild_legacy", "wild_hint", "wild_trained")})
    wt = metrics_out["wild_test"]
    limitations = [
        "Обучено на открытых наборах (PlantVillage, PlantDoc, JIC, Holeta, подсолнечник, огурец, PlantWild); снимков из Казахстана нет — применимость к казахстанским полям не доказана.",
        f"На независимых «диких» фото из интернета (не участвовали в обучении) точность {wt['acc']*100:.0f}% по всем состояниям и {wt['crop_acc']*100:.0f}% по культуре; на лабораторно-подобных фото ≈{metrics_out['test']['acc']*100:.0f}%.",
        "Не поддерживаются ячмень, сахарная свёкла, лён, рапс, бобовые и другие культуры; неподдерживаемые растения и не-растения должны отклоняться, но это не гарантировано.",
        "Анализируется один лист при хорошем освещении; несколько болезней на одном листе и ранние стадии распознаются хуже.",
        "Результат — гипотеза для осмотра; не заменяет агронома и лабораторный анализ.",
    ]
    manifest = dict(
        benchmark=benchmark, limitations=limitations,
        name=a.name, version=a.version,
        architecture=" + ".join(r["model"] for r in reports),
        trained_on=a.trained_on,
        calibration=a.calib,
        classes=classes,
        models=[dict(file=f"{r}.onnx", temperature=t, weight=1.0) for r, t in zip(a.runs, temps)],
        thresholds=thresholds,
        parity=parities,
        metrics=metrics_out,
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(json.dumps({k: manifest[k] for k in ("architecture", "thresholds", "parity", "metrics")}, indent=1))


if __name__ == "__main__":
    main()
