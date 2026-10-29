# Proofport: передача backend frontend-разработчику

Дата аудита: 2026-10-29. Ветка: `backend/codex`. Основа: P3, коммит
`5e45392`. Документ описывает существующий код, а не новый API-контракт.
Предложения расширений в разделе 11 пока **не реализованы**.

## 1. Что можно подключать сейчас

Dashboard уже может запускать одну задачу, опрашивать ее состояние, показывать
модули, базовые счетчики, findings, evidence и скачивать HTML/JSON-отчеты.
Все режимы используют одни и те же пять бизнес-endpoints. Режим задачи,
версии Python и источники fixtures выбираются **оператором на сервере до
запуска приложения**; frontend пока не может выбирать их в POST.

Основные ограничения интеграции:

- Нет capabilities endpoint и сведений о режиме в текущем RunState. Health
  показывает `LLM_MODE`, но этого недостаточно для определения вида задачи.
  До появления расширения dashboard должен получать режим из согласованной
  конфигурации развертывания; если он неизвестен, показывать «режим не определен».
- Подробные результаты проверок, provenance, версии, CWE, confidence, diffs и
  попытки исправлений доступны в **завершенном JSON-отчете**, а не в RunState.
- Нет upload, клонирования URL, истории запусков, cancel/retry, SSE/WebSocket,
  API управления findings или ручного принятия security patch.
- `done` означает завершение выбранной операции. Это не универсальный знак
  успешной миграции, полной совместимости или отсутствия уязвимостей.

### Матрица реальных возможностей

| Возможность | Через существующий HTTP API | Другие точки входа и границы |
| --- | --- | --- |
| Python 2.7 → 3.12 migration pipeline | Да, POST run при серверном `verify` или `fixtures` | Golden recording, перевод кандидатов, компиляция, существующие тесты, сравнение, Bandit; оригиналы сохраняются |
| Offline migration fixtures | Да, серверный `fixtures`, `LLM_MODE=mock` | Реальные Docker-проверки заранее написанных patches; **не AI-миграция** |
| Live Meta translation/repair | Код подключен к `verify`, но в текущем этапе не включать | Нужны live/key/model/cases; реальная Meta-модель не проверена. Автоматического fixture fallback нет |
| Анализ Python 2.7 / 3.x | Да, серверный `analyze`; детали в отчете | `python -m backend.universal analyze`; `core.analyzer.analyze_python` |
| Security audit без миграции | Да, серверный `audit`; отчет и findings | `python -m backend.universal audit`; только статический Bandit, без исправлений и импорта проекта |
| Проверка совместимости | Да, серверный `compatibility` | CLI `check`; синтаксис, непустой unittest suite, optional golden comparison; код не переводится |
| Security Fix Engine | Да, как **этап fixture-миграции**, если настроен manifest | Независимый `SecurityFixEngine.run(generator)` доступен из Python; standalone fix endpoint/CLI нет |
| Генерация security fixes моделью | Нет | `LLMFixGenerator` содержит schema/parser, но `generate` явно отключен для live/replay |
| Реестр Python runtimes | Прямого GET нет; snapshot бывает в P3-отчете | CLI `registry`, `VersionRegistry.inspect/select/verify`; проверка runtime выполняется явно |
| Статическое определение версии до запуска | Отдельного endpoint нет; результат бывает в P3-отчете | CLI `detect`, `core.detection.detect`; возвращает признаки/диапазон, не доказательство совместимости |
| Evidence, SHA-256, отчеты | Да, events/state/report | Дисковые артефакты под `backend/.work/`; отдельного файлового download API нет |
| Настройка модели / вызов LLMClient | Нет публичного endpoint | Только backend Python; ключи никогда не передаются frontend |
| Replay migration/security generation | Нет рабочего пути | Health принимает строку `replay`, но LLMClient/генератор не реализуют replay |

P3 проверен на Docker Python **2.7.18, 3.12.16, 3.13.18**. Версии 3.8, 3.10,
3.14 только configured; на машине проверки их образы не были установлены.
Это результаты предыдущего P3-прогона, а не текущий runtime-discovery API.
`configured`, `available`, `verified` — разные признаки. Verified runtime
подтверждает контрольные проверки самого интерпретатора/проверяющего кода,
а не совместимость любого проекта или наличие переводчика для каждой пары.
Реальная миграция пока реализована только для 2.7 → 3.12.

## 2. Подключение и серверная конфигурация

Локальный адрес: `http://127.0.0.1:8000`. Приложение читает корневой `.env`,
затем переменные окружения; окружение имеет приоритет. Настройки приложения
фиксируются при создании app. После изменения режима нужен перезапуск сервера.

Если папка `frontend/` существует, она обслуживается как static files на `/`.
API зарегистрирован раньше static mount. SPA fallback на произвольный route
не реализован: для dashboard подходят hash routing или заранее согласованная
настройка хостинга. Встроенные `/docs`, `/redoc`, `/openapi.json` доступны,
но не заменяют описание custom errors и report-полей в этом документе.

