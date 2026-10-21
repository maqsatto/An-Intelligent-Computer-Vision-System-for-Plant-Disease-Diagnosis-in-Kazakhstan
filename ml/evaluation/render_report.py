"""Render completed evaluation to standalone local HTML and photo-free tracked Markdown.

Reads measured JSON only; never runs inference or changes its frozen provenance.
"""

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CROPS = {"wheat": "Пшеница", "potato": "Картофель", "tomato": "Томат"}
CONDITIONS = {
    "early_blight": "Альтернариоз / Early blight",
    "late_blight": "Фитофтороз / Late blight",
    "healthy_appearance": "Внешне здоровый лист",
    "septoria_source_label": "Септориоз — исходная метка",
    "stripe_rust": "Полосатая ржавчина",
}
TRANSFORMS = {
    "clean": "Без дополнительного ухудшения",
    "blur_radius4": "Размытие Gaussian, радиус 4",
    "rotate90": "Поворот на 90°",
    "dark_0.15": "Яркость 15%",
    "jpeg_quality5": "JPEG quality 5",
}


def label(class_id):
    crop, condition = class_id.split("__", 1)
    return CROPS.get(crop, crop) + " · " + CONDITIONS.get(condition, condition)


def pct(value):
    return f"{value * 100:.2f}%"


def escaped(value):
    return html.escape(str(value))


def image_uri(path):
    mime = "image/png" if path.suffix == ".png" else "image/jpeg"
    return "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode()


