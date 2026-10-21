# AgroVision API v1 — контракт и границы реализации

Работающий FastAPI API и Android-клиент используют [сгенерированный OpenAPI](../../../packages/api-client/openapi.json) и [TypeScript schema](../../../packages/api-client/src/schema.d.ts). Они определяют точные текущие endpoints, DTO и коды ответов. Этот текст описывает семантику и целевые расширения; при расхождении wire-format приоритет имеет сгенерированный контракт.

[examples.json](examples.json) — синтетические проектные fixtures, а не ответы исследовательской модели. Текущие поведенческие уточнения и исполняемые проверки: [IMPLEMENTATION](../../development/IMPLEMENTATION.md), [VERIFICATION](../../development/VERIFICATION.md).

Текущий scope: owner-scoped observations/photos/assessments/history/feedback, private local ImageStore и отдельный PostgreSQL worker. `field_season_id` принимает только null; farms/seasons и экспертные annotations не реализованы. Web и persistent offline queue — следующий этап. Реальный research bundle возвращает кандидатов с глобальными scores и всегда `inconclusive`; production diagnostic bundle пока не допущен. OIDC token validation и клиентский PKCE реализованы, но provider-backed end-to-end приёмка остаётся отдельной проверкой.

## 1. Правила

- Базовый path: `/v1`; JSON — UTF-8; server timestamps — ISO 8601 в UTC.
- Идентификаторы ресурсов — UUID strings. Идентификаторы культуры/состояния/класса — стабильные catalog strings, не локализованный текст и не индекс нейросети.
- Кандидаты пилота: `wheat`, `potato`, `tomato`; `maize` — optional. Реальный каталог возможностей определяется проверенными model manifests. Кандидат не становится `can_assess: true` только от присутствия в документе.
- Каждый assessment использует ровно **один `primary_photo_id`**. Context photos относятся к observation, но не сливаются и не интерпретируются этим assessment v1.
- Все личные объекты авторизуются по actor/owner scope. `user_id`, присланный клиентом, не определяет владельца; owner выводится из проверенной сессии.
- Для personal endpoints используется выбранная bearer/session integration. `/v1/me` возвращает текущий actor. Login/refresh DTO зависят от выбранного auth-провайдера/библиотеки и не должны изобретаться из этого документа. Mobile refresh storage и будущие web cookie rules описаны в [архитектуре](../architecture/SYSTEM_DESIGN.md).
- Новые поля добавляются совместимо; breaking changes требуют следующей API version либо явной миграции клиентов. Клиент не должен crash из-за нового `reason_code`: показать общий безопасный текст с логированием неизвестного кода.

## 2. Основные endpoints

| Метод и path | Запрос / назначение | Ответ и права |
|---|---|---|
| `GET /v1/catalog` | Версия каталога; культуры/органы/classes/support | `200`; публичные capabilities, без личных данных |
| `GET /v1/me` | Текущий actor | `200` либо `401` |
| `POST /v1/observations` | Metadata + stable `client_observation_id` | `201`; replay существующего своего client ID — `200`; измененный semantic body с прежним ID — `409` |
| `POST /v1/observations/{id}/photos` | Multipart file + `client_photo_id` + `purpose` | `201` после проверки/ready; replay — существующий photo; только свой observation |
| `GET /v1/photos/{id}/content-url` | Авторизованный просмотр | `200` с short-lived URL/expiry; owner check |
| `POST /v1/assessments` | `observation_id`, `primary_photo_id`; header `Idempotency-Key` | Первый запрос `202`; replay `200` с тем же assessment ID и текущим состоянием; owner check |
| `GET /v1/assessments/{id}` | Polling processing/result | `200`; только разрешенный assessment |
| `GET /v1/observations` | Cursor pagination; `crop_id`, `from`, `to`, optional `field_season_id` | `200` `{items,next_cursor}`; только собственная история |
| `GET /v1/observations/{id}` | Metadata, photos, assessment summaries | `200`; owner check |
| `POST /v1/assessments/{id}/feedback` | Полезность/предполагаемая ошибка, optional note | `201`; отдельная feedback-запись, prediction не меняется |
| `DELETE /v1/observations/{id}` | Удаление собственной записи | `202`: чтение/новая обработка блокируются, blob cleanup выполняется отдельно |

