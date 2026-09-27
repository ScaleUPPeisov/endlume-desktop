# ENDLUME Studio — Release Contract 8.41+

## Цель
Выпускать стабильные версии ENDLUME Studio без повторяющихся installer/FIX-циклов. Для macOS Apple Silicon конечный пользователь должен получить готовую `ENDLUME Studio.app`, а начиная с 8.41 последующие обновления должны устанавливаться через `Настройки → Обновления` без Terminal.

## Критическое правило
СТРОГО НЕ ТРОГАТЬ функциональность, дизайн, кнопки, очередь, Effects, Subscribe, Library, лицензирование, single-app guard, FFmpeg/FFprobe, структуру проекта и существующие рабочие сценарии, если изменение прямо не относится к пунктам ниже.

## Обязательные пользовательские требования 8.41
1. Реальный финальный рендер 60 FPS, без скрытого clamp 60→30. При этом исходное изображение не ухудшать; итог 1920×1080, 16:9, cover/crop, без black bars.
2. Убрать зависания приложения после очередей около 100 видео. Не сериализовать тяжёлую render-history на каждом progress update; батчить UI progress и не блокировать WKWebView.
3. Effects/эквалайзер должны визуально работать плавно в 60 FPS; для low-FPS исходников использовать motion interpolation в preview/cache вместо простого дублирования кадров.
4. Убрать секундные разрывы музыки. Timeline/PTS должны быть непрерывными; длинная дорожка не должна иметь gap при loop boundary.
5. Обновления выпускаются в приложение через официальный Tauri updater.
6. macOS UI/меню/кнопки должны быть плавными, без искусственного 30 FPS ощущения; не ухудшать Windows.
7. Восстановить слышимый audio crossfade и существующий visual video xfade между склейками. Strict/Fidelity режим не имеет права принудительно выставлять crossfade=0.
8. Сохранить доказанный быстрый pipeline: около 30 секунд на типичное 2-часовое видео и примерно 700–1000 MB. Не увеличивать proven video budget без отдельного требования пользователя.
9. Улучшить chromakey/despill: не сбрасывать despill в 0 при persistence; убрать зелёный spill в render/cache/WebGL preview.
10. О программе: создатель `Kirill Peisov`, email `peisov.business@gmail.com`.

## Постоянные требования
- Noise 1 / Noise 2 отсутствуют.
- Старая иконка ENDLUME сохранена.
- 1920×1080 exact.
- 16:9 fill/crop; padding/black bars запрещены.
- 1 изображение + 10–15 треков; типичная длительность около 2 часов.
- Музыка высокого качества; если crossfade требует re-encode — использовать HQ 320 kbps, не низкий битрейт.
- FFmpeg и FFprobe должны быть внутри `.app` и executable.
- Ошибка одного проекта не останавливает очередь.

## Native updater
Использовать только официальный Tauri updater:
- `@tauri-apps/plugin-updater`
- `@tauri-apps/plugin-process`
- `check()`
- `downloadAndInstall()`
- `relaunch()`

Frontend не должен использовать:
- `local_update_check`
- `local_update_start`
- `local_update_status`

Updater endpoint:
`https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/latest.json`

`src-tauri/tauri.conf.json` должен содержать непустые `plugins.updater.pubkey` и `plugins.updater.endpoints`.
Capabilities обязаны содержать `updater:default` и `process:default`.

Публичный релиз НЕ считается опубликованным, пока реально не существуют одновременно:
- `latest.json`
- `ENDLUME-macos-aarch64.app.tar.gz`
- `ENDLUME-macos-aarch64.app.tar.gz.sig`

`latest.json` должен парситься как JSON, иметь правильную version, `darwin-aarch64.url` и непустую signature.

## Зафиксированная база 8.40
Для 8.41 использовать proven 8.40 base commit:
`4c1fcc30f5b8ef270484b5c61f8e26120d852b99`

Не использовать mutable `release` как application base во время bootstrap 8.41. Из текущего `release` допускается брать только явно перечисленные 8.41 patch/version/validator файлы.

## Запрещённые исторические ошибки
Перед долгой сборкой обязательный preflight должен исключить все случаи ниже.