В app нет CORS middleware. Для отдельного dev-server используйте proxy `/api`
на backend; production dashboard предпочтительно обслуживать с того же origin.
Добавление cross-origin политики требует отдельного backend-изменения.

### Режимы оператора

| `PROOFPORT_PIPELINE` | Условия и результат |
| --- | --- |
| `verify` (default) | Docker + `PROOFPORT_CASES_FILE`; затем нужен live translator. `mock` не переводит код. При отсутствии условий задача завершается failed, а не демонстрационным успехом |
| `fixtures` | `LLM_MODE=mock`, cases и `PROOFPORT_FIXTURE_FILE`; настоящие тесты fixture-кандидатов |
| `simulation` | Только `LLM_MODE=mock`; имитация модулей, тестов, fixes, tokens и cost; реальные только inventory/hash/evidence bookkeeping |
| `analyze` | Подтвержденный source runtime и явная/однозначная source version; статический анализ в Docker |
| `audit` | Те же source-условия + локальный Bandit image; анализ и статический scan |
| `compatibility` | Подтвержденный target runtime, `PROOFPORT_TARGET_VERSION`; source нужен для golden recording, иначе при неоднозначности анализ может идти target-интерпретатором |

P3 использует `PROOFPORT_SOURCE_VERSION`, `PROOFPORT_TARGET_VERSION`, optional
`PROOFPORT_CASES_FILE`. `PROOFPORT_VERIFY_RUNTIME=1` явно разрешает контрольные
проверки нужных локальных образов; автоматических pull нет. Полные команды
оператора и ограничения: [UNIVERSAL.md](UNIVERSAL.md).

Для демонстрации fixture-миграции оператор задает `LLM_MODE=mock`,
`PROOFPORT_PIPELINE=fixtures`,
`PROOFPORT_CASES_FILE=tests/fixtures/legacy_shop/cases.json`,
`PROOFPORT_FIXTURE_FILE=tests/fixtures/legacy_shop/patches.json`.
Optional `PROOFPORT_SECURITY_FIXTURES=tests/fixtures/security/legacy_shop_fixes.json`
включает проверку security proposals после успешной миграции.
Этот flag разрешен API только с `fixtures` + `mock`; перед переключением на
P3-режимы его нужно убрать. Установка flag не гарантирует принятие исправлений.

Для безопасной интеграции текущего этапа используйте offline-режимы. Не
включайте `verify` + `live` с действующим ключом ради проверки интерфейса:
этот путь может отправить платные запросы. Ключа и переключателя платного
режима в dashboard сейчас быть не должно.

## 3. Текущие endpoints и примеры

Все JSON-примеры ниже валидны. Фрагменты отчета помечены как проекции:
отсутствующие в примере поля не следует считать удаленными из ответа.
Сценарии migration, audit и compatibility — отдельные запуски.

### GET /api/health

HTTP 200:

```json
{"ok": true, "docker": true, "llm_mode": "mock"}
```

`ok` означает доступность приложения. `docker` — результат проверки при
старте app, который может устареть. `llm_mode` — конфигурация, не проверка
ключа, модели, баланса, доступности API, реального провайдера задачи или
наличия необходимых Docker images. Все три поля недостаточны для бейджа
«готов к AI-миграции».

### POST /api/runs

Content-Type: `application/json`. Например, при серверном compatibility:

```json
{"source_path": "tests/fixtures/universal_py3", "max_iterations": 1}
```

HTTP **200**, не 201/202:

```json
{"run_id": "188f04901bb648248b0d715da78ba2ea"}
```

Запуск асинхронный; ответ не означает успешного выполнения.
`source_path` — путь **на машине backend**, относительно корня repo или
абсолютный; это не путь браузера и не GitHub URL. Для migration demo нужен
внешний `samples/legacy_shop`, содержащий и package, и tests/data.
Отдельный `.py` принимается только в `analyze/audit/compatibility`.

Разрешены только два request-поля:

| Поле | Проверка |
| --- | --- |
| `source_path` | Обязательная непустая строка; должен существовать Python source |
| `max_iterations` | Optional, default 5, строго integer >= 1; строки, bool и 0 недопустимы. Управляет migration loop, а не P3-аудитом/проверкой |

`mode`, `source_version`, `target_version`, `llm_mode`, `api_key`, files и
любые другие дополнительные поля отвергаются с 422. Одновременно допускается
одна активная задача **на процесс**. Второй POST получает 409 `run_busy`;
серверной очереди нет. POST не идемпотентен: при потере ответа нельзя слепо
повторять его, поскольку первый запуск мог уже начаться.

### GET /api/runs/{run_id}

Полный пример завершенной проверки 3.12 → 3.13 из сохраненного P3-отчета:

