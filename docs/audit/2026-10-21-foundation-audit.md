# AgroVision — аудит рабочей папки и Foundation

Дата: 21 октября 2026, Asia/Aqtau. Область проверки: `/home/maqsatto/Documents/Diploma`; ограниченный поиск связанных файлов в Documents/Downloads. Это аудит и проектирование, не отчет о реализации.

## Источник запроса и документов

Пользовательский запрос прочитан из приложенного `Pasted text.txt`. Foundation — справочные проектные материалы. Вложенные CODEX_START_PROMPT и MAQSAT_ACTION_PLAN не выполнялись как новые команды. Старый Context ZIP обнаружен в Downloads, но не использован как состояние кода и не распаковывался.

Foundation скопирован без изменения исходников в [docs/foundation](../foundation/README.md).
SHA-256 исходного ZIP: `9ae311fe122d2cc682fa07f8bd095a8854b5c0fe30ae5fc964cfd3b33560bef7`.

Прочитаны README, PROJECT_PROPOSAL, SYSTEM_DESIGN, DECISIONS, REQUIREMENTS_AND_TRACEABILITY, API_CONTRACT, DATA_POLICY, TRAINING_AND_EVALUATION и MOBILE_PROTOTYPE; дополнительно examples.json и baseline_config.yaml. Независимый агент сверил требования/архитектуру/политику данных/ML; изменений он не делал.

## Фактическое состояние

