# AgroVision: технические решения и альтернативы

**Статус:** исторический проектный документ от 21 октября 2026. Он описывает исходные решения, а не текущее состояние реализации; актуальная реализация и измерения находятся в [development](../../development/IMPLEMENTATION.md).

Критерии: понятность для двух разработчиков, связь с ML на Python, стабильность контрактов/истории, восстановление после обрыва связи, небольшое число эксплуатационных компонентов и возможность независимо проверить качество. Численные benchmark-преимущества без измерений не заявляются.

## ADR-01. Backend-платформа

**Требования:** FR-02–07/09/14/16; NFR-03/04/06/10. Нужно REST API для mobile и будущего web, связанное с Python ML/runtime, объектным хранилищем и PostgreSQL.

| Вариант | Когда рационален | Цена / ограничение в AgroVision |
|---|---|---|
| **FastAPI + Pydantic + SQLAlchemy/Alembic** | Небольшое Python API с явными schemas/services; удобно держать serving и ML-adapter в одном языковом окружении | Auth, операции с данными и админ-процедуры надо собрать осознанно; сам framework не создает durable queue |
| **Django + Django REST Framework** | Много административного CRUD, пользователей и контентных процессов; DRF предоставляет serializers, permissions и REST tooling | Более широкий framework, чем требует первый photo flow; может быть предпочтителен, если экспертный административный интерфейс станет главной частью проекта |
| **NestJS / Node.js + отдельный Python runtime** | Команда предпочитает TypeScript на backend; нужны структурированные модули Node-приложения | В этом проекте увеличивает число языковых/процессных границ между бизнес-API и существующим ML-стеком; преимущества надо сопоставлять с этим расходом |

**Выбор:** FastAPI как модульный монолит. Он соответствует желанию пользователя и позволяет вызывать Python runtime локально из worker. Это не утверждение, что FastAPI всегда быстрее/лучше других frameworks. DRF и NestJS — полноценные альтернативы, а не искусственно слабые варианты.

**Последствия:** проектировать auth и DB transactions явно; генерировать OpenAPI/TS из единых schemas; тяжелый inference выносить в worker.