Следующий объем: farm/field/field-season CRUD; разрешенная экспертная annotation/import/export. Их схемы уточняются отдельными задачами без расширения основного capture flow. При activation проверяются status/совместимость decision policy, score space и calibration artifact, если заявлена calibration. Незаданные/null thresholds не превращаются в разрешающие defaults. Model activation и evaluation сначала доступны оператору как CLI-процедуры, а не как публичный upload executable-model endpoint.

## 3. Создание observation и загрузка photo

`ObservationCreate`:

| Поле | Тип | Правило |
|---|---|---|
| `client_observation_id` | UUID | Создается один раз при сохранении draft; сохраняется при всех retries |
| `crop_id` | string | Выбранная пользователем культура из каталога; запись может иметь `can_assess: false` |
| `organ` | string | Для первой конфигурации `leaf`; расширение требует оцененных данных |
| `captured_at` | ISO timestamp | Заявленное клиентом время съемки с offset; server сохраняет нормализованное время и происхождение |
| `field_season_id` | UUID или null | Необязательная ссылка на свой сезон |
| `notes` | string или null | Ограниченный текст, например до 1000 символов; лимит фиксируется в schema |

Создание без поля/фермы разрешено. Observation и photo можно сохранить **без assessment** для известной культуры каталога с `can_assess: false`, например для планируемой `maize`. Это запись наблюдения, а не поддержка диагностики. Неизвестный произвольный `crop_id` либо невалидный metadata organ отклоняется как `422 invalid_crop`/`invalid_organ`; client не изобретает новые стабильные IDs.

Проверка поддержки inference относится к `POST /v1/assessments`: неподдерживаемая культура дает `422 unsupported_crop`, без создания assessment/job. Если заявленная поддерживаемая культура позже расходится с фактическим изображением, принятый assessment может завершиться `inconclusive`; это другой случай, чем невалидный request.

`PhotoUpload`: multipart, `client_photo_id: UUID`, `purpose: primary | context`, один file. `purpose` помогает UI; фактический input определяет `AssessmentCreate.primary_photo_id`. У одного observation могут храниться контекстные снимки и снимки разных попыток, но один assessment не принимает массив `photo_ids`.

Предлагаемые ограничения: JPEG/PNG, ≤10 MiB, ≤20 MP; проверить фактические bytes/decoder, orientation, dimensions. Значение из MIME/расширения недостаточно. Фото получает `ready` только после успешной проверки и записи объекта. Ответ photo содержит `id`, `observation_id`, `purpose`, `status`, `media_type`, `width`, `height`, `sha256`; постоянный публичный URL не хранится.

Служебные upload states — `pending`, `ready`, `failed`; они не заменяют processing states assessment. Наличие pending photo в БД не означает, что можно поставить его в inference. Повтор upload с прежним client ID и иным content hash — `409`.

## 4. Создание assessment и идемпотентность

Тело:

```json
{
  "observation_id": "11111111-1111-4111-8111-111111111111",
  "primary_photo_id": "22222222-2222-4222-8222-222222222222"
}
```

Header: `Idempotency-Key: 33333333-3333-4333-8333-333333333333` — пример, не общий ключ для всех запросов. Реальное приложение создает отдельный UUID для одной намеренной оценки и сохраняет его через retry.

После проверки actor/schema сервер сначала разрешает уже существующий idempotency key. Для нового ключа проверяет, что оба объекта принадлежат actor, photo относится к указанному observation и `ready`. Из observation фиксируется `crop_id`/organ snapshot; проверяется поддержка и выбирается совместимая active model/policy. Наблюдение, сохраненное без анализа для неподдерживаемой культуры, само по себе не разрешает inference. Клиент не передает произвольный path/URL весов.

Уникальность idempotency задается owner + operation + key. Тот же ключ/semantic body возвращает прежний ID, даже если active model за это время сменилась. Иное тело с прежним ключом дает `409 idempotency_conflict`. Assessment и job создаются в одной DB-транзакции, после commit — `202`.

