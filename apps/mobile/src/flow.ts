import type { ApiClient, Schemas } from "@agrovision/api-client";
function abortError() {
  const error = new Error("Ожидание отменено");
  error.name = "AbortError";
  return error;
}
function checkAborted(signal: AbortSignal) {
  if (signal.aborted) throw abortError();
}
export type Draft = {
  observationId: string;
  photoId: string;
  key: string;
  cropId: string;
  capturedAt: string;
  notes: string;
  uri: string;
  serverObservationId?: string;
  serverPhotoId?: string;
};
export async function runSubmission(
  api: ApiClient,
  draft: Draft,
  canAssess: boolean,
  signal: AbortSignal,
  update: (s: string) => void,
) {
  checkAborted(signal);
  update("Сохраняем наблюдение");
  if (!draft.serverObservationId) {
    const o = await api.createObservation(
      {
        client_observation_id: draft.observationId,
        crop_id: draft.cropId,
        organ: "leaf",
        captured_at: draft.capturedAt,
        notes: draft.notes || null,
        field_season_id: null,
      },
      signal,
    );
    draft.serverObservationId = o.id;
  }
  update("Загружаем основной снимок");
  if (!draft.serverPhotoId) {
    const p = await api.uploadPhoto(
      draft.serverObservationId!,
      draft.photoId,
      draft.uri,
      signal,
    );
    draft.serverPhotoId = p.id;
  }
  if (!canAssess)
    return { observationId: draft.serverObservationId!, assessment: null };
  update("Отправляем на оценку");
  const assessment = await api.createAssessment(
    {
      observation_id: draft.serverObservationId!,
      primary_photo_id: draft.serverPhotoId!,
    },
    draft.key,
    signal,
  );
  return { observationId: draft.serverObservationId!, assessment };
}
export const delay = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    checkAborted(signal);
    const abort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    signal.addEventListener("abort", abort, { once: true });
  });
export async function pollAssessment(
  api: ApiClient,
  id: string,
  signal: AbortSignal,
  update: (a: Schemas["AssessmentRead"]) => void,
  sleep = delay,
) {
  let attempts = 0;
  while (true) {
    checkAborted(signal);
    const a = await api.assessment(id, signal);
    update(a);
    if (a.status === "completed" || a.status === "failed") return a;
    attempts++;
    if (attempts >= 30)
      throw new Error(
        "Обработка продолжается на сервере. Продолжите ожидание или вернитесь к истории позже.",
      );
    await sleep(Math.min(1500 * 1.4 ** (attempts - 1), 10000), signal);
  }
}
export function outcomeCopy(outcome: string, reasonCodes: string[] = []) {
  if (reasonCodes.includes("unsupported_crop_or_organ"))
    return {
      title: "Культура или орган вне поддержки",
      body: "Выберите поддерживаемую культуру и снимите лист. Для этого наблюдения модель не рассчитывала гипотезы.",
    };
  if (reasonCodes.includes("research_model_unvalidated"))
    return {
      title: "Исследовательский результат",
      body: "Модель рассчитала предварительные гипотезы. Правила диагностического вывода и работа в полевых условиях ещё не проверены; эти гипотезы не подтверждают болезнь. Обсудите снимок с агрономом.",
    };
  switch (outcome) {
    case "predicted":
      return {
        title: "Предполагаемое состояние",
        body: "Это предварительная гипотеза по видимым признакам. Для подтверждения причины обратитесь к агроному.",
      };
    case "inconclusive":
      return {
        title: "Недостаточно данных",
        body: "Уверенного вывода нет. Снимите другой лист при естественном свете и обсудите наблюдение с агрономом.",
      };
    case "unsupported_input":
      return {
        title: "Снимок вне области поддержки",
        body: "Выберите поддерживаемую культуру и снимите один лист крупным планом.",
      };
    case "retake_photo":
      return {
        title: "Нужен другой снимок",
        body: "Протрите объектив, наведите фокус и снимите лист при равномерном свете.",
      };
    default:
      return {
        title: "Результат наблюдения",
        body: "Для этого результата требуется уточнение. Сохраните наблюдение для обсуждения с агрономом.",
      };
  }
}
export const conditionNames: Record<string, string> = {
  early_blight: "Возможный альтернариоз",
  late_blight: "Возможный фитофтороз",
  stripe_rust: "Возможная жёлтая ржавчина",
  septoria_source_label: "Пятнистость листа (класс «септориоз»)",
  healthy_appearance: "Предположительно здоровый вид",
  healthy: "Предположительно здоровый вид",
};
export function conditionLabel(id: string) {
  return (
    conditionNames[id] ??
    conditionNames[id.split(".").at(-1)!] ??
    `Гипотеза модели: ${id}`
  );
}
export const reasons: Record<string, string> = {
  research_model_unvalidated:
    "Исследовательская модель: диагностический вывод пока не разрешён",
  unsupported_crop_or_organ:
    "Культура или орган растения не поддерживается этой моделью",
  crop_mismatch_or_insufficient_evidence:
    "Не хватает признаков выбранной культуры",
  low_confidence: "Недостаточно оснований для уверенного вывода",
  too_blurry: "Недостаточная резкость",
  too_dark: "Недостаточное освещение",
  crop_mismatch: "Признаки не соответствуют выбранной культуре",
  insufficient_evidence: "Недостаточно признаков для вывода",
  ambiguous_candidates: "Несколько близких гипотез",
  unsupported_organ: "Этот орган растения не поддерживается",
  unsupported_view: "Этот ракурс не поддерживается",
  development_predictor: "Демонстрационный обработчик: диагноз не выполнялся",
  subject_not_visible: "Лист плохо виден",
};