```json
{
  "status": "done",
  "phase": "reporting",
  "isolation": "docker",
  "modules": [
    {"name": "numbers_demo", "status": "green", "iterations": 0, "tests_passed": 2, "tests_total": 2}
  ],
  "security": {"before": 0, "after": 0, "findings": []},
  "hashes": {
    "universal_py3/cases.json": "83b5e4fad18a418759a4ddf69e67fd9bef9d9fa5bd6dab06003711b0ca3e3c8b",
    "universal_py3/numbers_demo.py": "3178254fb814926b90e6ceb68acc78890efa3c867b4bd7b69e80fdf51a2587bb",
    "universal_py3/README.md": "aaf3317308d87cfe5f22095f257956d914cf6b5da069d42242418b83a2c0aab3",
    "universal_py3/tests/test_numbers.py": "2d5c98a1629d91c2e7d0d89de73f613a1748c8bf12402fc79028d6297b95b241",
    "unchanged": true
  },
  "metrics": {
    "tests_passed": 4, "tests_total": 4, "lines_migrated": 0,
    "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "seconds": 36.672
  },
  "chain_intact": true
}
```

`run_id`, source path, режим и версии не входят в RunState. Сохраните run_id
из POST отдельно. `error` отсутствует при отсутствии ошибки; при неуспехе
добавляется объект `{code, message}`. Транспорт успешного polling остается
HTTP 200, даже если `state.status == "failed"`.

Здесь нули security означают **scan не выполнялся в compatibility**, а не
«проект безопасен». `iterations: 0` и `lines_migrated: 0` нормальны: код
проверялся, но не переводился. Состав modules после анализатора может отличаться
от стартового inventory, в частности тестовые модули могут исчезнуть из списка.

### GET /api/runs/{run_id}/events?since=N

`since` optional, default 0, integer >= 0. Возвращается обычный JSON-массив
событий с `seq > since`, без envelope, пагинации и long polling.
Это **не SSE**. Пример реальных первых событий того же P3-запуска:

```json
[
  {
    "seq": 1,
    "ts": "2026-10-29T10:46:26.359Z",
    "type": "run_started",
    "module": null,
    "detail": "Static source inventory only; no code execution, migration, tests, or security scan.",
    "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000",
    "entry_hash": "72a8c7853320599e2c53bea0b53ae93c33db55027ce4dc663f187c64cfac63bf"
  },
  {
    "seq": 2,
    "ts": "2026-10-29T10:46:26.359Z",
    "type": "hashes_recorded",
    "module": null,
    "detail": "SHA-256 recorded from 4 actual source files.",
    "prev_hash": "72a8c7853320599e2c53bea0b53ae93c33db55027ce4dc663f187c64cfac63bf",
    "entry_hash": "c977d2b098a4f88f65dc833e6ab0b230297873809d37b128f55c9f76c98fe1d9"
  }
]
```

Начальное `run_started` описывает inventory до выполнения worker; в migration
может быть еще одно `run_started` с уточнением реального режима. Повторение type
легально. `detail` — текст; некоторые сообщения содержат JSON в строке, другие
обычный текст. Это не стабильный machine-readable payload. `module` может
быть null, именем модуля либо путем файла, а не гарантированным FK в modules.

Текущие типы: `run_started`, `hashes_recorded`, `golden_recorded`,
`patch_applied`, `model_call`, `sandbox_run`, `test_result`, `security_finding`,
`security_fix`, `fix_reverted`, `error`, `run_finished`.
При неизвестном type показывать безопасный текстовый fallback.
`patch_applied` означает в том числе **staged candidate**, не обязательно
принятое исправление. `error` бывает промежуточным в repair loop: terminal
состояние определяется RunState, а не одним событием.

### GET /api/runs/{run_id}/report?format=html|json

Default `html`. До terminal status возвращает 409 `run_not_finished`.
Отчет доступен и для failed-задачи. HTML: `text/html`; JSON:
`application/json`. Оба ответа содержат `Content-Disposition: attachment`
с именем `proofport-{id}.html` или `.json`. PDF/ZIP/download исходников нет.

Корневые поля JSON-отчета:

| Поле | Значение |
| --- | --- |
| `simulation` | Признак симуляции, независимо от успешности задачи |
| `notice` | Объяснение scope/ограничений для человека; не парсить как API enum |
| `state` | RunState; статус и целостность читать даже при наличии хороших отдельных checks |
| `settings` | `pipeline`, `model`, `max_iterations`; без ключей API |
| `allowed_differences` | Документированные разрешенные различия comparator; не скрывать их от пользователя |
| `verification` | Детали фактически дошедших до выполнения этапов; состав зависит от режима/ошибки |
| `events` | Полный массив evidence с seq с начала задачи |

`settings.pipeline` — **execution mode**, а не буквальное значение env во всех
случаях: `verify` дает `live` после инициализации, fixture migration —
`fixtures`, P3 — `analyze/audit/compatibility`, ранние отказы могут дать
`static_only`. Security subsection использует singular `mode: "fixture"`.
Ниже — именно report-поля; не ожидайте их в GET RunState.

## 4. Состояния и отображение прогресса

### Run и modules

