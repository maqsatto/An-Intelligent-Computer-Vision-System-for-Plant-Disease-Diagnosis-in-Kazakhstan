# AgroVision: проектная архитектура

**Официальная тема:** An Intelligent Computer Vision System for Plant Disease Diagnosis in Kazakhstan.

**Статус:** исторический проектный документ от 21 октября 2026. Он описывает исходные решения, а не текущее состояние реализации; актуальная реализация и измерения находятся в [development](../../development/IMPLEMENTATION.md).

**Текущий приоритет:** mobile на React Native; макеты/Figma создаются только для mobile. React web остается будущим клиентом общего API, без разработки его экранов и кода в данном пакете. Backend — Python/FastAPI. Кандидаты исследовательского пилота: `wheat`, `potato`, `tomato`; `maize` — возможное расширение после оценки данных. Кандидат культуры не равен подтвержденной поддержке модели.

## 1. Главный выбор

Строить **модульный монолит** с одним backend codebase, одной PostgreSQL и двумя исполняемыми процессами:

1. **FastAPI API:** учетная запись, каталог, наблюдения/поля, загрузки, постановка assessment, история и доступ.
2. **Inference worker:** берет устойчивую задачу из PostgreSQL, вызывает локальную библиотеку `ml/runtime`, сохраняет версионированный результат.

Фотографии и модельные bundles находятся в приватном S3-совместимом объектном хранилище. В PostgreSQL — владельцы, связи, состояния, задания, результаты и метаданные версий. Worker не является отдельным сетевым ML-микросервисом: два процесса используют одни прикладные модули и миграции. Training/evaluation запускаются отдельно от serving.

Это проектный выбор под команду из двух студентов: меньше распределенных протоколов и эксплуатационных зависимостей, при этом CPU inference не обязан занимать процесс HTTP API. FastAPI рекомендует рассматривать отдельные инструменты обработки для тяжелых независимых вычислений; его `BackgroundTasks` не используется как гарантия сохранности assessment [S1].

Редактируемые схемы: [контекст](diagrams/context.mmd), [компоненты](diagrams/components.mmd), [UML Use Case](diagrams/use_cases.puml). Альтернативы разобраны в [DECISIONS.md](DECISIONS.md).

## 2. Путь одного наблюдения

Пользователь выбирает поддерживаемую культуру, делает фото листа и сохраняет наблюдение. После проверки upload файл получает состояние `ready`. Запрос на assessment указывает **один `primary_photo_id`**; сервер фиксирует культуру, фото, модель и decision policy, затем атомарно создает assessment и job. Клиент получает ID, опрашивает состояние и показывает результат.

Дополнительные фото могут сохраняться как контекст наблюдения, но **не объединяются моделью и не влияют на assessment v1**. Для другого основного фото или новой модели создается отдельный assessment. Первый ML-сценарий — одно основное видимое состояние листа; смешанные поражения и разные органы требуют отдельной разметки и исследования.

Обработка: `queued → running → completed` либо `failed`. Внутренний retry может вернуть job к ожиданию; клиентский контракт остается простым. При `completed` outcome имеет ровно одно из значений: `predicted`, `inconclusive`, `unsupported_input`, `retake_photo`. Подробный контракт и примеры — [API_CONTRACT.md](../contracts/API_CONTRACT.md).

`inconclusive` — результат оценки, а не HTTP 500. Ошибка инфраструктуры не должна отображаться как «болезнь не обнаружена». Здоровый класс означает отсутствие поддержанного видимого поражения на данном фото в пределах изученной задачи; он не доказывает здоровье всего растения.

## 3. Границы модулей