Replay существующего доступного assessment возвращает `200` с его актуальным представлением, header `Idempotency-Replayed: true`. Если собственное observation уже удалено, возвращается `409 resource_deleted`; replay не раскрывает удаленные данные и не восстанавливает их. Это явно принятая семантика данного контракта: одинаковый эффект и resource ID, а не обязательно побайтовое повторение первого ответа. Запланированная повторная оценка новым bundle использует **новый** key/assessment; старый result сохраняется.

## 5. Канонический `AssessmentRead`

| Поле | Тип / назначение |
|---|---|
| `id`, `observation_id`, `primary_photo_id` | UUID |
| `crop_id` | Snapshot заявленной культуры |
| `status` | `queued` / `running` / `completed` / `failed` |
| `model` | Pinned `version`, `artifact_sha256`, `preprocessing_version`, `decision_policy_version` |
| `result` | `AssessmentResult` при completed, иначе null |
| `error` | `ProcessingError` при failed, иначе null |
| `created_at` | UTC timestamp |
| `started_at` | UTC timestamp или null |
| `finished_at` | UTC timestamp у terminal state, иначе null |

Инварианты:

1. `queued`/`running`: `result == null`, `error == null`, `finished_at == null`.
2. `completed`: `result != null`, `error == null`, `finished_at != null`.
3. `failed`: `result == null`, `error != null`, `finished_at != null`.
4. `model` фиксирован при принятии job. Ошибка выбора/доступности модели до enqueue — HTTP error, а не assessment с выдуманной version.
5. Один `assessment_id` имеет один committed result; retries не создают новые результаты и не изменяют модель.

### `AssessmentResult`

| Поле | Значение |
|---|---|
| `outcome` | `predicted` / `inconclusive` / `unsupported_input` / `retake_photo` |
| `reason_codes` | Массив стабильных кодов, пустой допустим для обычного prediction |
| `prediction` | Один `Candidate` при predicted; null у других outcomes |
| `candidates` | До трех гипотез `Candidate`; пустой массив допустим. Это не подтвержденные сопутствующие болезни |
| `quality` | `{status: passed | warning | unusable | not_assessed, flags: string[]}` |
| `next_action` | `view_guidance` / `retake_photo` / `select_supported_crop` / `consult_expert` |

`Candidate`: `class_id`, `crop_id`, `condition_id`, `score`, `score_kind`, `score_space`. Для первоначального joint classifier `score_space: global_joint`; значения не перенормируются после фильтрации выбранной культуры. `crop_conditional` допустим только как явно другой output contract с собственной оценкой/calibration и сохранением исходной crop mass там, где она вычисляется. `score` может быть null, если для пользовательского вывода он не предусмотрен. Для softmax-модели `score_kind: model_score`; `calibrated_probability` допустим только после отдельной calibration-проверки и соответствующего manifest. UI не обязан показывать число. Raw/global и crop-conditional значения не сравниваются как одна шкала; decision policy и manifest фиксируют используемое пространство. Для «healthy» используется отдельный class/condition в поддержанном catalog, например `healthy_appearance`, с ограниченным смыслом.

`quality.status: passed` означает, что настроенные проверенные quality rules не заблокировали фото; это не универсальная гарантия правильности кадра или диагноза. Не все quality/OOD признаки обязательно реализуются в первом baseline.

## 6. Outcomes и примерные reason codes

| Outcome | Когда допустим | Пример reason / следующее действие |
|---|---|---|
| `predicted` | Есть допустимая гипотеза в поддержанной области и пройдена принятая decision policy | Показать предполагаемое состояние, справку и пределы вывода |
| `inconclusive` | Данных недостаточно, кандидаты близки или есть расхождение с заявленной культурой | `insufficient_evidence`, `ambiguous_candidates`, `crop_mismatch`; переснять/обратиться к эксперту |
| `unsupported_input` | После обработки вход обоснованно признан вне поддержанного scope | `unsupported_organ`, `unsupported_view`; выбрать подходящий сценарий/сделать фото поддержанного органа |
| `retake_photo` | Проверенная quality policy нашла исправимую проблему фото | `too_blurry`, `too_dark`, `subject_not_visible`; переснять |