| Значение | Отображение и смысл |
| --- | --- |
| run `queued` | Принят; worker еще не начал работу. Это не очередь нескольких задач |
| run `running` | Выполняется; показывать текущую phase и активности |
| run `done` | Выбранная операция закончена; вывод о миграции/совместимости делать по отчету |
| run `failed` | Вывести error, сохранить доступ к частичным результатам/отчету |
| module `pending` | Еще не проверен полностью; может остаться pending в успешном analyze/audit/syntax-only/test-only run |
| module `translating` | Готовится кандидат миграции |
| module `testing` | Идет проверка кандидата |
| module `fixing` | Повторная попытка миграции; это не статус security fix |
| module `green` | Выполнены условия конкретного worker; читать provenance/coverage; simulation тоже рисует green |
| module `failed` | Требуемая проверка не подтверждена; другие ранее green-модули не означают успех всего run |

`phase` — свободная строка, не enum: сейчас `analyzing`, `recording`,
`migrating`, `security`, `reporting`. В migration возможен порядок
analyzing → recording → security → migrating с повторами → security → reporting.
P3 не обязан проходить все эти этапы и не публикует отдельную phase для каждого
compile/test/case check. Unknown phase должна иметь нейтральное отображение.
`reporting` встречается и при failed. Отдельного поля процента/ETA нет.

Прогресс показывать как phase + счетчики модулей по статусам + текущие результаты
тестов. Если нужен индикатор активности — indeterminate. Производный процент
green/modules допустим только с подписью «проверено модулей», это не процент
времени, и для audit/analysis не является показателем завершения.
Counters/denominators могут меняться; при repair часть значений сбрасывается.

### Metrics, hashes, isolation

| Поле | Как читать |
| --- | --- |
| `modules[].tests_passed/total` | В migration/compatibility обычно golden cases модуля, а не количество unittest методов |
| `metrics.tests_passed/total` | Агрегат golden comparisons + существующих тестов, где этапы выполнены; не складывать с module counters еще раз |
| `lines_migrated` | Число строк принятых green-модулей target, не точное число измененных строк diff |
| `tokens_in/out`, `cost_usd` | Учет записанных успешных LLM calls; стоимость вычисляется по серверным PRICE-настройкам, не billing balance и не подтвержденная цена Meta |
| `seconds` | Истекшее время, не ETA |
| `hashes` | Динамические ключи файлов с SHA-256 плюс специальный `unchanged: null/true/false`; null = еще не подтверждено |
| `chain_intact` | Локальная проверка evidence chain; не внешняя сертификация |
| `isolation: docker` | Worker использовал Docker; не доказательство успешности всех этапов |
| `isolation: reduced` | Контейнерная проверка не выполнена; host execution fallback отсутствует |

В simulation метрики тестов, строк, tokens/cost и fixes **выдуманы для demo**.
У LLMClient mock, fixture migration и P3 нет платного model usage. Нулевые
метрики сами по себе не доказывают режим: смотрите provenance. При live ошибках
счетчик записанных calls не равен количеству всех сетевых попыток/SDK retries.
Положительный счетчик вызовов тоже не подтверждает успешную миграцию.

## 5. Подробные результаты migration и compatibility

### Migration report

Используйте `verification.analysis`, `source_python`, `images`,
`golden_case_count`, `legacy_tests`, `target_compiles`, `target_tests`,
`comparisons`, `limitations`, `mode`, `model_calls`, `ai_migration`.
Часть полей отсутствует, если соответствующий этап не закончился.
Например, проекция `verification` для одного существующего теста и case:

```json
{
  "mode": "fixtures",
  "ai_migration": false,
  "model_calls": 0,
  "target_compiles": true,
  "target_tests": {
    "python": [3, 12, 16],
    "tests_run": 1,
    "outcomes": [{"id": "test_demo.DemoTest.test_total", "status": "passed"}],
    "output": ""
  },
  "comparisons": [
    {"id": "demo.total", "module": "demo", "matches": true, "allowed_differences": []}
  ]
}
```

Это сокращенный **иллюстративный** fixture-пример структуры, не результаты
нового запуска. Реальный demo legacy_shop в P3 regression сохраняет 90/90
golden cases и 10/10 существующих тестов. `comparisons` — массив по case ID;
при mismatch появляются `expected` и `actual`, сравниваются также значения,
типы, исключения и stdout/stderr с явно зафиксированными allowances.
`outcomes[].status` бывает `passed`, `failed`, `error`, `skipped`; reason
optional. Пропущенный тест не следует отображать как прошедший.

### Compatibility report

Проекция `verification` реального P3-примера из раздела 3; часть вложенных
диагностик опущена ради размера примера:

```json
{
  "mode": "compatibility",
  "ai_migration": false,
  "migration_performed": false,
  "model_calls": 0,
  "source_version": "3.12",
  "analysis_interpreter": "3.12",
  "target_version": "3.13",
  "compatibility": {
    "syntax_compatible": true,
    "tests_passed": true,
    "behavior_verified": true,
    "level": "behavior_verified",
    "recorded_cases_match": true,
    "covered_modules": ["numbers_demo"],
    "uncovered_modules": [],
    "existing_tests": {
      "python": [3, 13, 18],
      "tests_run": 2,
      "outcomes": [
        {"id": "test_numbers.NumbersTest.test_add", "status": "passed"},
        {"id": "test_numbers.NumbersTest.test_divide", "status": "passed"}
      ],
      "output": ""
    }
  }
}
```

