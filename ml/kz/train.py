"""Fine-tune an ImageNet/in21k pretrained timm backbone on the KZ-agro corpus.

Data: ``data/pack/images.npy`` (N,256,256,3 uint8) + ``meta.csv``. Augmentation runs on the GPU.
Selection uses only the ``val`` split; ``test`` (lab+field, grouped) and ``field_test``
(held-out PlantDoc field photographs) are reported once at the end with the best-val checkpoint.
"""

import argparse
import json
import math
import threading
import time
from pathlib import Path
from queue import Queue

import numpy as np
import pandas as pd
import timm
import torch
import torch.nn.functional as F
from sklearn.metrics import accuracy_score, f1_score

ROOT = Path(__file__).resolve().parents[2]
RES = 224
LR = {  # (backbone lr, head lr)
    "default": (1e-4, 1e-3),
    "efficientnet": (4e-4, 2e-3),
    "mobilenet": (5e-4, 2e-3),
    "vit": (4e-5, 1e-3),
    "deit": (4e-5, 1e-3),
    "swin": (6e-5, 1e-3),
    "eva": (4e-5, 1e-3),
}


def lr_for(name):
    for key, value in LR.items():
        if key in name:
            return value
    return LR["default"]


class Loader:
    """Background-thread batch producer from the uint8 memmap."""

    def __init__(self, images, labels, idx, weights, batch, steps, seed, masks=None, has_mask=None):
        self.images, self.labels, self.batch, self.steps = images, labels, batch, steps
        self.masks, self.has_mask = masks, has_mask
        self.idx, self.weights = idx, weights
        self.rng = np.random.default_rng(seed)
        self.q = Queue(maxsize=6)
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        p = self.weights / self.weights.sum()
        for _ in range(self.steps):
            pick = np.sort(self.rng.choice(self.idx, size=self.batch, p=p))
            x = torch.from_numpy(self.images[pick]).pin_memory()
            y = torch.from_numpy(self.labels[pick])
            if self.masks is not None:
                m = torch.from_numpy(np.ascontiguousarray(self.masks[pick])).pin_memory()
                hm = torch.from_numpy(self.has_mask[pick])
                self.q.put((x, y, m, hm))
            else:
                self.q.put((x, y))
        self.q.put(None)

    def __iter__(self):
        while (item := self.q.get()) is not None:
            yield item


def composite_background(x, m, hm, bank, p=0.6):
    """Replace the background of masked (lab) samples with random textures/scenes. x uint8 (B,256,256,3)."""
    b = x.shape[0]
    use = hm & (torch.rand(b, device=x.device) < p)
    if not use.any():
        return x
    bg = bank[torch.randint(0, bank.shape[0], (b,), device=x.device)]
    flip = torch.rand(b, device=x.device) < 0.5
    bg = torch.where(flip.view(-1, 1, 1, 1), bg.flip(2), bg)
    bgf = bg.float() * torch.empty(b, 1, 1, 1, device=x.device).uniform_(0.6, 1.2)
    mf = m.float().unsqueeze(1)
    mf = F.avg_pool2d(mf, 3, 1, 1)  # soften the edge
    out = x.permute(0, 3, 1, 2).float() * mf + bgf.permute(0, 3, 1, 2) * (1 - mf)
    out = out.clamp(0, 255).round().to(torch.uint8).permute(0, 2, 3, 1)
    return torch.where(use.view(-1, 1, 1, 1), out, x)


