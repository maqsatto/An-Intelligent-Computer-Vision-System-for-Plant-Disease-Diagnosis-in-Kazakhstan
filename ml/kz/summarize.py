"""Aggregate runs/*/report.json into a markdown + JSON benchmark table."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(prefix=""):
    rows = []
    for report in sorted((ROOT / "runs").glob(f"{prefix}*/report.json")):
        r = json.loads(report.read_text())
        if r.get("skipped"):
            continue
        rows.append(
            dict(
                run=report.parent.name,
                wild_trained=report.parent.name.startswith(("w_", "w2_")),
                variant=(
                    "wild-v1+v2" if report.parent.name.startswith("w2_")
                    else "wild-v1" if report.parent.name.startswith("w_")
                    else "clean+bg-aug" if report.parent.name.startswith("v2_")
                    else "clean"
                ),
                wild_legacy=json.loads((report.parent / "external.json").read_text())["legacy_classes"]["acc"] if (report.parent / "external.json").exists() else None,
                model=r["model"],
                params_m=r["params_m"],
                val_f1=r["val"]["macro_f1"],
                test_acc=r["test"]["acc"],
                test_f1=r["test"]["macro_f1"],
                field_acc=r["field_test"]["acc"],
                field_f1=r["field_test"]["macro_f1"],
                wild_acc=json.loads((report.parent / "external.json").read_text())["acc"] if (report.parent / "external.json").exists() else None,
                wild_crop=json.loads((report.parent / "external.json").read_text())["crop_acc"] if (report.parent / "external.json").exists() else None,
                wild_hint=json.loads((report.parent / "external.json").read_text()).get("acc_with_crop_hint") if (report.parent / "external.json").exists() else None,
                img_s=r["gpu_img_per_s_bs32"],
                minutes=r["history"][-1]["seconds"] / 60,
            )
        )
    rows.sort(key=lambda x: (x["variant"], -((x["wild_legacy"] or 0) + x["field_acc"])))
    lines = [
        "| Model | Training data | Params, M | Val F1 | Test acc | Test F1 | PlantDoc acc | PlantDoc F1 | PlantWild acc (all supported classes) | PlantWild acc (23 shared classes) | PlantWild crop acc | PlantWild acc, crop given | img/s | Train min |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for x in rows:
        lines.append(
            f"| {x['model']} | {x['variant']} | {x['params_m']:.1f} | {x['val_f1']:.4f} | {x['test_acc']:.4f} | {x['test_f1']:.4f} | "
            f"{x['field_acc']:.4f} | {x['field_f1']:.4f} | "
            f"{'' if x['wild_acc'] is None else format(x['wild_acc'], '.4f')} | {'' if x['wild_legacy'] is None else format(x['wild_legacy'], '.4f')} | {'' if x['wild_crop'] is None else format(x['wild_crop'], '.4f')} | "
            f"{'' if x['wild_hint'] is None else format(x['wild_hint'], '.4f')} | "
            f"{x['img_s']:.0f} | {x['minutes']:.1f} |"
        )
    text = "\n".join(lines)
    (ROOT / "runs" / f"{prefix or 'benchmark'}_summary.md").write_text(text)
    (ROOT / "runs" / f"{prefix or 'benchmark'}_summary.json").write_text(json.dumps(rows, indent=1))
    print(text)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