| Модуль | Что ему принадлежит | Что он не должен присваивать |
|---|---|---|
| `identity` | Current actor, пользователи и сессии, интеграция с выбранным auth | Решения об истинности ML-диагноза |
| `catalog` | Stable crop/condition IDs, пары «культура–состояние», подписи и справка | Непроверенная поддержка любого растения |
| `farms` | Ферма, поле, сезон, культура сезона | Прогноз распространения инфекции без отдельной задачи |
| `observations` | Событие съемки, метаданные, photo upload lifecycle, собственная история | Изменение старого prediction после новой разметки |
| `assessments` | Создание запроса, idempotency, job/lease, модельная версия, решение и result | Training в HTTP-процессе |
| `feedback` | Пользовательский отзыв и отдельно проверенная annotation | Автоматическое превращение отзыва в ground truth |
| `ml/runtime` | Manifest validation, preprocessing, ONNX execution, postprocessing | FastAPI, ORM, бизнес-доступ к чужим объектам |
| `ml/training` | Dataset manifests, splits, baseline, train/evaluate/export | Незаметное изменение модели в production |

Внутри backend feature сначала достаточно `router.py`, `schemas.py`, `service.py`, `models.py`. Router проверяет вход и вызывает прикладной service; service задает транзакцию и бизнес-правила. Репозиторий или `Protocol` добавляются на реальной границе, например `ImageStore` и `Predictor`. Не создавать интерфейс для каждой функции или дублирующий слой объектов без задачи.

API и worker переиспользуют assessment service. Модули обращаются к небольшим публичным функциям соседнего модуля, а не к его HTTP router. Общий `core` содержит только конфигурацию, DB sessions, общие ошибки и actor context; это не место для всей бизнес-логики.

## 4. Структура monorepo

Это целевая карта, не указание немедленно создать пустые папки или заменить существующий полезный код.

```text
agrovision/
  apps/
    mobile/                    React Native / Expo; текущий первый клиент
    web/                       будущий React-клиент, сейчас только архитектурный план
  packages/
    api-client/                generated OpenAPI types + thin client
    shared/                    pure TS helpers, messages, tokens по мере использования
  server/
    pyproject.toml
    src/agrovision/
      api.py
      worker.py
      core/
      modules/
        identity/
        catalog/
        farms/
        observations/
        assessments/
        feedback/
      adapters/
        object_store.py
        predictor.py
    migrations/
    tests/
  ml/
    runtime/
      pyproject.toml
      src/agrovision_inference/
        manifest.py
        preprocess.py
        predictor.py
        postprocess.py
      tests/
    training/
      pyproject.toml
      uv.lock
      src/
      configs/
      data_manifests/
      reports/
  contracts/
    openapi.json               генерируется из реализованных FastAPI schemas
    examples/
  infra/
    compose.yaml
    Dockerfile.api
    Dockerfile.worker
  docs/
  pnpm-workspace.yaml
  pnpm-lock.yaml
  package.json
  pyproject.toml               uv workspace: server + ml/runtime
  uv.lock
```

pnpm имеет встроенные workspaces; `workspace:` делает локальную зависимость явной [S2]. Expo поддерживает monorepo и автоматическую настройку Metro; совместимые версии Expo/React/React Native выбираются вместе, без случайных дубликатов native packages [S3]. Nx/Turbo не требуются до конкретной проблемы со сборкой/оркестрацией.

uv workspace объединяет совместимые Python-пакеты одним lockfile [S4]. Training можно оставить отдельным uv-проектом, чтобы CUDA/training dependencies не становились условием запуска API. Реальные веса и полные датасеты находятся в artifact/data storage, а в Git — manifests, конфигурации, исходники и разумные small fixtures. Доступные лицензии определяют, какие исследовательские данные разрешено распространять.

Между клиентами разделяются API types/client, pure logic и согласованные strings/tokens. Web DOM и native components остаются своими. Token storage, camera, file system и offline persistence — платформенные адаптеры. Не импортировать `window`, DOM или native SDK в общий domain/API package.

## 5. Данные и инварианты