Причины здесь — словарь контракта, не обещание уже реализованного детектора каждого случая. Если baseline не умеет надежно установить конкретную причину, используется более общее `inconclusive`, а не выдуманное уверенное объяснение.

Порог confidence не делает любой unfamiliar input распознаваемым как unknown. Политика и покрытие проверяются на validation и отдельном неподдержанном/неподходящем наборе; результат этой проверки входит в model report.

## 7. Ошибки HTTP и обработки

HTTP error body: `{code, message, details, request_id}`. Это проектный формат; не заявляется совместимость с отдельным error RFC без его реализации.

| HTTP | Примеры | Действие клиента |
|---|---|---|
| `401` | `authentication_required`, `session_expired` | Один управляемый refresh либо вход; не бесконечный retry |
| `403` | `role_not_permitted` для экспертной/операторской операции | Показать отсутствие разрешения |
| `404` | Нет доступного владельцу объекта | Не раскрывать существование чужого ID |
| `409` | `idempotency_conflict`, `photo_not_ready`, `resource_deleted` | Исправить состояние/ключ по смыслу; не создавать случайно duplicate |
| `413` | `image_too_large` | Уменьшить/переснять |
| `415` | `unsupported_media_type` | Преобразовать в поддержанный формат |
| `422` | `invalid_crop`, `unsupported_crop`, `invalid_organ`, `image_decode_failed` | Исправить ввод; automatic inference не запущен |
| `429` | `rate_limited` | Уважать `Retry-After` |
| `503` | `model_unavailable`, `storage_unavailable` до принятия job | Временная ошибка; bounded retry с тем же `Idempotency-Key`/client UUID. `request_id` в ошибке служит только для трассировки |

`ProcessingError` внутри уже созданного failed assessment: `{code, message, retryable}`. Примеры: `assessment_timeout`, `storage_unavailable`, `model_execution_failed`. `retryable: true` означает, что после исчерпания внутренних попыток можно предложить **осознанную новую попытку**; polling/replay прежнего assessment не оживляет его автоматически. Сообщение не содержит secrets/stack traces.

`POST /assessments` не должен вернуть `202`, если enqueue не зафиксирован. Если HTTP response потерялся после commit, прежний idempotency key восстанавливает ссылку на созданный assessment.

## 8. Mobile draft и связывание с экраном

| Локальное состояние / server state | Экран / пользовательский смысл |
|---|---|
| Draft `local` | Сохранено на устройстве; отправка при связи |
| Draft `uploading` | Загружается фото; доступно понятное состояние повтора |
| Server `queued` / `running` | Оценка принята / выполняется; один polling-loop с backoff |
| `completed.predicted` | Предполагаемое поддержанное состояние; версия/ограничения доступны |
| `completed.inconclusive` | Уверенного вывода нет; альтернативы не выдаются за подтверждение |
| `completed.unsupported_input` | Текущий режим не подходит для этого ввода |
| `completed.retake_photo` | Конкретная проверенная помощь по пересъемке |
| Server `failed` | Технический сбой; повтор по правилам, история сохраняет failure |

Polling прекращается на terminal state, при уходе со страницы/фонового состояния по выбранной политике и при отсутствии доступа. Интервалы/backoff — конфигурация; не создавать отдельный websocket-протокол для первой версии.

На стадии прототипа изображения, значения и результаты явно демонстрационные. Один основной снимок должен быть визуально выбран; context photos не создают впечатление, что модель агрегировала несколько кадров.

## 9. Проверка контракта при реализации

Синтетические примеры покрывают все четыре processing states и все четыре completed outcomes, request/replay/conflict, invalid upload и feedback. Они должны стать fixtures для проверки discriminated union, idempotency и клиентского отображения. Дополнительно обязательны реальные negative ownership tests, lease-fencing/restart tests, image decode limits и model parity.

Описанный JSON fixture — материал проектирования, а не автоматическое доказательство работы backend. Трассировка требований: FR-01–09/11–16, NFR-03–06/09–10 из [REQUIREMENTS_AND_TRACEABILITY.md](../planning/REQUIREMENTS_AND_TRACEABILITY.md).