def render(directory, publish=False):
    report = json.loads((directory / "report.json").read_text())
    cases = report["cases"]
    joint = report["joint"]
    paired = report["paired"]
    sections = []

    def section(title, body):
        sections.append("<section><h2>" + escaped(title) + "</h2>" + body + "</section>")

    section(
        "Что действительно проверено",
        f"""<p>Полный сохранённый test joint: <b>{joint["images"]} фото / {joint["groups"]} доступные группы</b>.
    Raw global top-1 совпал с исходной меткой на <b>{pct(joint["accuracy"])}</b>, macro-F1 <b>{joint["macro_f1"]:.5f}</b>.
    Это внутренние результаты по исходным меткам наборов, не точность диагностики в Казахстане.
    Группы пшеницы — только прокси дедупликации: независимость растений/сессий не установлена.</p>
    <p>Все результаты публичного research runtime — <b>inconclusive</b>, prediction=null.
    Кандидат и его скор не означают принятый диагноз. Все скоры ниже — некалиброванные глобальные model_score, не вероятность болезни.</p>""",
    )
    section(
        "Честное сравнение двух моделей на одних фото",
        f"""<p>Пересечение test∩test по SHA256: <b>{paired["images"]} одинаковых фото картофеля/томата, {paired["groups"]} групп</b>.
    Joint: accuracy {pct(paired["joint"]["accuracy"])}, macro-F1 по общим6классам {paired["joint"]["macro_f1"]:.5f}.
    PV: accuracy {pct(paired["pv"]["accuracy"])}, macro-F1 {paired["pv"]["macro_f1"]:.5f}.</p>
    <p>Обе верны: {paired["both_correct"]}; только joint: {paired["joint_only_correct"]}; только PV: {paired["pv_only_correct"]}; обе ошиблись: {paired["both_wrong"]}.
    Joint имеет9выходных классов, PV6. Шкалы softmax между моделями не калиброваны. Нельзя объявлять победителя по сравнению разных тестовых наборов.</p>""",
    )
    cards = []
    for record in cases["illustrative_successes_and_errors"]:
        path = directory / "case_images" / f"example-{record['sha256'][:12]}.jpg"
        correct = record["correct"]
        status = "Совпало" if correct else "Ошибка"
        css = "ok" if correct else "error"
        cards.append(f'''<article class="card {css}"><img src="{image_uri(path)}" alt="Исходный лист для демонстрации" loading="lazy">
        <h3>{status}</h3><p><b>Метка источника:</b> {escaped(label(record["expected_class_id"]))}</p>
        <p><b>Raw global top-1:</b> {escaped(label(record["predicted_class_id"]))}</p>
        <p><b>Скор:</b> {record["top_score"]:.3f}, не вероятность диагноза</p>
        <p>Публичный исход: <b>inconclusive</b></p><small>SHA256 {record["sha256"][:16]}… · {escaped(record["selection"])}</small></article>''')
    section(
        "Совпадения и ошибки — реальные фото",
        '<p>После полного replay детерминированно выбран минимальный SHA256 для совпадения и ошибки каждого класса, где такие случаи есть. Это иллюстрации, а не новый тестовый набор. Метка источника не является независимо подтверждённым диагнозом. На полном joint test11ошибок; ниже6представителей классов с ошибками и9совпадений.</p><div class="cards">'
        + "".join(cards)
        + "</div>",
    )
    legend = (
        '<ol start="0">'
        + "".join("<li>" + escaped(label(name)) + "</li>" for name in joint["class_order"])
        + "</ol>"
    )
    section(
        "Полная confusion matrix",
        '<p>Строка — метка источника, колонка — raw global top-1. Все153тестовых фото включены; ошибочные предсказания не отфильтрованы.</p><img class="plot" src="'
        + image_uri(directory / "joint_confusion.png")
        + '" alt="Joint confusion matrix">'
        + legend,
    )
    perclass = (
        "<table><tr><th>Метка источника</th><th>N</th><th>Precision</th><th>Recall</th><th>F1</th></tr>"
    )
    for name, metrics in joint["per_class"].items():
        perclass += f"<tr><td>{escaped(label(name))}</td><td>{metrics['support']}</td><td>{metrics['precision']:.3f}</td><td>{metrics['recall']:.3f}</td><td>{metrics['f1']:.3f}</td></tr>"
    section("Результаты по каждому классу", perclass + "</table>")
    variants = "<table><tr><th>Вариант</th><th>Совпало crop top-1 / N9</th></tr>"
    for name, stats in report["variants_summary"].items():
        variants += (
            f"<tr><td>{escaped(TRANSFORMS[name])}</td><td>{stats['correct']}/{stats['images']}</td></tr>"
        )
    variants += "</table><p>Девять исходников выбраны до оценки: по минимальному SHA256 на каждый класс. Это9случаев, не45независимых растений. Поворот здесь не доказывает улучшение модели. Сначала PIL-аналог мобильной подготовки (длинная сторона≤2048,JPEG90), затем реальная API-нормализация; варианты применены к общей нормализованной фотографии и повторно нормализованы API. Это не bit-parity Expo/Android.</p>"
    for seed in cases["selection"]:
        variants += "<h3>" + escaped(label(seed["class_id"])) + '</h3><div class="variants">'
        for case in (item for item in cases["variants"] if item["source_sha256"] == seed["sha256"]):
            candidate = case["result"]["candidates"][0]
            path = (
                directory
                / "case_images"
                / f"{case['class_id']}-{case['transform']}-{case['source_sha256'][:8]}.jpg"
            )
            variants += f'''<article class="card"><img src="{image_uri(path)}" alt="{escaped(TRANSFORMS[case["transform"]])}" loading="lazy"><h3>{escaped(TRANSFORMS[case["transform"]])}</h3>
            <p>Кандидат выбранной культуры: {escaped(label(candidate["class_id"]))}</p><p>Глобальный скор {candidate["score"]:.3f}</p><p>inconclusive · {"совпало" if case["correct_selected_crop_top1"] else "ошибка"}</p></article>'''
        variants += "</div>"
    section("Детерминированные ухудшения", variants)
    wrong = "<table><tr><th>Культура источника</th><th>Выбрана неверно</th><th>Масса выбранной культуры</th><th>Кандидат</th><th>Его глобальный скор</th></tr>"
    for case in cases["wrong_crop"]:
        candidate = case["result"]["candidates"][0]
        wrong += f"<tr><td>{CROPS[case['true_crop']]}</td><td>{CROPS[case['selected_crop']]}</td><td>{case['result']['selected_crop_mass']:.5f}</td><td>{escaped(label(candidate['class_id']))}</td><td>{candidate['score']:.5f}</td></tr>"
    section(
        "Неверно выбранная культура",
        wrong
        + "</table><p>Скоры не перенормируются после фильтрации культуры: кандидат с очень маленькой глобальной массой не становится уверенным ответом. Исход всегда inconclusive; это не валидация автоматического распознавания неправильной культуры.</p>",
    )
    section(
        "Синтетические контроли — не реальный OOD-тест",
        f'''<p>Однотонный серый/зелёный, шахматная текстура и шум seed17, по3выбора культуры: {report["synthetic_control_count"]} входов.
    Максимальный raw global скор {report["synthetic_max_global_score"]:.3f}. Метки болезни у них отсутствуют.
    Это не реальные фотографии неизвестных растений и не доказательство детекции OOD. Research abstains по правилу режима.</p><img class="plot" src="{image_uri(directory / "synthetic_controls.png")}" alt="Синтетические контроли">''',
    )
    section(
        "Ограничения входа и память",
        f"""<p>{report["raw_joint_serving_geometry_rejected"]} из153сырых test-фото превышают serving-геометрию (типично24MP): offline replay явно использовал cap50MP, сохраняя4MP intermediate cap. Они не подаются в API без уменьшения.
    На9демоисходниках отдельно измерены исходнаяAPIдопустимость и мобильный PIL-аналог; затем фактическая API-нормализация.
    Некорректные байты и сжатый JPEG10×60000 отклонены до inference. Неподдержанная культура даёт inconclusive без кандидатов.</p>
    <p>CPU only,2ORTthreads, scope MemoryMax2GiB. Время {report["environment"]["elapsed_seconds"]:.2f}s; peakRSS {report["environment"]["peak_process_rss_mib"]:.1f}MiB. Нет обучения/GPU/новых данных.</p>""",
    )
    section(
        "Источники изображений и лицензии",
        "<p><b>PlantVillage:</b> Sharada P. Mohanty, David P. Hughes, Marcel Salathé, "
        "<i>Using Deep Learning for Image-Based Plant Disease Detection</i> (2016). "
        '<a href="https://github.com/spMohanty/PlantVillage-Dataset">Авторский репозиторий</a>; '
        '<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC BY-SA 3.0</a>. '
        "Изображения PlantVillage и показанные преобразования сохраняют эту лицензию.</p>"
        "<p><b>Wheat Leaf Dataset, version 1:</b> Hawi Getachew (2021), "
        '<a href="https://doi.org/10.17632/wgd66f8n6h.1">DOI 10.17632/wgd66f8n6h.1</a>, '
        '<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. '
        "Изображения пшеницы и показанные преобразования сохраняют эту лицензию.</p>"
        "<p>Преобразования явно выполнены для этой демонстрации: EXIF/RGB-нормализация, "
        "уменьшение до длинной стороны 2048, JPEG-сериализация, размытие, поворот на 90°, "
        "затемнение и сильное JPEG-сжатие; миниатюры и контактные листы. "
        "Исходные метки сохранены. Авторы наборов не заявляются авторами предсказаний модели. "
        "Точные SHA256, версии источников и выборка сохранены в JSON и манифестах.</p>",
    )
    body = "".join(sections)
    css = """body{font:18px/1.55 system-ui,sans-serif;background:#f3f6f2;color:#17261b;margin:0}main{max-width:1500px;margin:auto;padding:30px}h1{font-size:38px}h2{font-size:28px}h3{font-size:20px}section{background:white;padding:26px;border-radius:16px;margin:24px 0}p{max-width:1100px}table{width:100%;border-collapse:collapse;font-size:17px}td,th{padding:10px;border-bottom:1px solid #ccd7cc;text-align:left}th{background:#e7efe6}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}.variants{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}.card{border:1px solid #c9d3c9;border-radius:12px;padding:14px;background:#fafcf9;font-size:17px}.card img{width:100%;height:245px;object-fit:contain;background:#e5e9e2}.card p{margin:9px 0}.ok{border-top:6px solid #4e8549}.error{border-top:6px solid #bd623d}.plot{max-width:100%;height:auto}small{font-size:13px;overflow-wrap:anywhere}.note{padding:18px;background:#fff1cc;border-radius:10px}li{padding:3px}ol{columns:2}a{color:#205f32}"""
    document = (
        '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AgroVision · реальные модельные кейсы</title><style>'
        + css
        + '</style><main><h1>AgroVision: что модель видит — и где ошибается</h1><p class="note">Исследовательская демонстрация. Метки исходных наборов ≠ подтверждённый диагноз. Raw model_score ≠ вероятность болезни. Продуктовый исход всегда inconclusive.</p>'
        + body
        + "</main></html>"
    )
    (directory / "index.html").write_text(document)
    checksums = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [directory / "index.html", directory / "report.json", directory / "raw_predictions.json"]
    }
    (directory / "render_manifest.json").write_text(
        json.dumps(
            dict(renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), files=checksums),
            indent=2,
        )
    )
    md = f"""# Реальные модельные кейсы AgroVision

Проверены существующие исследовательские веса: без обучения, GPU и подбора порогов. Полный локальный HTML с фотографиями: `artifacts/evaluation/model-cases-v1/index.html`. В Git сохраняются только скрипты и агрегаты.

| Проверка | Результат |
|---|---|
| Joint: полный test | {joint["images"]} фото / {joint["groups"]} доступные группы; accuracy {pct(joint["accuracy"])}; macro-F1 {joint["macro_f1"]:.5f} |
| PV: полный test | {report["pv"]["images"]} фото; accuracy {pct(report["pv"]["accuracy"])}; macro-F1 {report["pv"]["macro_f1"]:.5f} |
| Одинаковые test ∩ test | {paired["images"]} SHA256 / {paired["groups"]} групп; accuracy joint и PV: {pct(paired["joint"]["accuracy"])} / {pct(paired["pv"]["accuracy"])} |
| Парный macro-F1 по общим 6 меткам | Joint {paired["joint"]["macro_f1"]:.5f}; PV {paired["pv"]["macro_f1"]:.5f} |
| Парные совпадения и ошибки | Обе верны: {paired["both_correct"]}; только joint: {paired["joint_only_correct"]}; только PV: {paired["pv_only_correct"]}; обе ошиблись: {paired["both_wrong"]} |
| Иллюстрации | 9 заранее выбранных исходников × 5 вариантов; отдельно 9 совпадений и 6 ошибок после полного replay |
| Синтетические контроли | {report["synthetic_control_count"]} входов; максимальный глобальный скор {report["synthetic_max_global_score"]:.3f}; это не реальная OOD-валидация |
| Ограничения serving | {report["raw_joint_serving_geometry_rejected"]} / 153 сырых фото не допускаются геометрией serving; offline явно допускает источник до 50 MP |
| Ресурсы | CPU, 2 потока ORT, scope 2 GiB; peak RSS {report["environment"]["peak_process_rss_mib"]:.1f} MiB; {report["environment"]["elapsed_seconds"]:.2f} с |

## Варианты девяти фиксированных исходников

| Вариант | Совпало crop top-1 |
|---|---|
"""
    for name, stats in report["variants_summary"].items():
        md += f"| {TRANSFORMS[name]} | {stats['correct']} / {stats['images']} |\n"
    md += r"""
Все 153 joint- и 88 PV-предсказания включены в оценку. Сохранены precision, recall и F1 каждого класса, а также полные confusion matrices. Исторические raw-метрики воспроизвелись точно. Полные тестовые наборы различаются, поэтому модели сравниваются только на 88 одинаковых SHA256 без пересечений с non-test разделами. У joint 9 выходов, у PV 6; парный macro-F1 усредняется по общим 6 истинным классам. Полная матрица joint сохраняет ошибки в дополнительные классы. Результаты по отдельным изображениям не доказывают независимость растений.

Скоры глобальные и после выбора культуры не перенормируются. Все проверенные публичные research-результаты имеют `inconclusive`, `prediction=null`. Неверная культура, неподдержанная культура, некорректные байты и чрезмерно вытянутый JPEG проверены отдельно. Высокий скор не даёт диагноза: среди реальных ошибок есть томат Early blight → healthy appearance со скором 0.910.

Деградации не являются независимыми растениями или полной оценкой устойчивости: n=9, один минимальный SHA256 на класс выбран до оценки. Совпадения и ошибки в галерее детерминированно выбираются после полного replay и явно помечены как иллюстрации. Варианты применены к общей API-нормализованной фотографии с повторной API-сериализацией. Мобильная стадия — PIL-аналог 2048 / JPEG90, а не проверка совпадения с кодеком Expo/Android. Синтетические контроли не заменяют реальные OOD, unknown и poor-quality данные. Группы пшеницы — дедуп-прокси, без подтверждённых plant/session ID. Нет локальной проверки в Казахстане, калибровки или диагностического допуска.

## Источники изображений

PlantVillage: Sharada P. Mohanty, David P. Hughes, Marcel Salathé (2016), [авторский репозиторий](https://github.com/spMohanty/PlantVillage-Dataset), CC BY-SA 3.0. Wheat Leaf Dataset v1: Hawi Getachew (2021), [DOI 10.17632/wgd66f8n6h.1](https://doi.org/10.17632/wgd66f8n6h.1), CC BY 4.0. В локальном HTML явно обозначены преобразования; изображения и их производные сохраняют соответствующие лицензии. Фотографий в Git нет.

## Воспроизведение

```bash
systemd-run --user --scope -p MemoryMax=2G -p MemoryHigh=1800M -p MemorySwapMax=512M \
  env OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  uv run python ml/evaluation/evaluate_cases.py --publish
uv run python ml/evaluation/render_report.py --publish
uv run pytest tests/evaluation -q
```

Нужны уже полученные локальные данные и два bundle. Unit-тестам ignored data/models не нужны. Контрольные суммы весов, исходных и split/test-манифестов, выборки, скрипта, runtime, API-normalizer и локальных результатов сохранены в [MEASURED_CASES.json](MEASURED_CASES.json). Полные raw-скоры и фотографии остаются в ignored `artifacts/`. Скрипт отклоняет несовпадение хешей изображений, моделей и манифестов, а также исторической confusion matrix. Это replay существующих весов, а не новое обучение. Renderer сохраняет отдельные контрольные суммы в [RENDERING.json](RENDERING.json) и не меняет зафиксированную provenance inference-отчёта.
"""
    if publish:
        (ROOT / "docs/evaluation/MEASURED_CASES.md").write_text(md)
        descriptor = dict(
            renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            inference_report_sha256=checksums["report.json"],
            local_html_sha256=checksums["index.html"],
            markdown_sha256=hashlib.sha256(md.encode()).hexdigest(),
            measured_aggregate_sha256=hashlib.sha256(
                (ROOT / "docs/evaluation/MEASURED_CASES.json").read_bytes()
            ).hexdigest(),
        )
        (ROOT / "docs/evaluation/RENDERING.json").write_text(json.dumps(descriptor, indent=2))
    print("Rendered", directory / "index.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="artifacts/evaluation/model-cases-v1")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    render(ROOT / args.directory, args.publish)