| Сущность | Основные данные / инвариант |
|---|---|
| `User`, `RefreshSession` | Собственный actor, срок/отзыв сессии; сырые refresh-секреты не хранить вместо предусмотренного механизма защиты |
| `Farm` | Имя и владелец; регион при наличии |
| `Field` | Ферма, имя участка, необязательные приблизительные координаты |
| `FieldSeason` | Поле, сезон/период, заявленная культура и необязательный сорт |
| `Observation` | Owner, client UUID, capture time, crop, organ, notes, optional field season, source/provenance |
| `Photo` | Observation/owner, client UUID, private object key, hash, MIME/dimensions, upload state, purpose |
| `Crop`, `Condition`, `CropCondition` | Канонические IDs и пары; одинаковое разговорное название болезни не объединяет разных хозяев автоматически |
| `Assessment` | Observation + ровно одно primary photo, snapshot crop, pinned model/policy, processing state |
| `AssessmentJob` | Attempts, available time, lease token/deadline, bounded retry metadata |
| `AssessmentResult` | Один immutable result на assessment; outcome/reasons/candidates/score kind/quality |
| `ModelVersion` | Bundle hash, class map, contracts, evaluation references; неизменяемая версия |
| `Feedback` | Мнение пользователя о результате |
| `Annotation` | Референсная метка, reviewer/source/verification level; отдельна от prediction |

На первом этапе граница доступа — `owner_user_id`; enterprise tenancy не требуется. Если позже подтвержден совместный доступ к ферме, добавить ограниченную membership-модель отдельным решением. Все вложенные ссылки проверяют владельца/разрешение: чужой photo ID нельзя прикрепить к своему observation или assessment.

Наблюдение, оценка модели и референсная разметка не взаимозаменяемы. Новая модель создает новую оценку; новый expert label не переписывает старый результат. Изменение культуры нового `FieldSeason` не меняет прежнюю историю.

Быстрый capture разрешен без фермы/поля. Для локального исследования полезны group IDs растения/поля/сессии съемки, source, дата/регион если известны, условия получения и уровень проверки labels. Эти метаданные нужны для групповых split и оценки domain shift. Местоположение в Казахстане само по себе не определяет болезнь.

## 6. Устойчивая очередь и идемпотентность

PostgreSQL подходит как первая durable queue для одного типа тяжелого задания; документация прямо указывает queue-like consumers среди применений `SKIP LOCKED` [S5]. Сам SQL-примитив не реализует полный протокол надежности.

1. API проверяет actor и schema запроса; для idempotency вычисляет hash нормализованных клиентских полей.
2. Уникальность: `(owner_user_id, operation, idempotency_key)`. Тот же ключ/тело возвращает исходный assessment. Другие semantic fields с тем же ключом дают `409`. Существующий ключ проверяется до выбора нового active model и новых resource/preflight-проверок, чтобы retry не сменил модель. Replay не восстанавливает удаленный ресурс: для собственного удаленного observation возвращается `resource_deleted`, без новых side effects.
3. Для нового ключа проверяются принадлежность/готовность фото, его связь с observation и отсутствие удаления; выбирается совместимая версия. В одной транзакции создаются idempotency record, assessment с точными версиями и job. `202` возвращается после commit.
4. Worker короткой транзакцией выбирает ready job `FOR UPDATE SKIP LOCKED`, увеличивает attempt и устанавливает новый случайный lease token/deadline. После commit DB-lock освобожден.
5. Загрузка image/model и inference происходят вне DB-транзакции. Timeout ограничен; lease превышает время задачи либо продлевается heartbeat.
6. Финальная транзакция блокирует ту же job row либо выполняет атомарный compare-and-set по `job_id + lease_token + running + lease_until > now()`. Проверка token отдельным незаблокированным `SELECT` недостаточна. При несовпадении/истекшем lease транзакция не сохраняет результат. Под тем же согласованным порядком блокировок проверяется, что observation не удалено; result с unique `assessment_id`, завершение assessment и job фиксируются вместе. Старый worker с устаревшим token не может записать или перезаписать result. Heartbeat также меняет deadline только при совпадении текущего token; finalize, reclaim и deletion должны иметь тестируемую синхронизацию.
7. Expired lease делает job доступным для повторного claim. Временный storage/network сбой получает bounded exponential backoff с jitter; поврежденный вход или несовместимый bundle не повторяются бесконечно. После лимита — `failed` с понятным code.

Гарантия: **at-least-once execution, один committed result для одного запроса**. Exactly-once computation не обещается: worker может умереть после вычисления до commit, и повтор безопасно пересчитает результат.

