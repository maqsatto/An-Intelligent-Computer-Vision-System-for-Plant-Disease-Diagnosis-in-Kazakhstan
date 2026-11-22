"use strict";
const $ = (id) => document.getElementById(id);
const state = { crop: "auto", file: null, model: null };

const QUALITY = {
  blurry: "Фото выглядит размытым — снимите ближе и дождитесь фокуса.",
  dark: "Слишком темно — снимите при дневном свете.",
  overexposed: "Пересвеченное фото — избегайте прямого солнца и вспышки.",
  low_resolution: "Низкое разрешение — лист лучше снять крупнее.",
  no_vegetation: "На фото почти нет зелёных тканей — убедитесь, что в кадре лист растения.",
};
const STATUS = {
  confident: ["Уверенный результат", "confident"],
  uncertain: ["Результат требует проверки", "uncertain"],
  unrecognized: ["Не удалось распознать", "unrecognized"],
};

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.append(child);
  return node;
}
const pct = (p) => `${(Math.min(p, 0.999) * 100).toFixed(1)}%`;

async function loadModel() {
  try {
    state.model = await (await fetch("/api/model")).json();
  } catch (e) {
    state.model = null;
  }
  const box = $("crops");
  box.replaceChildren();
  const crops = [{ id: "auto", name: "Авто" }, ...(state.model?.crops || [])];
  for (const crop of crops) {
    const chip = el("button", { class: "chip", type: "button", role: "radio", "aria-checked": String(crop.id === state.crop), text: crop.name });
    chip.addEventListener("click", () => {
      state.crop = crop.id;
      for (const c of box.children) c.setAttribute("aria-checked", String(c === chip));
    });
    box.append(chip);
  }
}

function setFile(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) return showError("Выберите файл изображения.");
  state.file = file;
  const url = URL.createObjectURL(file);
  $("preview").src = url;
  $("preview").hidden = false;
  $("drop-hint").hidden = true;
  $("analyze").disabled = false;
}

function showError(message) {
  $("empty").hidden = true;
  $("loading").hidden = true;
  const out = $("out");
  out.hidden = false;
  out.replaceChildren(el("div", { class: "alert bad", role: "alert", text: message }));
}

async function analyze() {
  if (!state.file) return;
  $("analyze").disabled = true;
  $("empty").hidden = true;
  $("out").hidden = true;
  $("loading").hidden = false;
  const form = new FormData();
  form.append("file", state.file);
  form.append("crop", state.crop);
  try {
    const response = await fetch("/api/diagnose", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || data.detail || "Ошибка анализа");
    render(data);
    await saveHistory(data);
  } catch (e) {
    showError(e.message || "Не удалось выполнить анализ. Повторите попытку.");
  } finally {
    $("analyze").disabled = false;
    $("loading").hidden = true;
  }
}

function meter(p, cls = "") {
  const m = el("div", { class: `meter ${cls}`, role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round(p * 100)) });
  m.append(el("i", { style: `width:${Math.max(2, p * 100)}%` }));
  return m;
}

function render(d) {
  const out = $("out");
  out.replaceChildren();
  const best = d.top[0];
  const [label, cls] = STATUS[d.status];
  out.append(el("span", { class: `status ${d.status === "confident" && best.healthy ? "healthy" : cls}`, text: label }));
  if (d.status === "unrecognized") {
    out.append(
      el("h3", { class: "dx", text: "Не похоже на поддерживаемый лист" }),
      el("p", { class: "muted", text: "Попробуйте снять один лист крупнее, при дневном свете, и выберите культуру вручную." }),
    );
  } else {
    out.append(el("h3", { class: "dx", text: best.healthy ? `${best.crop_name}: ${best.condition_name.toLowerCase()}` : best.condition_name }));
    out.append(el("p", { class: "crop", text: best.healthy ? "Признаков болезни не обнаружено" : `Культура: ${best.crop_name}` }));
    const level = d.status === "confident" ? "" : "amber";
    out.append(meter(best.probability, level), el("div", { class: "conf" }, el("span", { text: "Уверенность модели" }), el("span", { text: pct(best.probability) })));
  }
  if (d.crop_mismatch) {
    out.append(el("div", { class: "alert warn", text: `Фото больше похоже на культуру «${d.crop_mismatch.crop_name}» (${pct(d.crop_mismatch.probability)}). Проверьте выбранную культуру.` }));
  }
  for (const flag of d.quality_flags) if (QUALITY[flag]) out.append(el("div", { class: "alert warn", text: QUALITY[flag] }));
  if (d.status === "uncertain") out.append(el("div", { class: "alert warn", text: "Уверенность умеренная. Сделайте ещё одно фото и покажите растение агроному." }));

  const others = d.top.slice(1).filter((t) => t.probability >= 0.01);
  if (others.length && d.status !== "unrecognized") {
    out.append(el("h3", { text: "Другие варианты", style: "font-size:15px;margin:10px 0 6px" }));
    const list = el("ul", { class: "alt" });
    for (const t of others) {
      list.append(el("li", {}, el("span", { text: `${t.crop_name}: ${t.condition_name}` }), el("span", { class: "muted", text: pct(t.probability) }), meter(t.probability, "amber")));
    }
    out.append(list);
  }
  if (d.status !== "unrecognized" && state.model?.can_explain) {
    const box = el("div", { class: "explain" });
    const btn = el("button", { class: "btn secondary", type: "button", text: "Показать, где модель увидела признаки" });
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "Строим карту…";
      try {
        const form = new FormData();
        form.append("file", state.file);
        form.append("label", best.label);
        const r = await fetch("/api/explain", { method: "POST", body: form });
        const data = await r.json();
        if (!r.ok) throw new Error(data.message || "Карта недоступна");
        btn.remove();
        box.append(el("img", { src: data.image, alt: "Карта внимания модели: красным отмечены области, повлиявшие на результат" }), el("p", { class: "muted", text: "Красным отмечены области, сильнее всего повлиявшие на результат. Это подсказка, а не точная разметка поражения." }));
      } catch (e) {
        btn.disabled = false;
        btn.textContent = e.message;
      }
    });
    box.append(btn);
    out.append(box);
  }
  if (d.status !== "unrecognized" && d.advice && (d.advice.symptoms || d.advice.actions.length)) {
    const info = el("div", { class: "info" });
    if (d.advice.summary) info.append(el("p", { text: d.advice.summary }));
    if (d.advice.symptoms) info.append(el("h3", { text: "Признаки" }), el("p", { text: d.advice.symptoms }));
    if (d.advice.actions.length) {
      const ul = el("ul");
      for (const a of d.advice.actions) ul.append(el("li", { text: a }));
      info.append(el("h3", { text: "Что делать" }), ul);
    }
    out.append(info);
  }
  out.append(el("p", { class: "meta", text: `Модель: ${d.model.name} · ${d.latency_ms} мс · результат ориентировочный` }));
  out.hidden = false;
}