**Основание:** [FastAPI](https://fastapi.tiangolo.com/), [DRF](https://www.django-rest-framework.org/), [NestJS](https://docs.nestjs.com/). Решение о меньшей цене интеграции — инженерный вывод для данной команды, не benchmark.

## ADR-02. Границы приложения

**Требования:** FR-03–07/09/14; NFR-03/06/10. Нужны понятные feature boundaries, общий data model и возможность перезапускать CPU worker без потери заданий.

| Вариант | Преимущество | Цена / ограничение |
|---|---|---|
| **Модульный монолит, API + worker из одного codebase** | Простые локальные вызовы и единые миграции; разделение CPU-работы и HTTP; одна транзакция для assessment/job | Надо удерживать границы модулей и не превращать общий `core` в склад логики |
| **Один неразделенный HTTP-процесс со всей логикой** | Минимальный первый локальный эксперимент | CPU/load/restart связаны с HTTP; бизнес-правила, inference и storage быстро переплетаются; долговечность фоновых действий не возникает автоматически |
| **Отдельные API, ML, catalog, history services** | Независимая эксплуатация и масштабирование действительно самостоятельных частей | Для двух студентов добавляет сетевые контракты, deployment, диагностику и согласование данных, пока нет соответствующей организационной потребности |

**Выбор:** первый вариант. `identity`, `catalog`, `farms`, `observations`, `assessments`, `feedback` — модули, а не отдельные deployment units. `ml/runtime` — библиотека worker. Training/evaluation остаются offline-инструментами.

**Когда пересмотреть:** устойчиво измеренный bottleneck, отдельная команда/эксплуатационный цикл либо существенно отличающиеся требования к отдельной части. Большой размер файла сам по себе решается модульным рефакторингом, а не обязательным сервисом.

**Основание:** границы и стоимость — архитектурное рассуждение; необходимость отделять тяжелую независимую работу согласуется с [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).

## ADR-03. Метаданные и фото

**Требования:** FR-03–06/09/10/14/15; NFR-03/04/05/06. Нужны связи владельцев/наблюдений/сезонов/результатов, immutable image/model artifacts и согласованная очередь.

| Вариант | Преимущество | Цена / ограничение |
|---|---|---|
| **PostgreSQL + private S3-compatible storage** | Реляционные связи и транзакции для metadata/job, отдельно управляемые image/model bytes | DB и storage не имеют общей транзакции: требуются upload states, immutable keys и cleanup |
| **PostgreSQL с image/model bytes в таблицах** | Один механизм транзакций/backup для данных | Для данного потока увеличивает размер БД/backup и связанность metadata с тяжелыми артефактами; перед выбором нужно измерить реальный объем |
| **SQLite + локальные файлы** | Очень простой local prototype и хороший формат данных на мобильном устройстве | Для общего server API+worker придется отдельно продумать конкурентную запись, хранение и обслуживание; выбранный протокол PostgreSQL `SKIP LOCKED` не переносится автоматически |

**Выбор:** PostgreSQL для server metadata/jobs, private S3-compatible storage для фото/моделей. SQLite используется для **локальной mobile draft queue**, где решает другую задачу. Нельзя описывать SQLite как заведомо непригодную для любого web: ее документация прямо содержит server/web сценарии; выбор PostgreSQL здесь связан с общим серверным доступом и конкретной queue-моделью.

**Последствия:** blob key и checksum вместо публичного URL; short-lived URLs после авторизации; `pending/ready/failed` upload lifecycle; регулярная уборка незавершенных uploads. Presigned direct upload возможен позже, с защитой готового input от повторной перезаписи по временной URL.

**Основание:** [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html), [S3 presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html), [SQLite: Appropriate uses](https://sqlite.org/whentouse.html). Оценка цены хранения — проектный tradeoff, а не результат замера.

## ADR-04. Выполнение assessment и взаимодействие API/worker

**Требования:** FR-05/06/14; NFR-02/03/06. Mobile может потерять ответ; worker может остановиться; система должна сохранить смысл запроса и один итоговый результат.

| Вариант | Преимущество | Цена / ограничение |
|---|---|---|
| **Dedicated worker + PostgreSQL job table** | Assessment и job создаются одной транзакцией; нет отдельного broker для одного типа задач | Lease, fencing, bounded retry и cleanup надо явно реализовать и проверить; не подходит как бесконтрольная замена полноценной workflow-платформе |
| **Celery + Redis/RabbitMQ** | Готовые worker, routing/scheduling/workflow/monitoring возможности | Еще один сервис; DB commit и broker publish требуют outbox/согласования; idempotency и корректность side effects все равно нужны |
| **Синхронный inference в запросе / in-process background callback** | Быстрый первый local proof of concept | Зависимость от request/process lifetime; устойчивость, recovery и распределение нагрузки ограничены; `BackgroundTasks` сам по себе не является durable queue |

**Выбор:** узкая PostgreSQL очередь для одного типа inference jobs и отдельный worker. HTTP polling достаточно для статуса одного фото. При появлении кода проверить протокол полностью: claim короткой транзакцией, inference вне lock, точный model pinning, уникальный result, lease fencing, retries, terminal failure.

**Гарантия:** at-least-once выполнение, один committed result на assessment. Не обещать exactly-once вычисление. Для replay сохранять idempotency scope/body hash; иной body с тем же key — `409`.

**Когда пересмотреть:** потребность в большом числе task types, сложном scheduling, мониторинге нескольких worker pools или измеренном queue bottleneck. Уже работающую зрелую очередь в свежем проекте можно сохранить.

**Основание:** [PostgreSQL locking clause](https://www.postgresql.org/docs/current/sql-select.html), [Celery introduction](https://docs.celeryq.dev/en/stable/getting-started/introduction.html), [FastAPI background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).

## ADR-05. Формат и место inference

**Требования:** FR-07/14/16; NFR-01/02/06/08. Требуются воспроизводимый результат, понятная версия и оцененная скорость на доступном оборудовании.

| Вариант | Преимущество | Цена / ограничение |
|---|---|---|
| **Server CPU + ONNX Runtime** | Единый runtime для клиентов; модель обновляется централизованно; serving отделен от training framework | Нужны export compatibility и parity tests; latency/RAM измеряются, а не предполагаются |
| **Server CPU/GPU + PyTorch** | Можно сохранить исходный model graph и preprocessing, если ONNX export проблемен | Framework/training зависимости могут увеличивать environment; GPU serving — дополнительный ресурс, его необходимость надо доказать |
| **On-device ONNX в React Native** | Возможна оценка без сети после загрузки модели | Проверка operator/build/device compatibility, памяти, скорости, обновлений bundle и parity на каждом целевом типе устройств; это отдельный объем |

**Выбор:** начать с CPU ONNX, если экспорт сохраняет требуемое поведение; при доказанной проблеме использовать PyTorch serving как осознанный fallback. Выбор architecture сети делает ML-эксперимент, а не этот ADR. Native offline в первой версии — draft/upload queue, не inference.

**Последствия:** versioned bundle содержит labels/preprocess/policy/score-space/metrics references; release-проверка отклоняет неготовую policy и null thresholds вместо permissive defaults; worker кеширует по checksum и загружает session заранее; измерять cold/warm время, CPU/RAM и p95, без обещаний скорости по названию технологии.

**Основание:** [ONNX Runtime Python](https://onnxruntime.ai/docs/get-started/with-python.html), [ONNX Runtime React Native](https://onnxruntime.ai/docs/get-started/with-javascript/react-native.html). Наличие native-пакета не является доказательством работоспособности конкретной модели.

## ADR-06. Monorepo и совместное использование кода

**Требования:** FR-01–07/09; NFR-06/08/10. Одна команда изменяет API, mobile и ML; будущий web должен получать тот же контракт без копирования интерфейсов вручную.

| Вариант | Преимущество | Цена / ограничение |
|---|---|---|
| **pnpm workspaces + uv projects в одном Git repo** | Общие атомарные изменения contract/types; простое ownership; отдельные Python training/runtime environments | Нужно аккуратно закреплять версии native dependencies и Python workspace boundaries |
| **Monorepo с дополнительным Nx/Turbo orchestration** | Имеет смысл, когда задачи сборки/cache/dependency graph уже создают заметную проблему | Дополнительные настройки и слой инструмента без подтвержденной потребности первой версии |
| **Отдельные repos для mobile/API/ML** | Независимые циклы версий при независимых командах | Для двух участников добавляет публикацию/синхронизацию контрактов и связанные изменения сразу в нескольких repos |

**Выбор:** первый вариант. Общий TS-код — generated API types/client и небольшие pure helpers/tokens. DOM/native UI не объединяется автоматически. Адаптеры camera/storage/auth остаются платформенными. Не создавать web-дизайн или пустое web-приложение в текущей mobile-задаче.

**Последствия:** один root script для проверки, lockfiles, простая CI; `workspace:` для локальных TS dependencies; отдельный training uv.lock допустим. При большом реальном времени сборки решение можно пересмотреть.

**Основание:** [pnpm workspaces](https://pnpm.io/workspaces), [Expo monorepos](https://docs.expo.dev/guides/monorepos/), [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/). Цена дополнительной orchestration — проектная оценка, а не benchmark инструментов.

## Следующие проверяемые решения

Перед первой реализацией зафиксировать поддерживаемые class pairs по аудиту данных, целевые mobile OS/устройства, конкретную auth integration и параметры deployment CPU. После baseline — thresholds, разрешенную область применения и измеримый performance budget. До получения evidence нельзя выдавать произвольные значения за измеренные или согласованные.

Источники проверены 21 октября 2026. Сведения о ценах/конкретных облачных тарифах не использованы; выбор поставщика storage/hosting остается открытым. Связи с требованиями: [REQUIREMENTS_AND_TRACEABILITY.md](../planning/REQUIREMENTS_AND_TRACEABILITY.md).