| Level / check | Честная подпись в UI |
| --- | --- |
| `not_verified` | «Совместимость не подтверждена» |
| `syntax_compatible` | «Синтаксис подходит для выбранного интерпретатора» |
| `tests_passed` | «Существующие тесты прошли»; это еще не golden equivalence |
| `behavior_verified` | «Поведение совпало на записанных случаях» с указанием coverage, не универсальная эквивалентность |

Check boolean использует три значения: `true` = подтверждено на этапе,
`false` = проверка не прошла, `null` = не подтверждено/не выполнялось.
Отсутствующее поле также показывать как неизвестное, не как false или success.
Level — сильнейший выполненный check, но не заменяет `state.status`, errors
и отдельные checks: например, тесты могут пройти, а golden сравнение провалиться.
При failed-задаче нельзя выдавать итоговый зеленый compatibility verdict.

Дополнительные данные: `compatibility.syntax` (errors/python),
`existing_tests`, `comparisons`, optional `target_metadata_compatible`.
Совпавшие случаи с неполным покрытием дают `recorded_cases_match: true`,
но `behavior_verified: null`. Для behavior status нужны положительные direct
операции по всем проанализированным application modules и полное parser coverage;
это все равно не означает покрытие всех функций/ветвей. Empty/unsupported
suite не дает `tests_passed: true`. Сейчас поддержан discovery unittest под
`tests/`; зависимости проекта не устанавливаются/не разрешаются автоматически.

P3-отчеты также содержат `version_detection`, `registry`, `analysis` и
`limitations`. В detection показывать possible_versions/status и признаки,
а не «точно обнаружена версия». В analysis доступны modules с функциями,
классами, imports/obsolete advisories, graph, order, cyclic_or_blocked и
migration_plan. План не означает выполненную миграцию.

## 6. Security audit и security fixes

### Findings и audit-only

RunState содержит только `security.before`, `after`, `findings`.
Сокращенный Finding DTO (пример из реального audit legacy_shop):

```json
{
  "id": "B307-501c959a03faf42afa68fc25",
  "file": "legacy_shop/config.py",
  "line": 7,
  "severity": "MEDIUM",
  "status": "open",
  "note": "Bandit B307 (HIGH confidence): Use of possibly insecure function - consider using safer ast.literal_eval. Not automatically fixed."
}
```

Для карточки CWE/confidence/рекомендации нужен join по `id` с
`verification.security_details[]`. Дополнительные поля: `cwe` (object
`id/link` или отсутствует), `confidence` (Bandit HIGH/MEDIUM/LOW), `scanner`,
`scanner_test`, `scope`, `description`, `column`, `verification_status`,
`proposed_fix`. Последнее — текст рекомендации, **не готовый patch**.
Не путать Bandit confidence с числом confidence 0..1 у fix proposal.

Audit-only сохраняет `verification.security_audit` с `scan`, `coverage`,
`scanner_python`, `project_executed`, `fixes_applied`. Например, проекция:

```json
{
  "mode": "audit",
  "ai_migration": false,
  "model_calls": 0,
  "security_audit": {
    "coverage": "partial",
    "scanner_python": "3.12",
    "project_executed": false,
    "fixes_applied": false
  }
}
```

`coverage` сейчас `partial` при scan errors, иначе `parsed_files_only`.
Настоящий `scan` дополнительно содержит `results`, `errors`, metrics и
scanner metadata. Никаких задач исправления в audit-only нет, original hashes
проверяются. Поле `project_executed` относится к проекту; trusted runtime
self-tests при явном verify-runtime могут выполняться отдельно.

Bandit 1.8.6 работает в Python 3.12 scanner image: Python 2 и более новый
синтаксис могут быть пропущены. В проверенном legacy_shop audit было 8
потенциальных findings и 4 parser errors. «0 предупреждений» при partial
coverage не значит «безопасно». Даже полный parse не доказывает отсутствие
уязвимостей. В интерфейсе используйте «потенциальная проблема/предупреждение».

### Жизненный цикл finding

| Status | Отображение |
| --- | --- |
| `open` | Открытое предупреждение, подтвержденного исправления нет |
| `fixed` | Принят проверенный patch в рабочей копии; оригинал не менялся. В simulation — только имитация |
| `false_positive` | Есть контекстное основание классификации; raw advisory может остаться в scan |
| `needs_review` | Требуется ручное решение, например при изменении поведения/API/config/crypto/data format; это не принятое исправление |
| `fix_reverted` | Попытка отклонена/откачена, принятого изменения от этой попытки нет |

В обычной миграции before/after относятся к исходному/target scan.
После включения Security Fix Engine счетчики проецируют baseline security
pass и accepted copy после попыток. В audit значения before/after равны.
Они считают scanner findings, а не доказанные эксплойты; нельзя вычислять
«fixed» простой разностью счетчиков. После fixes `state.security.findings`
может включать и исторические resolved decisions, поэтому `after` не обязан
равняться длине массива. Нужны явные `security_fix.fixed` и decisions.