def strong_extras(x):
    """x: normalised float (B,3,H,W). Blur, noise and random erasing."""
    b, _, h, w = x.shape
    dev = x.device
    blur = torch.rand(b, device=dev) < 0.2
    if blur.any():
        k = F.avg_pool2d(x, 5, 1, 2)
        x = torch.where(blur.view(-1, 1, 1, 1), k, x)
    x = x + torch.randn_like(x) * (torch.rand(b, 1, 1, 1, device=dev) * 0.08)
    for _ in range(2):
        er = torch.rand(b, device=dev) < 0.2
        eh = (torch.rand(b, device=dev) * 0.3 + 0.1) * h
        ew = (torch.rand(b, device=dev) * 0.3 + 0.1) * w
        cy, cx = torch.rand(b, device=dev) * h, torch.rand(b, device=dev) * w
        yy = torch.arange(h, device=dev).view(1, h, 1)
        xx = torch.arange(w, device=dev).view(1, 1, w)
        box = ((yy - cy.view(-1, 1, 1)).abs() < eh.view(-1, 1, 1) / 2) & ((xx - cx.view(-1, 1, 1)).abs() < ew.view(-1, 1, 1) / 2)
        box = (box & er.view(-1, 1, 1)).unsqueeze(1)
        x = torch.where(box, torch.randn_like(x) * 0.5, x)
    return x


def gpu_augment(x, mean, std):
    """x: uint8 (B,256,256,3) on GPU -> normalised float (B,3,224,224) with per-sample augmentation."""
    b = x.shape[0]
    x = x.permute(0, 3, 1, 2).float() / 255.0
    dev = x.device
    scale = torch.empty(b, device=dev).uniform_(0.45, 1.0)  # crop side fraction^2 -> area
    side = scale.sqrt()
    ratio = torch.empty(b, device=dev).uniform_(math.log(3 / 4), math.log(4 / 3)).exp().sqrt()
    sx, sy = (side * ratio).clamp(max=1.0), (side / ratio).clamp(max=1.0)
    angle = torch.empty(b, device=dev).uniform_(-math.pi / 6, math.pi / 6)
    flip = (torch.rand(b, device=dev) < 0.5).float() * 2 - 1
    vflip = (torch.rand(b, device=dev) < 0.2).float() * 2 - 1
    tx = (torch.rand(b, device=dev) * 2 - 1) * (1 - sx)
    ty = (torch.rand(b, device=dev) * 2 - 1) * (1 - sy)
    cos, sin = angle.cos(), angle.sin()
    theta = torch.stack(
        [
            torch.stack([sx * cos * flip, -sy * sin, tx], 1),
            torch.stack([sx * sin * flip, sy * cos * vflip, ty], 1),
        ],
        1,
    )
    grid = F.affine_grid(theta, (b, 3, RES, RES), align_corners=False)
    x = F.grid_sample(x, grid, mode="bilinear", padding_mode="reflection", align_corners=False)
    # colour jitter
    br = torch.empty(b, 1, 1, 1, device=dev).uniform_(0.7, 1.3)
    ct = torch.empty(b, 1, 1, 1, device=dev).uniform_(0.7, 1.3)
    sat = torch.empty(b, 1, 1, 1, device=dev).uniform_(0.6, 1.4)
    x = x * br
    m = x.mean(dim=(1, 2, 3), keepdim=True)
    x = (x - m) * ct + m
    g = x.mean(dim=1, keepdim=True)
    x = (x - g) * sat + g
    x = x + torch.randn(b, 3, 1, 1, device=dev) * 0.02  # white-balance shift
    x = x.clamp(0, 1)
    return (x - mean) / std


def prep_eval(x, mean, std):
    x = x.permute(0, 3, 1, 2).float() / 255.0
    o = (256 - RES) // 2
    x = x[:, :, o : o + RES, o : o + RES]
    return (x - mean) / std