// ---- history (browser only) ----
const HKEY = "agrovision-history-v1";
const readHistory = () => { try { return JSON.parse(localStorage.getItem(HKEY) || "[]"); } catch { return []; } };
function thumb(file) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas");
      const s = 96 / Math.min(img.width, img.height);
      c.width = c.height = 96;
      c.getContext("2d").drawImage(img, (96 - img.width * s) / 2, (96 - img.height * s) / 2, img.width * s, img.height * s);
      resolve(c.toDataURL("image/jpeg", 0.7));
    };
    img.onerror = () => resolve("");
    img.src = URL.createObjectURL(file);
  });
}
async function saveHistory(d) {
  const best = d.top[0];
  const item = { t: Date.now(), thumb: await thumb(state.file), status: d.status, title: d.status === "unrecognized" ? "Не распознано" : `${best.crop_name}: ${best.condition_name}`, p: best.probability };
  try { localStorage.setItem(HKEY, JSON.stringify([item, ...readHistory()].slice(0, 20))); } catch { /* storage unavailable */ }
  refreshCount();
}
function refreshCount() {
  const n = readHistory().length;
  $("history-count").hidden = n === 0;
  $("history-count").textContent = n;
}
function showHistory() {
  const body = $("history-body");
  body.replaceChildren();
  const items = readHistory();
  if (!items.length) body.append(el("p", { class: "muted", text: "Пока пусто." }));
  const list = el("div", { class: "hist" });
  for (const it of items) {
    list.append(el("div", { class: "hist-item" }, it.thumb ? el("img", { src: it.thumb, alt: "" }) : el("span"),
      el("div", {}, el("strong", { text: it.title }), el("small", { text: new Date(it.t).toLocaleString("ru-RU") })),
      el("span", { class: "muted", text: it.status === "unrecognized" ? "" : pct(it.p) })));
  }
  body.append(list);
  $("history-dialog").showModal();
}