| Объект | Наблюдение |
|---|---|
| Рабочая папка до работы | Пустая, включая скрытые файлы |
| Git root / branches / remotes / history | Отсутствуют; `git status --short` завершился 128: not a git repository |
| Незакоммиченные изменения | Git отсутствует; нельзя сообщать «чистая ветка». До работы файлов в папке не было |
| AGENTS.md | Не найден в рабочей папке и проверенных родительских каталогах |
| API / mobile / web | Исходников нет |
| Locks / workspace manifests / migrations / tests | Нет |
| Bundles / weights | В рабочей папке нет; ограниченный поиск *.onnx/*.pt/*.pth в Documents/Downloads ничего не нашел |
| Старый ZIP | Есть в Downloads; не доказывает существование актуального репозитория |
| YouTrack | Настоящие IDs и ссылка на проект не предоставлены; задачи/номера/ветки/коммиты не выдумывались |

Не утверждается, что на всем компьютере или в удаленном Git нет другого репозитория. Новый проект в текущей папке — явно обозначенное предположение для предлагаемой спецификации. Git init/commit/remote не выполнялись.

## Окружение

| Проверка | Получено |
|---|---|
| `python3 --version` | Python 3.14.8, системный |
| `uv python list --only-installed` | Доступны также 3.13.14, 3.12.13, 3.11.15 |
| `uv --version` | 0.12.1 |
| `node --version` / `npm --version` | v26.12.0 / 12.2.1 |
| `command -v pnpm` | Найден bundled fallback; версия/работоспособность для проекта пока не проверены |
| `docker info --format '{{.ServerVersion}}'` | 29.9.1, daemon доступен |
| `command -v psql adb emulator java` | Не найдены в PATH; это не полный аудит установленных SDK |
| `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader` | RTX 2060, 6144 MiB, driver 615.78.08 |
| `git --version` | 2.56.0 |

RTX 3050 Laptop на этом компьютере не обнаружена. GPU-обучение, CUDA inference и native Android build не запускались. Доступность Docker не подтверждает доступность конкретных образов, PostgreSQL schema или порта приложения.

## Что сохраняем

Весь Foundation сохранен как исходный reference, включая предупреждения о синтетических данных. Сохраняем словарь API, четыре processing state и четыре completed outcome, modular monolith, PostgreSQL jobs, pins/checksums и разграничение данных/feedback. Рабочих компонентов для переноса здесь нет. Существующей очереди/менеджера окружения проекта нет: миграция не требуется; uv/pnpm будут первичным выбором, а не заменой действующих инструментов.

## Конкретные расхождения и пробелы

| Источники | Проблема первой вертикали | Предлагаемое решение |
|---|---|---|
| Запрос об актуальном репозитории / пустая cwd | Нет кода, который можно сохранить или исправить | Считать текущую папку новым проектом только как открытое предположение; не импортировать старую историю |
| DATA_POLICY §7 / TRAINING_AND_EVALUATION §9 | Research preview и диагностический выпуск имеют разные основания допуска | Для этого инкремента предлагаются production fail-closed и явно обозначенный dev/test predictor; реальный research release решается отдельно |
| FR-01: минимум две поддержанные культуры / отсутствие bundle | Нельзя честно выполнить ML-поддержку по документам или демонстрационному каталогу | Справочный каталог отдельно, все production can_assess=false; 503 при отсутствии модели, 422 для культуры вне разрешенного scope |
| SYSTEM_DESIGN §9, DECISIONS: следующие решения | Auth-провайдер не выбран | Стандартный OIDC Authorization Code + PKCE; конкретный issuer задается конфигурацией, локальный проверочный issuer предлагается в спецификации |
| API_CONTRACT: таблицы endpoints и examples | Нет исчерпывающих DTO каталога, history/detail и download; field_season указан без CRUD | Зафиксировать Pydantic DTO до mobile; non-null field_season отклонять до реализации ownership seasons |
| PROJECT_PROPOSAL: объем MVP / FR-11–13 Should / запрос пользователя | Offline, feedback, annotation шире первой online-вертикали | Отложить отдельными инкрементами; не выдавать память текущего экрана за durable offline |
| Четыре outcomes / отсутствие quality/OOD detector | Декодирование не определяет blur/болезнь/орган | Реализовать типы и отображение; искусственные branches только тестовые; не придумывать детекторы |
| SYSTEM_DESIGN §6–8 | Не фиксированы attempts/lease/timeouts/reclaim/cleanup | Явные локальные defaults и тесты с управляемыми короткими интервалами |
| DATA_POLICY §6.3 / обычный upload | Отдельное разрешение на обучение/публикацию не получено | Upload используется для assessment/history; training/export/publication не включать |
| Figma: условные истории, задержка, RU/ҚАЗ | Прототип может выглядеть как готовая диагностика/offline/локализация | Реальная история и polling; без фальшивого переключателя языка и таймера диагноза |

Каталог examples.json иллюстративный: experimental/can_assess=true там не являются доказательством допуска модели.

## Проверка Figma

Прямой read-only `get_design_context` для файла `07cVYgjO4tZw4IaR7kUxEz`, узла `4:49` вернул код, screenshot и метаданные. Проверен только стартовый экран: 390×844, Roboto, фон #f6f7f2, brand #174c38, action #267a51, карточки/radius 16, основной touch target 56. Изображение соответствует стартовому экрану, описанному в MOBILE_PROTOTYPE. Остальные экраны живого Figma пока не запрошены. Нет оснований заявлять визуальную готовность приложения.

## Совместимость: что проверено и что остается

Официальные страницы проверены в ходе аудита. Expo перечисляет SDK 55 → RN 0.83 → React 19.2 и minimum Node 20.19.x: [Expo SDK](https://docs.expo.dev/versions/v55.0.0/), [общая таблица](https://docs.expo.dev/versions/latest/). Это кандидат совместимой линии, не утверждение о последней версии и не результат сборки. Node 26 локально не проверен на native toolchain; предлагается отдельный Node 22 LTS runtime с точной версией после проверки.

[PyTorch previous versions](https://docs.pytorch.org/get-started/previous-versions/) перечисляет согласованную пару torch 2.6.0 / torchvision 0.21.0 с cu124 и CPU wheels. Это справочная совместимая пара, не выбранная training-конфигурация и не выполненная установка. Training и CUDA не нужны первому инфраструктурному инкременту. [ONNX CPU Python](https://onnxruntime.ai/docs/get-started/with-python) — направление будущего реального adapter; wheel availability, opset и parity предстоит проверить на конкретном bundle.

Точных dependency locks пока нет: продуктовые зависимости не устанавливались. Выдавать предложенные версии за воспроизводимый lock нельзя.

## Выполненные действия и граница доказательств

`ls -la`, `rg --files`, чтение родительских AGENTS и материалов ZIP, `unzip -l`, `unzip -q` во временную папку, `cp -a` в docs/foundation, команды окружения из таблицы выше, read-only Figma и официальные страницы совместимости. `docker ps --format '{{.Image}}'` использован только для проверки доступного daemon, чужие контейнеры не изменялись. Полный аудит чужих каталогов не выполнялся.

После записи документов отдельно проверяются идентичность копии Foundation, JSON fixtures и относительные ссылки новых документов. Это проверки документации. API tests, worker kill/restart, migration, TypeScript compile, Expo doctor, end-to-end и модельная parity пока НЕ запускались: исполняемого проекта нет.

## Следующий шаг

[Спецификация первой online-вертикали](../superpowers/specs/2026-10-21-online-vertical-design.md). Она требует review по используемому процессу brainstorming. После подтверждения — отдельный исполняемый план и реализация. После рабочей вертикали ближайший ограниченный инкремент: offline capture/upload queue с persistent files/SQLite и проверками account switch/restart; обученный bundle и независимая оценка остаются самостоятельными задачами.
