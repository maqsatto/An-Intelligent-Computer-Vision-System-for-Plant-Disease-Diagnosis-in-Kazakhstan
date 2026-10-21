# AgroVision — спецификация первой online-вертикали

Дата: 21 октября 2026. Статус: предложено для review; не реализовано и не согласовано повторно пользователем. Это узкое дополнение к Foundation, а не замена его научной части.

## 1. Цель и границы

Пользователь Android создает observation, загружает один primary photo, создает assessment с сохраненным Idempotency-Key, получает 202 и читает immutable terminal result через polling. API и worker — два процесса одной Python-кодовой базы. PostgreSQL — источник состояния и durable jobs. Web UI, обучение, реальная диагностика без bundle, offline queue, фермы/поля, annotation и публичный model upload исключены из этого инкремента.

Принято из запроса: все ownership checks, atomic assessment/job, pinned bundle, fencing, retries, image decode/EXIF/RGB/limits, generated TS и изоляция runtime обязательны. [API_CONTRACT](../../foundation/contracts/API_CONTRACT.md) имеет приоритет над визуальными условными примерами.

Предположение: пустая текущая папка предназначена для нового проекта. Если существует другой актуальный checkout, сначала повторить аудит там и сохранить его решения/изменения; эту структуру поверх него не накладывать.

## 2. Подход и альтернативы

Выбран узкий modular monolith, PostgreSQL jobs и простые ports для ImageStore/Predictor. Celery потребует дополнительного broker и решения dual-write/outbox без существующего кода, который оправдывал бы перенос. Синхронный inference в API не обеспечивает нужный протокол восстановления. Сейчас мигрировать нечего.

Python 3.12.13, уже установленный через uv, — кандидат runtime проекта; системный Python не менять. pnpm workspace для mobile/api-client, отдельный uv project для server + dependency-light runtime. Training не добавлять в runtime dependencies. Expo SDK 55/RN 0.83/React 19.2 — предварительная согласованная линия по официальной таблице; перед фиксацией проверить доступность patch versions и expo doctor. Точные pins/locks создаются при реализации, не считаются существующими.

## 3. Границы кода и владелец контракта

Предлагаемое размещение: apps/mobile; packages/api-client; server/agrovision/{identity,catalog,observations,photos,assessments}; ml/runtime; server/migrations; tests/integration; docs/foundation. Каждый функциональный модуль имеет router/schema/service/model только там, где это нужно. Runtime не импортирует FastAPI/ORM/training. Никаких универсальных BaseRepository/BaseService и отдельного ML microservice.

Единый владелец Pydantic/OpenAPI/SQL migrations и протокола worker — основной агент. Mobile-agent после фиксации контракта изменяет только apps/mobile и UI tests; reviewer проверяет runtime/negative tests отдельно. Схемы не редактируются параллельно. Реальные YouTrack IDs отсутствуют: внешние задачи/ветки/PR/commits с вымышленными ID не создавать. Новый Git можно инициализировать в этой папке при реализации; импортировать чужую историю из старого ZIP нельзя.

## 4. Identity

Предлагается стандартный OIDC Authorization Code с PKCE для Android через Expo AuthSession и поддерживаемую JWT validation library на API. Локальная проверка — отдельный OIDC issuer (Keycloak в Compose) с двумя учетными записями A/B; production issuer/audience задаются конфигурацией. Проверять signature, allowed algorithm, issuer, audience, exp и стабильный sub; owner выводить из issuer+sub. Токены не брать из owner UUID/header без проверки.

Access token — память, refresh — SecureStore. Вход/выход и один сериализованный refresh; на 401 остановить бесконечный retry. Logout отзывает refresh credential/session поддержанным endpoint провайдера, затем очищает scoped state; тест проверяет отказ последующего refresh. При недоступности revocation локальный logout завершается с явным уведомлением, что удаленный отзыв не подтвержден; секрет не сохраняется для фонового retry и полная серверная инвалидизация не заявляется. Секреты и реальные credentials вне Git. Выбор конкретного production identity provider не обязателен локальному доказательству, но до deployment должен быть зафиксирован.

## 5. Хранение и DB constraints

PostgreSQL с миграциями Alembic. Observation: owner, unique(owner, client_observation_id), normalized semantic hash, known crop/organ, captured_at с offset, notes <=1000, nullable deleted_at. Время без timezone отклонять. Пока field seasons не реализованы, null разрешен; non-null — явный 422, без молчаливого игнорирования.