async function showModel() {
  const body = $("model-body");
  body.replaceChildren(el("p", { text: "Загрузка…" }));
  $("model-dialog").showModal();
  const m = state.model || (await (await fetch("/api/model")).json());
  body.replaceChildren(el("h2", { text: "О модели" }));
  body.append(el("p", {}, el("strong", { text: m.name }), document.createTextNode(` · ${m.architecture} · версия ${m.version}`)));
  if (m.trained_on) body.append(el("p", { class: "muted", text: m.trained_on }));
  if (m.metrics) {
    const rows = [
      ["Тест, фото как в обучении (лаборатория + поле)", m.metrics.test],
      ["Полевые фото PlantDoc (не обучались)", m.metrics.field_test],
      ["«Дикие» фото из интернета PlantWild (не обучались)", m.metrics.wild_test],
    ].filter((r) => r[1]);
    const table = el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "Набор" }), el("th", { class: "num", text: "Фото" }), el("th", { class: "num", text: "Точность" }), el("th", { class: "num", text: "Macro-F1" }), el("th", { class: "num", text: "«Уверенно»: доля / точность" }))));
    const tb = el("tbody");
    for (const [name, r] of rows) {
      const sel = r.confident_coverage == null ? "—" : `${(r.confident_coverage * 100).toFixed(0)}% / ${r.confident_accuracy == null ? "—" : (r.confident_accuracy * 100).toFixed(0) + "%"}`;
      tb.append(el("tr", {}, el("td", { text: name }), el("td", { class: "num", text: String(r.n) }), el("td", { class: "num", text: pct(r.acc) }), el("td", { class: "num", text: r.macro_f1.toFixed(3) }), el("td", { class: "num", text: sel })));
    }
    table.append(tb);
    body.append(el("h3", { text: "Качество" }), table);
    const w = m.metrics.wild_test;
    if (w) body.append(el("p", { class: "muted", text: `На «диких» фото: культура определена верно в ${(w.crop_acc * 100).toFixed(0)}% случаев, посторонние растения отклонены в ${(w.other_plants_rejected * 100).toFixed(0)}%.` }));
  }
  if (m.benchmark?.length) {
    body.append(el("h3", { text: "Сравнение архитектур (один и тот же протокол)" }));
    body.append(el("p", { class: "muted", text: "«Дикие» — независимая половина PlantWild (фото из интернета), не участвовавшая в обучении; точность по 23 исходным классам, одинаковым для всех строк. Варианты данных: чистые (без PlantWild), +фон (аугментация заменой фона), PlantWild v1 / v1+v2 (некоммерческое исследование)." }));
    const names = { clean: "чистые", "clean+bg-aug": "+фон", "wild-v1": "PlantWild v1", "wild-v1+v2": "PlantWild v1+v2" };
    const table = el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "Модель" }), el("th", { text: "Данные" }), el("th", { class: "num", text: "Test F1" }), el("th", { class: "num", text: "Дикие, %" }), el("th", { class: "num", text: "М парам." }))));
    const tb = el("tbody");
    const rows = [...m.benchmark].sort((x, y) => (y.wild_legacy ?? 0) - (x.wild_legacy ?? 0));
    for (const b of rows) tb.append(el("tr", {}, el("td", { text: b.model.split(".")[0] }), el("td", { text: names[b.variant] || b.variant }), el("td", { class: "num", text: b.test_f1.toFixed(3) }), el("td", { class: "num", text: b.wild_legacy == null ? "—" : (b.wild_legacy * 100).toFixed(0) }), el("td", { class: "num", text: b.params_m.toFixed(1) })));
    table.append(tb);
    body.append(table);
  }
  body.append(el("h3", { text: "Поддерживаемые культуры и состояния" }));
  for (const c of m.crops) {
    body.append(el("p", {}, el("strong", { text: c.name + ": " }), ...c.conditions.map((x) => el("span", { class: "tag", text: x.condition_name }))));
  }
  if (m.limitations?.length) {
    const ul = el("ul");
    for (const l of m.limitations) ul.append(el("li", { text: l }));
    body.append(el("h3", { text: "Ограничения" }), ul);
  }
}

// ---- sample gallery (held-out test photos) ----
async function loadSamples() {
  let items = [];
  try { items = await (await fetch("/static/samples/samples.json")).json(); } catch { return; }
  const box = $("samples");
  for (const it of items) {
    const b = el("button", { class: "sample", type: "button", title: it.label.replace("__", " · ") });
    b.append(el("img", { src: `/static/samples/${it.file}`, alt: "Пример: " + it.label.replace("__", " ") }));
    b.addEventListener("click", async () => {
      const blob = await (await fetch(`/static/samples/${it.file}`)).blob();
      setFile(new File([blob], it.file, { type: "image/jpeg" }));
      state.crop = "auto";
      for (const c of $("crops").children) c.setAttribute("aria-checked", String(c.textContent === "Авто"));
      analyze();
    });
    box.append(b);
  }
}

// ---- wiring ----
const drop = $("drop");
drop.addEventListener("click", () => $("file").click());
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("file").click(); } });
for (const type of ["dragenter", "dragover"]) drop.addEventListener(type, (e) => { e.preventDefault(); drop.classList.add("over"); });
for (const type of ["dragleave", "drop"]) drop.addEventListener(type, (e) => { e.preventDefault(); drop.classList.remove("over"); });
drop.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));
$("file").addEventListener("change", (e) => setFile(e.target.files[0]));
$("camera").addEventListener("change", (e) => setFile(e.target.files[0]));
$("pick").addEventListener("click", () => $("file").click());
$("shoot").addEventListener("click", () => $("camera").click());
$("analyze").addEventListener("click", analyze);
$("open-model").addEventListener("click", showModel);
$("open-history").addEventListener("click", showHistory);
$("clear-history").addEventListener("click", () => { try { localStorage.removeItem(HKEY); } catch { /* ignore */ } refreshCount(); showHistory(); });
document.addEventListener("paste", (e) => { const f = [...(e.clipboardData?.files || [])].find((x) => x.type.startsWith("image/")); if (f) setFile(f); });
loadModel();
loadSamples();
refreshCount();