### Security Fix Engine: доступная интеграция

Последовательность: finding → offline proposal → staged copy → syntax →
golden → unchanged existing tests → Bandit rescan → policy decision.
Неудачный patch не принимается; исчезновение warning само по себе недостаточно.
Внешние исходники не редактируются. Даже успешная смена кода — fixture
hardening с заявленным scope, а не доказательство ранее эксплуатируемой дыры.

В `verification.security_fix` доступны:

| Поля | Назначение |
| --- | --- |
| `mode: fixture`, `ai_generated: false`, `isolation: docker` | Обязательный fixture provenance |
| `status: verified/failed` | Итог проверки accepted project, не обещание принять каждую proposal |
| `findings_before`, `findings_after`, `decisions` | Baseline, текущие warnings и история решений |
| `fixed`, `needs_review` | Массивы finding IDs |
| `rejected` | Массив **attempt IDs**, а не finding IDs |
| `attempts` | Каждая попытка: id/finding_id/file/mode/status, explanation, behavior_impact, confidence, review_areas, diff, applied/rolled_back/reasons |
| `attempts[].checks` | syntax/golden/existing_tests с `ran`, `passed` и диагностикой; не запущенное не отображать как failed test execution |
| `attempts[].rescan` | ran/passed/findings/errors, отдельно от изменения raw warning |
| `baseline_checks`, `final_checks`, `scan_after` | Проверки принятой копии, если этап завершился |
| `original_unchanged`, `evidence_chain_intact` | Условия доверия к результату |

Массивы и диагностика могут быть частичными после ошибки; не дорисовывать
несуществующие results. `needs_review` и `rejected` могут пересекаться:
proposal с ручным review тоже попадает в rejected attempts, если ее изменения
не приняты и откатились. Это не взаимоисключающие категории для pie chart.
Открывать diff как текст. Кнопки Apply/Reject/Mark false
positive пока не имеют HTTP endpoint и должны быть скрыты или disabled с
объяснением. `needs_review` не означает, что backend уже хранит интерактивную
очередь согласований. Proposal/attempt не являются новым публичным DTO.

На legacy_shop четыре offline proposals (eval, SQL, subprocess, secret)
остались для review, принятых security patches нет. Отдельный собственный
constant-command fixture демонстрирует принятое hardening и контекстный
false positive. Не переносите этот успех на весь legacy_shop или на Meta AI.

## 7. Live / mock / replay: правила маркировки

| Сценарий | Допустимая подпись |
| --- | --- |
| `simulation: true` | Постоянный бейдж «Симуляция». Тесты/fixes/tokens/cost показывать как simulated, независимо от green/done |
| `settings.pipeline: fixtures`, `simulation: false` | «Offline fixture; проверено в Docker» при наличии фактических results, без AI-бейджа |
| `analyze/audit/compatibility` | Название операции + реальные check results. Не называть переводом или AI security fix |
| `static_only` или недостаточно данных | «Не проверено»; нули не выдавать за успех |
| Live-путь | Только terminal done + не simulation + `verification.ai_migration === true` + записанные calls > 0 + успешные checks и целостность позволяют говорить о проверенном model-produced результате на указанном scope |
| Health `llm_mode: replay` | «Replay не реализован» для migration/security generation; health не обещает доступности replay |

`LLMClient.mock` возвращает canned response без сети и не является переводчиком.
`verify` с mock не превращается в fixture migration. Live при отсутствии
ключа/модели завершается ошибкой, не подставляет демонстрационные результаты.
Schema security proposal с `mode: live/replay` не включает генератор:
LLMFixGenerator.generate отключен. Нельзя рекламировать «AI Security Fix
готов» до проверки с настоящей Meta-моделью.

P3 offline-режимы не создают SDK-клиент даже при наличии live credentials.
Тем не менее один только health live не делает их AI-операциями.
При failed run, нарушении chain/hash или неизвестном provenance подавлять
общий success/AI verdict; отдельные завершенные checks можно показывать
как частичные результаты. Успешная отдельная проверка не отменяет отказ run.

## 8. Polling, evidence, отчеты и восстановление UI

Рекомендуемое поведение клиента (это рекомендации UI, не новые гарантии API):

1. Проверить health и загрузить согласованный deployment profile; показать
   доступность приложения отдельно от готовности выбранной операции.
2. Отправить один POST. Сохранить `{run_id, origin, deploymentProfile}` в
   состоянии приложения; не хранить credentials и не делать auto-retry POST.
3. Последовательно, без overlap, опрашивать state и events примерно раз в
   0.5–1 секунду. При сетевых ошибках применять backoff. AbortController при
   unmount отменяет только HTTP-запрос frontend, **не backend job**.
4. Хранить event cursor отдельно для каждого run. Начать с 0; после успешной
   обработки batch обновить на максимальный seq. Deduplicate по `(run_id, seq)`.
   При retry повторить прежний cursor. Пустой массив не означает completion.
