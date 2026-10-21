# AgroVision: архитектура Android online MVP

**Тема:** An Intelligent Computer Vision System for Plant Disease Diagnosis in Kazakhstan.

Этот документ описывает текущую реализацию. [DECISIONS.md](DECISIONS.md) сравнивает альтернативы; [требования](../planning/REQUIREMENTS_AND_TRACEABILITY.md) задают трассировку. [Implementation](../../development/IMPLEMENTATION.md), [verification](../../development/VERIFICATION.md), [mobile report](../../development/MOBILE_REPORT.md) и [измеренные модельные кейсы](../../evaluation/MEASURED_CASES.md) отделяют выполненные проверки от будущей работы. Foundation fixtures остаются синтетическими примерами.

## 1. Контекст и компоненты

Клиент — **Android React Native/Expo**. Пользователь входит, выбирает культуру, снимает/выбирает один лист, отправляет фото, получает предварительный результат, открывает свою историю и оставляет отзыв. Несохраненный draft существует в памяти. Web UI, persistent offline queue, on-device inference, farms/fields и экспертная annotation не реализованы.

Один Python backend codebase запускается двумя процессами:

- **FastAPI API** проверяет actor, schemas и ownership; обслуживает catalog, observations, photos, assessments и feedback.
- **Worker** берет durable job из PostgreSQL, вызывает независимый `ml/runtime` в supervised subprocess и сохраняет fenced terminal result.

PostgreSQL хранит связи, hashes, состояния, jobs и результаты. Private photos находятся в local ImageStore; Docker backend использует persistent volume. Model bundles — локальные операторские файлы, исключенные из Git. S3 пока является будущим adapter. Training/evaluation запускаются отдельно; runtime не импортирует FastAPI, ORM или training dependencies.

Редактируемые и экспортированные схемы: [контекст](diagrams/context.mmd), [компоненты](diagrams/components.mmd), [UML Use Case](diagrams/use_cases.puml), [описание экспорта](diagrams/README.md).

## 2. Фактическая структура

```text
apps/mobile/                         Android Expo UI, auth, transport, flow и tests
packages/api-client/                 generated OpenAPI types и thin client
server/agrovision/
  app.py, asgi.py                     HTTP routes и application entrypoint
  schemas.py, models.py              единые DTO и relational invariants
  config.py, db.py, identity/         конфигурация, sessions, проверенный actor
  catalog/, observations/, photos/   capabilities, история, upload/storage/cleanup
  assessments/                       enqueue, feedback, queue, worker, predictor supervisor
server/migrations/                   Alembic + immutable guards
ml/runtime/agrovision_runtime/       bundle admission, preprocessing, CPU ONNX, policy
ml/training/                         отдельный uv project: acquire/prepare/train/export
scripts/                             setup, dev token, OpenAPI, e2e, local runners
packages/api-client/openapi.json    generated contract
compose.yaml, Dockerfile             локальный backend profile
```

Один владелец меняет Pydantic/OpenAPI и migrations согласованно. TypeScript генерируется, а не редактируется вручную:

```bash
uv run python scripts/export_openapi.py
pnpm generate:client
```

Текущие команды установки, запуска и проверки находятся в [README](../../../README.md). `uv.lock` и `pnpm-lock.yaml` фиксируют serving/client dependencies; training имеет отдельный lockfile.

## 3. Наблюдение, upload и assessment

1. `POST /v1/observations` сохраняет crop/organ, captured_at с timezone и stable client UUID. Повтор идентичного semantic body возвращает исходную запись; измененный body с тем же UUID —409. `field_season_id` пока только null.
2. Upload проверяет actual JPEG/PNG decode, размер ≤10MiB/20MP, EXIF orientation и RGB; сохраняет normalized JPEG без metadata. Public hash относится к сохраненным bytes, input hash — к replay. Guard ограничивает projected resize до4MP/16384 pixels; два upload slots ограничивают память, saturation —429/Retry-After.
3. PostgreSQL reservation получает upload token/deadline и новый private object key. Decoder/storage IO идет вне row locks. Finalize берет observation→photo и проверяет tombstone, token и lease. Failed/expired reservation можно повторить с прежним client UUID; ready bytes/metadata immutable.
4. `POST /v1/assessments` принимает один `primary_photo_id` и UUID Idempotency-Key. Контекстные фото не агрегируются. Replay ищется до выбора текущей модели; key с другим body —409. Ownership/photo-ready и совместимость модели проверяются до enqueue.
5. Assessment с полным manifest/snapshot и job создаются **одной транзакцией**, затем API возвращает202. Replay возвращает тот же ID и текущее состояние200. Mobile polling читает queued/running/completed/failed.