### 1. 8.38 validator после version=8.40
`validate-release-8-38.sh` разрешён только до `apply-version-8-40.py`. После перехода на 8.40 его вызов запрещён.

### 2. 8.39 migration chain в bootstrap 8.40/8.41
Запрещены:
- `apply-performance-fidelity-8-39.py`
- `repair-render-chroma-8-39.py`
- `apply-hybrid-updater-8-39.py`
- `validate-release-8-39.sh`

### 3. Chroma repair loop
Не запускать historical structural chroma repair поверх дерева, где ожидаемого legacy chromakey expression уже нет.

### 4. Obsolete updater text self-failure
Patch не должен сам вставлять строку, которую затем считает запрещённой. Functional gate важнее хрупкого текстового совпадения.

### 5. Nested Python/heredoc/triple-quote generation
Запрещено генерировать Python через вложенные `f'''...'''`/`'''...'''` конструкции. Embedded Python обязан компилироваться `compile(...)`/`py_compile` до npm/cargo/Tauri.

### 6. AppleDouble
Удалять `._*`; не допускать AppleDouble в Tauri capabilities/resources. `COPYFILE_DISABLE=1`.

### 7. set -u/local declaration bugs
Не использовать значение shell local-переменной в той же declaration-строке до присваивания (`local name=... out="$name"`). Сначала объявить/присвоить, затем использовать.

### 8. Updater release assets empty
Нельзя сообщать «published» при `assets: []`. После upload обязательна повторная проверка GitHub release и публичного `latest.json`.

### 9. LaunchAgent PATH
Background builder обязан явно выставлять PATH для Homebrew Node/gh и `$HOME/.cargo/bin`; нельзя зависеть от interactive shell profile.

### 10. Signing key
Приватный updater key хранится только локально на Mac. Не загружать в GitHub/чат. Build использует локальный key path/environment.

## Preflight до долгой сборки
Обязательные быстрые проверки:
1. `bash -n` всех shell builder/publisher scripts.
2. `python3 -m py_compile` patch/version scripts.
3. Компиляция embedded Python из heredoc до запуска npm/cargo.
4. Проверка порядка historical validators/version migrations.
5. Проверка отсутствия forbidden 8.39 chain.
6. Проверка pinned base commit.
7. Проверка, что updater patch/version/gate идут в правильном порядке.
8. Проверка, что final Tauri build создаёт updater artifacts, а не использует config с `createUpdaterArtifacts=false`.

## Полный build gate macOS
Перед словом «готово» должны пройти:
- historical baseline gates в правильной точке миграции;
- 8.40 updater gate;
- 8.41 targeted gate;
- `npm run check`;
- `npm run build`;
- проверка основных button handlers;
- `cargo check --target aarch64-apple-darwin`;
- `npx tauri build --target aarch64-apple-darwin`;
- финальная `.app` проверка.

## Финальная `.app` проверка
- Bundle ID: `studio.endlume.desktop`
- Version: релизная версия
- Architecture: `arm64`
- `codesign --verify --deep --strict`
- FFmpeg executable
- FFprobe executable
- updater pubkey непустой
- updater endpoint правильный
- production frontend использует native Tauri updater
- production frontend не содержит `local_update_*`

## Пользовательский ZIP
Если нужен ручной bootstrap ZIP, внутри должен быть только:
`ENDLUME Studio.app`

Запрещены внутри пользовательского ZIP:
- `.command`
- исходники
- node_modules
- target
- `.git`
- build logs
- patch scripts

## Поведение при ошибке
Если сборка падает:
1. не создавать FIX1/FIX2/FIX3 по инерции;
2. зафиксировать точную failing line/root cause;
3. исправить исходный builder/patch;
4. увеличить generation для background retry;
5. повторить preflight/full gate;
6. не сообщать «готово», пока final artifact и updater channel реально не проверены.

## Definition of Done
Релиз считается завершённым только когда:
- приложение собрано на Apple Silicon Mac;
- `.app` прошла проверки;
- signed updater artifact создан;
- GitHub `endlume-stable` содержит три необходимых assets;
- публичный `latest.json` валиден;
- установленная предыдущая версия видит новую через `Настройки → Обновления`;
- пользователь не должен использовать Terminal для следующего обновления.