Photo: owner, observation_id, unique(owner, client_photo_id), raw upload hash для replay, normalized immutable blob key/hash/media_type/width/height, purpose, status. Ответный sha256 относится к нормализованным сохраненным bytes; исходный hash отдельно служит сравнению upload retry. Повтор того же ID с другим input hash/purpose/observation — 409.

Assessment: owner, observation_id, primary_photo_id, crop+organ snapshot, immutable model/policy/preprocessing pins, state/timestamps. Job: unique assessment_id, attempts/max_attempts, available_at, lease_token/lease_until и state. Result: primary/unique assessment_id, JSON структурированного результата. Idempotency: unique(owner, operation, key), normalized body hash, assessment_id. Составные ссылки или эквивалентные constraints плюс проверки сервиса исключают cross-owner/cross-observation привязку.

Один terminal result, assessment terminal state и job terminal state фиксируются атомарно. Прямые UPDATE/DELETE result запрещены роли приложения; terminal assessment не возвращается в queued по replay. Удаление observation блокирует новые чтения/download/create/finalize; retained result не становится доступным через ID. Очистка private blob отдельно.

## 6. HTTP и shared client

Реализуем GET catalog/me, POST/GET observations, GET observation detail, POST photos, GET content-url, POST/GET assessments и DELETE observation с tombstone/cleanup. Feedback откладывается отдельно; не объявлять отсутствующий endpoint реализованным. History — owner-scoped cursor pagination; DTO документировать до генерации клиента.

Канонические поля AssessmentRead и Candidate, status/outcome/error инварианты буквально из Foundation. Схема должна описывать допустимые terminal и nonterminal варианты; TS клиент генерируется из реального FastAPI OpenAPI и компилируется. CI regenerates и обнаруживает drift. Обработчик HTTP errors возвращает {code,message,details,request_id}, включая schema errors и безопасные storage/model ошибки. Незапланированные stack traces клиенту не выдавать.

POST observation: 201, replay 200, иной semantic body 409. POST assessment: Idempotency-Key UUID обязателен; actor+schema → lookup owner-scoped key → replay/current state 200 с Idempotency-Replayed:true или conflict 409. Собственный удаленный observation → resource_deleted 409. Для нового ключа проверить resources/ready/support/model, закрепить bundle и атомарно вставить idempotency+assessment+job. Уникальный constraint разрешает concurrent race; проигравшая транзакция читает победителя и сравнивает body. Только после commit 202.

## 7. Каталог и отсутствие модели

Справочные crop IDs wheat/potato/tomato/maize известны, но сами не дают can_assess. Catalog получает assessable capabilities только из проверенного активного manifest; без него can_assess=false, classes/supported_organs не выдумывать по макету. Known observation можно сохранить без анализа. Неизвестный crop/organ → 422 invalid_crop/invalid_organ.

Configured eligibility — отдельный операторский scope для маршрутизации ошибок, а не capability модели; wheat/potato/tomato здесь только предложенная integration-конфигурация. Для configured pilot crop без готовой модели — 503 model_unavailable, без assessment/job. Crop вне разрешенной области (например maize до ее включения) → 422 unsupported_crop. Такой приоритет уточняет различие unsupported и temporarily unavailable; фиксируется в тестах и контрактном дополнении. Пустой production catalog не маскируется demo capabilities. В DTO каталога дополнительно фиксируется availability_reason: model_unavailable для разрешенного pilot без bundle и unsupported_crop для исключенной культуры; эти поля — явное совместимое дополнение проектного контракта, а не уже существующие поля Foundation.

Успешная инфраструктурная цепочка сейчас возможна только в test или explicit development mode. Dev predictor возвращает completed.inconclusive с reason insufficient_evidence, никогда здоровое растение или болезнь. Идентификатор версии dev-synthetic-* и постоянный баннер «Демонстрационный режим. Модель не выполняет диагностику» на всех связанных экранах/истории. Production config отвергает synthetic adapter. Искусственные predicted/retake/unsupported branches используются только UI/contract fixtures, не как заключения по пользовательскому фото.

## 8. Worker и восстановление