Если в будущем вместо DB queue используется отдельный broker, нужен transactional outbox либо другой явно проверенный механизм согласования DB commit и publish. Redis сам по себе не устраняет dual-write race. Если свежий репозиторий уже содержит надежную очередь, ее не следует заменять только ради соответствия этому черновику.

## 7. Upload и object storage

Начальный вариант — bounded multipart upload через API. Предлагаемые лимиты: JPEG/PNG, ≤10 MiB и ≤20 мегапикселей, с понятным отказом. Проверять декодирование, фактический формат и размеры; нормализовать orientation/RGB и удалить ненужные метаданные. Native-клиент может преобразовать HEIC до поддержанного формата. Лимиты являются проектными настройками, подлежащими проверке на реальных фото.

`Photo` проходит `pending → ready` либо `failed`. Транзакцию DB не держать открытой на время upload. PostgreSQL и S3 не образуют одну атомарную транзакцию: нужны уникальные keys, состояния, компенсация и cleanup старых partial/orphan uploads. Assessment принимает только `ready` photo.

Не хранить base64-фото в бизнес-таблице и не полагаться на ephemeral filesystem контейнера. Сохранять private object key и content hash. Для просмотра API после авторизации выдает short-lived URL. Удаление блокирует новые чтения/URL и финализацию еще работающего assessment; cleanup удаляет объекты. Уже выданная URL истекает по TTL.

Direct presigned upload — возможная последующая оптимизация с create/finalize и server-side validation. S3 URL допускает повторное использование до expiry и запись по тому же key может заменить объект [S6]. Поэтому после finalize продвигать проверенный input на отдельный immutable final key либо обеспечивать version-specific immutability. Иначе фото способно измениться между проверкой и inference.

## 8. Контракт модельного артефакта

Сервер выбирает совместимый bundle по заявленной культуре и manifest. Это локальная граница `Predictor`/`ModelSelector`, допускающая общий классификатор или позднее crop-specific модели без изменения mobile API. Список поддержанных классов получается из данных и оценки, а не из численности культур в презентации.

Минимальный bundle:

- `model.onnx`, checksum и runtime/opset expectations;
- `manifest.json`: version, supported crop/organ/class IDs, порядок class indices, input/output tensor names/shapes/dtypes, `output_semantics` и `score_space`;
- спецификация/version preprocessing: orientation, RGB, resize/crop/interpolation, scale/normalization;
- postprocessing/decision-policy version, score transformation, calibration reference если есть, validation-derived thresholds;
- train dataset/split manifest hashes, code commit/config, evaluation/model-card references;
- parity fixtures или их manifest для сравнения export и исходного framework.

Release validation проверяет также status и совместимость decision policy с score space; при заявленной calibration — соответствующий artifact/hash. Незаданные или null thresholds не означают нулевой порог/разрешение любого prediction: такой bundle остается только в исследовательской процедуре и не активируется для пользовательских predicted outputs. Проверенный bundle загружается до readiness worker; один ONNX session переиспользуется. Cache key — checksum. Download идет во временный путь, затем hash verification и atomic rename. Веса не скачиваются и не создают новую session на каждый запрос. Concurrency и число ONNX threads измеряются на целевом CPU/RAM, чтобы несколько процессов не размножили thread pools сверх ресурса.

CPU ONNX — исходный вариант; официальная документация содержит Python CPU runtime [S7]. PyTorch serving остается допустимым fallback, если экспорт выбранного baseline не дает эквивалентный результат. Нельзя ради ONNX незаметно менять preprocessing/classes. GPU/native inference — отдельная последующая оценка. ONNX Runtime для React Native существует [S8], но совместимость модели/operator set, память, build и latency проверяются на реальных устройствах.