Детали DTO: [API contract](../contracts/API_CONTRACT.md) и generated OpenAPI. Outcome не равен processing status: inconclusive — завершенный результат; инфраструктурный сбой —failed, а не «здоровое растение».

## 4. Durable queue и сохранность истории

Owner-scoped уникальности observation/photo/idempotency и composite foreign keys предотвращают повторный эффект и cross-owner/cross-observation привязку. Terminal assessment и pinned input/model защищены DB triggers. Feedback — отдельное пользовательское мнение, не ground truth и не перезапись результата.

Claim читает ограниченный список candidate IDs без locks, затем блокирует **observation→assessment→job** с SKIP LOCKED и повторно проверяет eligibility. Короткая транзакция назначает новый lease token/deadline и увеличивает attempts. Весь image/model IO и inference происходят после commit.

Defaults:3 attempts,60s lease,30s общий predictor timeout, bounded exponential backoff с jitter. Predictor — постоянный supervised process; timeout завершает его и сбрасывает cache. Finalize/retry/reclaim/delete используют общий lock order, DB clock и проверку текущего token/state/deadline. Исчерпанная последняя попытка терминализируется даже после смерти worker.

Result, terminal status и job completion коммитятся вместе. Гарантия — **at-least-once computation, один committed result**. Exactly-once вычисление не обещается. Actual SIGKILL/regression evidence перечислено в verification report.

## 5. Private storage и удаление

Download URL short-lived, relative и подписан; **дополнительно требуется bearer владельца** и повторная проверка tombstone. URL без bearer не дает другому actor доступа. Photo storage не смонтирован публичным static route.

Удаление немедленно скрывает observation, запрещает новые download/assessment/finalize и отменяет незавершенную работу. Blob cleanup выполняется отдельно bounded проходами. Leased uploads, новые immutable keys и компенсация защищают retries; streaming scan без полного directory buffer возвращается к late/orphan writes, включая blobs, появившиеся после прежней очистки.

Private photos, dataset originals, weights, credentials, signing keys и run outputs исключены из Git. Пользовательские фото автоматически не становятся training dataset. S3/presigned upload потребуют отдельной реализации immutable finalize/versioning и соответствующих тестов.

## 6. Identity и границы deployment

Owner ID вычисляется из проверенных issuer+subject. Production проверяет OIDC RS256 signature, issuer, audience, expiry и непустой subject; нужны HTTPS issuer/JWKS settings. Development может явно использовать operator-issued expiring HS256 bearer либо configured OIDC. Произвольный client user_id владельцем не становится.

Mobile содержит PKCE/AuthSession, access token в памяти, refresh credential в SecureStore и provider logout/revocation flow. **Реальная интеграция выбранного OIDC provider и rotation/revocation еще не проверена**; текущая локальная демонстрация использует development bearer. Production отказывается от development credentials и research/synthetic bundles.

Локальные systemd runners и Docker backend profile — альтернативы, не два одновременных процесса на одном порту. Доступ с телефона требует достижимого API origin; LAN origin demo APK фиксируется при сборке. Restricted production DB role, provider deployment и физическое устройство требуют собственных проверок.

## 7. Модельная граница и измеренная область

Bundle admission проверяет checksum, class order/export metadata, tensors, preprocessing, score space, policy и provenance. ORT получает exact validated artifact bytes; cache key включает artifact hash, режим и digest полного manifest. Cold initialization включен в общий timeout; warm session переиспользуется. Нет загрузки новых weights на каждый HTTP request.

Joint scores сохраняются **global_joint**, без crop renormalization. Quality detector отсутствует: quality=not_assessed. Research runtime всегда inconclusive; synthetic mode не генерирует диагнозов. Без validated production bundle catalog не обещает диагностику и enqueue возвращает503 model_unavailable; excluded maize —422 unsupported_crop.

Реальный local research bundle: EfficientNet-B0, PlantVillage + Wheat Leaf Dataset,3 культуры/9 source-label классов; held-out153 images, macro-F1 0.89559. Эти внутренние значения не устанавливают пригодность в Казахстане. [Measured cases](../../evaluation/MEASURED_CASES.md) отдельно показывает ошибки, paired comparison88 одинаковых SHA256 и35/153 raw photos, не проходящих geometry serving. Synthetic controls не являются настоящей OOD validation. Независимая external/local оценка и diagnostic policy еще нужны.

## 8. Следующие scoped increments

Persistent offline capture/upload queue с app files/SQLite и restart/reconnect/account-switch tests; reviewed diagnostic release и independent evaluation; source-aware annotation; localization. Farms/fields, S3, web и on-device inference остаются последующими решениями. Онлайн MVP не заявляет эти возможности реализованными.