Предлагаемые проверяемые defaults: max_attempts=3, lease=60 s, inference timeout=30 s, backoff 2/4 s с ограниченным jitter. Один job одновременно на worker для локального профиля. Значения — инженерные настройки, не измеренный SLA. В тестах применяются короткие интервалы/контролируемые часы и синхронизационные барьеры вместо долгих sleep.

Claim: сначала без row locks получить ограниченный список ID кандидатов queued/expired running. Для каждого кандидата в короткой транзакции захватить observation → assessment → job через FOR UPDATE SKIP LOCKED, пропуская занятый набор; повторно проверить deleted/state/available_at/lease и attempts под locks. Только после этих проверок увеличить attempts, присвоить случайный новый token и deadline по DB clock, поставить assessment running/started_at. Нельзя удерживать job lock до получения observation lock. Commit до загрузки изображения и predictor. Inference и загрузка blob/model в постоянном supervised predictor process с warm session cache по checksum. Общий бюджет загрузки+вычисления ограничен 30 s; timeout убивает процесс, supervisor создает новый с пустым cache. Не создавать новый процесс/session на каждое успешное задание. Runtime initialization вне каждого HTTP-запроса; cold initialization включается в timeout и измеряется отдельно.

Reclaim обязательно терминализирует expired running с attempts>=max_attempts, даже если worker умер на последней попытке. Иначе такие задания зависнут навсегда. Временная ошибка ставит available_at и queued только пока остались попытки; non-retryable input/bundle ошибка завершается сразу. После исчерпания — failed, error со стабильным code и finished_at.

Finalize/retry/reclaim/delete используют общий порядок row locks: observation → assessment → job. При удалении нескольких assessments/jobs обходить assessment IDs в возрастающем порядке и job IDs в возрастающем порядке в рамках соответствующего assessment; все операции придерживаются той же последовательности. Нормативный claim-алгоритм выше выбирает кандидатов без блокировки и повторно проверяет eligibility после захвата всех locks; SKIP LOCKED не заменяет recheck. Finalize под этими locks проверяет текущий token, running, lease_until>DB clock и отсутствие tombstone. Insert result + completed + job done одной транзакцией. Любой mismatch отклоняет весь commit. Смерть до commit допускает повторное вычисление; после commit повтор не меняет результат. At-least-once computation, один committed result.

## 9. Изображения и download

Request body ограничен на reverse proxy и при чтении multipart; file stream <=10 MiB, Pillow actual JPEG/PNG decode, dimensions <=20,000,000 pixels до полного decode, decompression bomb policy, запрет анимированных/многокадровых файлов. Не доверять MIME/extension. Поврежденные файлы 422, неподдержанный actual format 415, лимиты 413. EXIF transpose → RGB → нормализованные bytes, без EXIF/GPS metadata.

ImageStore local private persistent Docker volume как минимальный adapter; не static public mount и не ephemeral контейнерный filesystem. Запись staging/exclusive final key, atomic publish; существующий ready key не заменять. ready только после успешной записи. DB lock не держать во время decoder/blob IO; уникальный client ID разрешается constraint. После blob write финальная транзакция захватывает observation → photo, повторно проверяет owner, tombstone и pending reservation и только затем ставит ready. При отказе blob попадает в cleanup, даже если deletion cleanup уже проходил. Abandoned pending reservations и staging/orphan objects очищаются периодической bounded процедурой; локальное filesystem перечисление сверяется с DB с grace period, чтобы не удалить еще записываемый blob. Будущий S3 adapter сохраняет ту же immutable семантику.

Content URL: короткоживущий подписанный opaque reference с expiry, но download дополнительно требует bearer и повторный owner/tombstone check. URL сам по себе не дает пользователю B права скачивания. React Native загрузчик изображения передает Authorization; не логировать URL/token. После удаления немедленно отказать новому download. Контент не включать в Git, access logs или общие fixtures.

## 10. Bundle/runtime boundary

Validator требует artifact checksum, ordered stable class IDs, tensor shape/names/dtypes, RGB/EXIF/resize/crop/interpolation/scale/normalization, output semantics, global_joint/crop_conditional score space, postprocessing/policy versions, explicit finite thresholds и evaluation/provenance refs. Проверяется независимый expected class-order digest/export metadata: сверка длины списка сама по себе не обнаруживает перестановку label order.