5. При done/failed сделать еще финальный fetch state/events/report JSON:
   GET report разрешен по status, но migration worker может дописывать финальные
   события/отчет после первой terminal snapshot. Нет атомарного finalized flag.
   Если report/state еще расходятся, повторить короткое ограниченное число раз;
   не объявлять completion по единственному `run_finished` event.
6. Рендерить отчеты с optional полями и учитывать errors/limitations. В том
   числе partial report для failed. Проверить chain/hash перед success badge.
   Последующие чтения могут отозвать done при обнаружении tampered evidence.
7. Предоставить HTML/JSON download через существующий URL. При fetch+Blob
   сохранять правильное расширение; не ожидать JSON от default HTML route.

GET state, GET events и GET report не являются атомарным snapshot. Нельзя
требовать идеального совпадения счетчиков разных ответов в процессе работы.
`seq` — порядок событий, UTC `ts` — время показа. Evidence hash chain локальная,
не внешне подписанная. `chain_intact` не следует называть «сертифицированным
доказательством» или «невозможностью подделки».

Runs и events живут в памяти процесса. После рестарта старый run_id получает
404, хотя файлы отчета могут оставаться на диске. Нет GET /api/runs со списком,
endpoint поиска активной задачи, загрузки старых артефактов, resume либо recovery
потерянного POST-ответа. Браузер может помнить известный ID, но это не серверная
история. Нельзя использовать несколько uvicorn workers как общую очередь:
они имеют независимые RunStore/active slots и HTTP reads могут попасть не туда.

## 9. Ошибки и доверие к отображаемым данным

HTTP errors обычно имеют общий envelope:

```json
{"error": {"code": "run_busy", "message": "Another run is already in progress."}}
```

| HTTP | Типичные code / действия UI |
| --- | --- |
| 400 | `source_not_found`, `source_unreadable`, `source_empty`, `unsupported_migration_pair`; поправить ввод/серверную настройку |
| 404 | `run_not_found`; показать отсутствие задачи, в том числе после restart |
| 409 | `run_busy`, `run_not_finished`, `source_changed`; не имитировать очередь/готовый отчет |
| 422 | `invalid_request`; неверные body/query/extra fields. Не ожидать стандартного FastAPI массива `detail` |
| 503 | `pipeline_unavailable`, `offline_only`; запрещенная комбинация режима и настроек |

Ошибки worker идут через **HTTP 200 RunState с status failed**. В `error.code`
встречаются `docker_unavailable`, `pipeline_unavailable`, `invalid_settings`,
`model_unavailable`, `verification_failed`, `verification_unavailable`,
`legacy_tests_failed`, `test_suite_incompatible`, `invalid_cases`,
`insufficient_cases`, `security_verification_failed`, `run_interrupted`,
`source_changed`, `source_snapshot_mismatch`, `source_version_ambiguous`,
`source_version_conflict`, `source_metadata_conflict`, `target_metadata_conflict`,
`unsupported_python_version`, `runtime_unavailable`, `unverified_version`,
`target_syntax_incompatible`, `target_tests_failed`, `behavior_mismatch`,
`report_unavailable`, `evidence_corrupted`. Список не закрытый: сохранять code
и безопасно выводить message для неизвестных значений. Error может произойти
после частичных реальных результатов, это не повод показывать все нулями.
Не все неожиданности инфраструктуры гарантированно превращаются в envelope:
нужен fallback для network errors, HTTP 5xx и неожиданного Content-Type.

В текущем backend нет authentication/authorization, project permissions,
request-level cancellation или контролируемой загрузки пользовательских файлов.
Это локальная интеграция; размещение dashboard в публичном сервисе требует
отдельных backend-решений до открытия доступа к server-local paths/runs/reports.
Docker ограничивает выполнение, но не заменяет эти функции и не является VM.

Source names, scanner messages, stdout/stderr, diffs, evidence и report-текст
считать недоверенными данными. Выводить через textContent/обычный escaped
rendering; не вставлять строку через innerHTML и не исполнять proposed code.
Скачиваемый HTML лучше открывать отдельно/в изолированном preview. Backend
редактирует известные secret snippets, но report не является гарантированным
универсальным secret scrubber: не отправлять его автоматически в аналитику.

## 10. Задачи для frontend, реализуемые без изменения контракта

- [ ] Типы/адаптеры для StartRun, RunState, Finding, Evidence, Error; optional
  report sections и fallback неизвестных phase/type/code.
- [ ] Deployment profile с заранее согласованным режимом; постоянные badges
  simulation/fixture/offline/unknown; health отдельно от readiness.
- [ ] Форма server-local source path и iterations; disable второго POST до
  terminal result; понятные 409/422/503. Не рисовать upload/clone как работающие.
- [ ] Polling без overlap, per-run cursor/dedup, cleanup и bounded retry;
  сценарии refresh с известным ID и 404 после рестарта.
- [ ] Module table, phase timeline, elapsed time и раздельные test/case totals
  без фиктивного процента, ETA или двойного суммирования.
- [ ] Совместимость: syntax/tests/behavior раздельно, null и partial coverage,
  source/target/actual patch versions и ограничения из отчета.