Для joint crop-condition baseline сохраняются global scores: `score_space: global_joint`. Нельзя молча отбросить остальные культуры и перенормировать слабое свидетельство выбранной культуры до высокой уверенности. При расчете crop-conditional scores обозначать `score_space: crop_conditional`, сохранять исходную массу вероятности выбранной культуры и проверять crop mismatch/gating отдельно; calibration и thresholds относятся к конкретному пространству scores. Model score — не автоматически вероятность правильного диагноза. Abstention пороги выбираются на validation; неподдержанные и неподходящие изображения тестируются отдельно. Общая softmax-модель может быть уверена на чужом входе; архитектура предусматривает `inconclusive`, но не объявляет проблему open-set recognition решенной.

## 9. Auth, доступ и mobile offline

Выбрать одну проверенную auth/OIDC-интеграцию или поддерживаемую библиотеку. Не проектировать собственный криптографический протокол. При выбранной схеме access/refresh:

- Native access token — память; refresh credential — SecureStore/keychain. AsyncStorage не использовать для токенов: официальные рекомендации React Native выделяют его как unencrypted storage [S9].
- В будущем web access token — память, refresh — `Secure`/`HttpOnly` cookie с соответствующими SameSite/Origin/CSRF правилами. Same-origin размещение упрощает cookie/CORS.
- На сервере refresh session отзываема; rotation/reuse handling соответствует выбранной реализации. Клиент сериализует одновременные refresh. Logout очищает scoped caches и приостанавливает drafts этого аккаунта.
- Каждый read/write/download/export проверяет scope. Authenticated actor не имеет доступа ко всем объектам; OWASP требует проверять разрешения для каждого запроса и ресурса [S10].

Offline mobile означает **сохранить и отправить позже**. Фото копируется в persistent app files; SQLite хранит metadata/queue/stable IDs. Не рассчитывать, что temporary camera URI переживет перезапуск. Состояния локального draft отделены от server processing: `local`, `uploading`, `uploaded`, `assessment_queued`, `completed`, `needs_attention`.

Resume происходит при старте/foreground, восстановлении связи и ручном retry. Потерянный ответ API не порождает новый UUID. При смене account нельзя отправлять старый draft от имени нового пользователя. «Сохранено» показывается после сохранения файла и записи очереди. Background completion после убийства приложения ОС не обещается; on-device inference не является частью draft-функции.

## 10. Минимальная проверка основы и порядок внедрения

Исходный план технической проверки:

1. Каталог и mobile photo flow с общим контрактом; synthetic fixture четко обозначается и не выдается за ML performance.
2. Реальный baseline bundle, preprocessing/export parity и immutable results.
3. Идемпотентность при потерянном ответе, worker kill/restart, fencing, bounded retries.
4. Два пользователя и отрицательные проверки чужих IDs; upload lifecycle и deletion race.
5. Native build, сохранение draft, restart/reconnect/account switch.
6. Локальная/внешняя оценка по фиксированным группам данных; архитектура расширяется по результатам, а не по произвольному списку технологий.


Требования и методы проверки: [REQUIREMENTS_AND_TRACEABILITY.md](../planning/REQUIREMENTS_AND_TRACEABILITY.md). Команды запуска появятся только после реальной реализации.

## Источники платформенных фактов

Рекомендации и tradeoffs выше — инженерные выводы для этого проекта. Документация подтверждает отдельные возможности/ограничения платформ; она не предписывает именно эту архитектуру. Проверено 21 октября 2026; конкретные версии надо фиксировать при начале реализации.

- **S1.** [FastAPI: Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).
- **S2.** [pnpm: Workspaces](https://pnpm.io/workspaces).
- **S3.** [Expo: Work with monorepos](https://docs.expo.dev/guides/monorepos/).
- **S4.** [uv: Workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/).
- **S5.** [PostgreSQL: SELECT / locking clause](https://www.postgresql.org/docs/current/sql-select.html).
- **S6.** [AWS S3: Presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html).
- **S7.** [ONNX Runtime: Python](https://onnxruntime.ai/docs/get-started/with-python.html).
- **S8.** [ONNX Runtime: React Native](https://onnxruntime.ai/docs/get-started/with-javascript/react-native.html).
- **S9.** [React Native: Security](https://reactnative.dev/docs/security) и [Expo SecureStore](https://docs.expo.dev/versions/latest/sdk/securestore/).
- **S10.** [OWASP: Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