Несовместимый preprocessing/version или порядок labels отклоняет activation. Calibration claim требует artifact/hash и корректной policy. Нельзя активировать manifest с пустыми/null thresholds. Никакой перенормировки после crop filtering; низкая global crop mass не превращается в уверенный выбранный диагноз. Отсутствие quality detector → not_assessed, а не passed/too_blurry по выдуманному правилу.

Для реального bundle отдельно потребуются фиксированные raw image fixtures и expected intermediate preprocessing tensors/logits, PyTorch/ONNX parity с заранее установленным допуском и provenance. Сейчас такой bundle отсутствует, parity не может считаться выполненной или заменяться synthetic fixture.

## 11. Mobile

Съемка/галерея через поддержанные Expo APIs с permissions и cancel, selection из серверного каталога, preview с заменой фото, стабильные in-memory client IDs/key для одной online попытки, upload отдельно от queued/running, один polling loop с bounded backoff, отмена при background/unmount/401/404 и остановка на terminal. После утраты ответа повтор сохраняет IDs/key. Process-death persistence и offline recovery относятся следующему инкременту; текущий интерфейс не обещает «сохранено на устройстве».

Визуальная отправная точка — Figma 07cVYgjO4tZw4IaR7kUxEz, стартовый узел 4:49. До реализации каждого экрана запросить его high-fidelity context и screenshot. Прямо проверен пока только home. RN layout и native controls; Figma React/Tailwind не копируется как web UI. Code Connect references проверять на применимость: библиотеки web Material Kit нет в пустом RN проекте. Демонстрационные истории/лист не подставлять вместо пользовательских данных.

UI отдельно показывает preflight 422/503, queued/running, failed и четыре completed outcomes. «Предполагаемое состояние» только при фактическом predicted; никаких фиктивных процентов. Неизвестный reason_code дает безопасный общий текст. RU/ҚАЗ переключатель не добавлять как работающую локализацию до переводов. При can_assess=false разрешено сохранить online observation/photo без запуска анализа.

## 12. Приемка и доказательства

Проверки на настоящем PostgreSQL, не замена SQLite для locking tests:

1. Два OIDC actors; A проходит observation/upload/202/отдельный worker/poll/immutable result с explicit dev adapter. Production тот же input → 503 без job, отсутствие bundle честно видно в catalog.
2. B не читает photo content-url/content, history/detail, assessment A и не связывает чужой photo со своим observation; ответы 404 без существования чужого объекта.
3. Повтор observation/upload/assessment и concurrent request с одним ключом → один ресурс/job. Иное semantic body/content → 409. Смена active model не меняет replay/pins.
4. Убийство worker после claim; после inference до commit; после commit до acknowledgment. Lease expiry, восстановление и один result. Повторные смерти вплоть до последней попытки → failed, без вечного running.
5. Новый worker claim сменяет token; старый finalize/retry/heartbeat отклоняются. Race deletion/finalize не публикует результат после tombstone.
6. Невалидный MIME/реальный файл, truncated JPEG, unsupported format, byte limit, pixel bomb, EXIF/RGB и duplicate upload race. Ready blob нельзя перезаписать.
7. Перестановка labels, preprocessing mismatch, неверный checksum, null policy/calibration mismatch отклоняют bundle. Production не принимает dev predictor.
8. Pydantic/OpenAPI/generated TS drift check; mobile typecheck и обработка всех status/outcome/error веток, polling cancellation. Реальный Android camera/gallery flow и screenshot comparison фиксируются отдельно; отсутствие SDK/устройства явно сообщается.

Успешное прохождение этих проверок доказывает инфраструктуру, не агрономическую точность. Не заявлять работу в Казахстане, interviews или accuracy без отдельного evidence. После интеграции независимый review и общий end-to-end обязательны; сейчас они еще не выполнены.

## 13. Открытые предположения и продолжение

Текущая папка — новый проект; production issuer/host/retention еще не выбраны. Предлагаемые local OIDC и DB defaults — проектные решения для review, не установленное окружение. Настоящие YouTrack IDs отсутствуют. Ни один model release не допущен.

После подтверждения этой спецификации следующий процессный шаг — письменный исполняемый план с проверками и разграничением файлов, затем реализация. Следующий продуктовый инкремент после первой рабочей вертикали — offline queue; интеграция обученного bundle, независимая оценка, feedback/annotation, локализация и web идут отдельно.