- [ ] Security table: potential warnings, CWE/confidence/details из report,
  parse errors, before/after semantics, статусы и история решений.
- [ ] Read-only fixes view: attempts, checks ran/passed, reasons, escaped diff,
  rescan, rollback, fixture provenance; без неработающих Apply/Approve кнопок.
- [ ] Evidence log с фильтрами, UTC/local time, integrity/hash badges,
  partial failure и явным отличием staged patch от accepted fix.
- [ ] HTML/JSON download и report view после done **и failed**; финальная
  сверка результатов, ошибок и provenance перед общим verdict.
- [ ] UI fixtures на показанных JSON: failed run, simulation green, fixture
  success, syntax-only, tests-only, mismatched/partial behavior, audit parse
  errors, fixed/false_positive/needs_review/fix_reverted, tampered evidence.

## 11. API-расширения для согласования — не текущий контракт

Ни один route/field ниже сейчас не следует вызывать или передавать в POST.
Приоритизация относится к dashboard, не является обещанием реализации.

| Приоритет | Предложение | Почему необходимо / критерий приемки |
| --- | --- | --- |
| P0 | Read-only capabilities/config summary + Python runtimes | Эффективный pipeline, generation mode, разрешенные операции/пары, configured/available/verified и причины недоступности; без ключей, без pull/оплачиваемого запроса при чтении |
| P0 | Согласованный versioned start DTO | Выбор operation/source/target/cases profile на задачу, строгая проверка поддержанных capability; paid generation по отдельной политике; старые клиенты остаются совместимы |
| P0 | Run metadata + финальный lifecycle | run_id, operation, provenance, source/target, timestamps, отдельный finalized; стабильные результаты и отмена success при integrity failure; не перегружать done/green |
| P0 | Typed progress и live check results | Stage/check status, counts и coverage, typed event payload; не парсить detail и не выдавать прогресс по времени без оснований |
| P0 | GET run list/active + persisted history | Reconnect после refresh/restart, общий job storage/идемпотентность POST, правила конкурентности, retention |
| P0 до remote deployment | Auth, authorization, безопасный intake проектов и origin policy | Upload/clone/server path allowlist, permissions, secret handling, CORS и доступ к артефактам; исключить arbitrary filesystem exposure |
| P1 | Read-only findings/tests/attempts/analysis resources с пагинацией | Подробности без скачивания огромного целого отчета, стабильные DTO/provenance/partial flags |
| P1 | Явные propose/verify/approve/reject fix operations | Отдельная подтверждаемая security workflow; atomic rollback/evidence, не считать кнопку подтверждением безопасности и не обходить policy checks |
| P1 | Cancel + явный новый retry | Изоляция отмены от HTTP AbortController; terminal semantics, cleanup, связь retry с исходным run и новая evidence chain |
| P1 | SSE/WebSocket или ограниченная events pagination | Cursor resume/duplicates/backpressure и terminal marker; обычный polling сохранить как fallback |
| P1 | Контролируемый artifact download | Manifest, hashes, доступ к candidate/diff/report без server absolute paths; authorization и ограничения объема |

Кандидат будущего start DTO (только **предложение**, текущий POST вернет 422):

```json
{
  "operation": "compatibility",
  "source_path": "tests/fixtures/universal_py3",
  "source_version": "3.12",
  "target_version": "3.13",
  "cases_profile": "universal_py3_offline",
  "max_iterations": 1
}
```

Пока backend/frontend владельцы не согласовали точные route names, поля,
versioning и error semantics, реализовывать следует только раздел 10.

## 12. Основания и проверка документа

Исходники: [API](api/main.py), [DTO](core/models.py), [RunStore](core/runs.py),
[reports](core/report.py), [migration](core/pipeline.py),
[P3 workflow](core/universal.py), [evidence](core/evidence.py),
[registry](core/versions.py), [security engine](security/engine.py),
[providers](security/providers.py), [LLMClient](llm/client.py).

`docs/BRIEF.md` на дату аудита отсутствует. Существующие DTO/endpoints сохранены;
документ не вводит контрактные поля из предложений. Примеры проверяются как
валидный JSON; полный RunState и POST DTO — существующими моделями; настоящие
P3 state/events/report projections сверяются с сохраненными артефактами.
Исторический полный P3-прогон: 154 passed (включая Docker). Для этого
документа нужны только быстрые тесты API/DTO/offline поведения, без тяжелых
Docker-прогонов и без Meta API.

Проверка текущего handoff:

```text
python -m pytest tests -q -m "not docker" -p no:cacheprovider
117 passed, 37 deselected in 9.61s
```

Все 11 JSON-примеров разобраны. Полный RunState и текущий POST body проверены
Pydantic-моделями; state, первые events и compatibility-проекция сопоставлены
с сохраненным P3-отчетом, проверены hashes событий и относительные ссылки.
Предлагаемый start DTO действительно отвергается текущей StartRun-моделью.
В этом этапе изменен только Markdown-документ; API и frontend не менялись.