def evaluate(model, images, labels, idx, mean, std, bs=256):
    order = np.sort(idx)
    logits = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(order), bs):
            x = torch.from_numpy(images[order[i : i + bs]]).cuda(non_blocking=True)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits.append(model(prep_eval(x, mean, std)).float().cpu())
    logits = torch.cat(logits).numpy() if logits else np.zeros((0, 1))
    y = labels[order]
    pred = logits.argmax(1)
    return order, logits, y, pred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--run", default=None)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--steps-per-epoch", type=int, default=500)
    ap.add_argument("--batch", type=int, default=96)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--field-weight", type=float, default=3.0)
    ap.add_argument("--no-field-train", action="store_true", help="exclude PlantDoc from training (zero-shot field test)")
    ap.add_argument("--lr-scale", type=float, default=1.0)
    ap.add_argument("--aug", choices=["v1", "v2"], default="v1", help="v2: background replacement + blur/noise/erasing")
    ap.add_argument("--bg-prob", type=float, default=0.6)
    ap.add_argument("--pack", default="pack", help="data/<pack> directory (pack | pack_w)")
    a = ap.parse_args()
    torch.manual_seed(a.seed)
    run = ROOT / "runs" / (a.run or a.model.replace("/", "_"))
    run.mkdir(parents=True, exist_ok=True)

    meta = pd.read_csv(ROOT / "data" / a.pack / "meta.csv")
    n = int(np.load(ROOT / "data" / a.pack / "images_n.npy")[0])
    images = np.load(ROOT / "data" / a.pack / "images.npy", mmap_mode="r")
    meta = meta[meta.split != "quarantine"].copy()
    classes = sorted(meta[meta.split == "train"].label.unique())
    cid = {c: i for i, c in enumerate(classes)}
    labels = np.full(n, -1, dtype=np.int64)
    for i, name in zip(meta.idx, meta.label):
        labels[i] = cid.get(name, -1)
    tr = meta[(meta.split == "train")]
    if a.no_field_train:
        tr = tr[tr.source != "plantdoc"]
    tr_idx = tr.idx.values
    counts = np.bincount(labels[tr_idx], minlength=len(classes)).astype(float)
    w = 1.0 / np.sqrt(counts[labels[tr_idx]])
    w = w * np.where(tr.domain.values == "field", a.field_weight, 1.0)
    (run / "classes.json").write_text(json.dumps(classes, indent=1))

    kwargs = {"drop_path_rate": 0.1} if any(k in a.model for k in ("convnext", "swin", "vit", "eva", "maxvit", "efficientnetv2")) else {}
    if "dinov2" in a.model:
        kwargs["img_size"] = RES
    model = timm.create_model(a.model, pretrained=True, num_classes=len(classes), **kwargs)
    cfg = model.pretrained_cfg
    mean = torch.tensor(cfg["mean"], device="cuda").view(1, 3, 1, 1)
    std = torch.tensor(cfg["std"], device="cuda").view(1, 3, 1, 1)
    model = model.cuda().to(memory_format=torch.channels_last)
    head_names = {n_ for n_, _ in model.named_parameters() if n_.startswith(tuple(h + "." for h in ("head", "fc", "classifier", "last_linear", "head_fc")))}
    head = [p for n_, p in model.named_parameters() if n_ in head_names]
    body = [p for n_, p in model.named_parameters() if n_ not in head_names]
    blr, hlr = (x * a.lr_scale for x in lr_for(a.model))
    opt = torch.optim.AdamW([{"params": body, "lr": blr}, {"params": head, "lr": hlr}], weight_decay=0.05)
    total = a.epochs * a.steps_per_epoch
    warm = 200

    def lr_at(step):
        return step / warm if step < warm else 0.5 * (1 + math.cos(math.pi * (step - warm) / (total - warm)))

    base = [blr, hlr]
    masks = has_mask = bank = None
    if a.aug == "v2":
        masks = np.load(ROOT / "data" / a.pack / "masks.npy", mmap_mode="r")
        has_mask = np.load(ROOT / "data" / a.pack / "has_mask.npy")
        pool = meta[(meta.split == "train") & meta.source.isin(["tinyimagenet", "dtd", "sunflower", "cucumber", "wheat_jic_field", "potato_field"])]
        pool = pool.sample(n=min(4500, len(pool)), random_state=a.seed).idx.values
        bank = torch.from_numpy(images[np.sort(pool)]).cuda()
        print("background bank", tuple(bank.shape), "masked samples", int(has_mask[tr_idx].sum()), flush=True)
    loader = iter(Loader(images, labels, tr_idx, w, a.batch, total, a.seed, masks, has_mask))
    val_idx = meta[meta.split == "val"].idx.values
    history, best_f1 = [], -1
    step, t0 = 0, time.time()
    for epoch in range(a.epochs):
        model.train()
        loss_sum = 0.0
        for _ in range(a.steps_per_epoch):
            batch_ = next(loader)
            if a.aug == "v2":
                x, y, m, hm = (t.cuda(non_blocking=True) for t in batch_)
                x = composite_background(x, m, hm, bank, a.bg_prob)
            else:
                x, y = (t.cuda(non_blocking=True) for t in batch_)
            for g, b0 in zip(opt.param_groups, base):
                g["lr"] = b0 * lr_at(step)
            xa = gpu_augment(x, mean, std)
            if a.aug == "v2":
                xa = strong_extras(xa)
            xa = xa.contiguous(memory_format=torch.channels_last)
            # mixup/cutmix-free; label smoothing only
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = F.cross_entropy(model(xa).float(), y, label_smoothing=0.1)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 2.0)
            opt.step()
            loss_sum += loss.item() if step % 20 == 0 else 0
            step += 1
        _, _, y_, p_ = evaluate(model, images, labels, val_idx, mean, std)
        f1 = f1_score(y_, p_, average="macro")
        acc = accuracy_score(y_, p_)
        history.append(dict(epoch=epoch + 1, val_macro_f1=f1, val_acc=acc, seconds=time.time() - t0))
        print(json.dumps(history[-1]), flush=True)
        if f1 > best_f1:
            best_f1 = f1
            torch.save(model.state_dict(), run / "best.pt")
    model.load_state_dict(torch.load(run / "best.pt"))
    report = dict(model=a.model, classes=classes, history=history, params_m=sum(p.numel() for p in model.parameters()) / 1e6,
                  mean=cfg["mean"], std=cfg["std"], args=vars(a), train_images=int(len(tr_idx)), peak_gb=torch.cuda.max_memory_allocated() / 2**30)
    for split in ("val", "test", "field_test"):
        idx = meta[meta.split == split].idx.values
        if not len(idx):
            continue
        order, logits, y_, p_ = evaluate(model, images, labels, idx, mean, std)
        mask = y_ >= 0
        sub = meta.set_index("idx").loc[order]
        res = dict(n=int(len(order)), acc=float(accuracy_score(y_[mask], p_[mask])), macro_f1=float(f1_score(y_[mask], p_[mask], average="macro")))
        res["by_source"] = {s: float(accuracy_score(y_[(sub.source.values == s) & mask], p_[(sub.source.values == s) & mask])) for s in sub.source.unique()}
        res["by_crop"] = {c: float(accuracy_score(y_[(sub.crop.values == c) & mask], p_[(sub.crop.values == c) & mask])) for c in sub.crop.unique()}
        report[split] = res
        np.savez_compressed(run / f"logits_{split}.npz", idx=order, logits=logits.astype(np.float16), y=y_)
    # inference speed (batch 1 and 32)
    model.eval()
    xb = torch.randn(32, 3, RES, RES, device="cuda").contiguous(memory_format=torch.channels_last)
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        for _ in range(5):
            model(xb)
        torch.cuda.synchronize()
        t = time.time()
        for _ in range(20):
            model(xb)
        torch.cuda.synchronize()
    report["gpu_img_per_s_bs32"] = 32 * 20 / (time.time() - t)
    (run / "report.json").write_text(json.dumps(report, indent=1))
    print("FINAL", json.dumps({k: report[k] for k in ("model", "val", "test", "field_test") if k in report}), flush=True)


if __name__ == "__main__":
    main()
