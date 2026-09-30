import React from 'react';

type Release={version:string;date:string;current?:boolean;title:string;items:string[]};

const releases:Release[]=[
  {version:'10.0.3',date:'30.09.2026',current:true,title:'Performance Hotfix • Parallel AAC • 400–600 MB',items:[
    '1-image fast-path: 10 MP3 больше не перекодируются последовательно внутри final mux; Apple-compatible AAC 320k/48k/stereo кэшируется по каждой песне и строится параллельно.',
    'AAC playlist собирается packet-copy и переиспользуется между рендерами; warm render не выполняет повторное двухчасовое AAC-кодирование.',
    'Visual master и AAC cache готовятся параллельно, а final mux получает уже готовую AAC дорожку packet-copy.',
    'Interval visual master выбирается по целевому payload около 500 МБ при сохранении 100M physical-master fidelity; итоговый target 400–600 МБ.',
    'Для sample-table fast-path убрана лишняя middle video decode-проверка; обязательные Apple AAC / audible start-middle-end проверки сохранены.',
    'Цели QA: local Mac warm ≤10 сек, cold ≤22 сек; без потери HEVC 1080p60, Effects, Subscribe и слышимой музыки.'
  ]},
  {version:'10.0.2',date:'30.09.2026',current:false,title:'P0 Apple Audio • Fast Ping-Pong • Persistent AAC Cache',items:[
    'P0 macOS: финальный MP4 использует совместимую AAC-LC 320 кбит/с / 48 кГц / stereo дорожку с default disposition; AVFoundation больше не получает MP3-in-MP4.',
    'Короткое исходное видео в Ping-Pong собирается как короткий физический цикл, а двухчасовой таймлайн расширяется через zero-copy sample-table без многочасового перекодирования.',
    'Persistent Ping-Pong AAC cache строится параллельно visual cache и повторно используется на warm render.',
    'Финальный Ping-Pong mux переведён на packet-copy video + packet-copy AAC; повторное двухчасовое AAC-кодирование убрано.',
    'Сохранены HEVC 1080p60, Effects, Subscribe, резкость, полные песни, target-size и текущая updater identity.'
  ]},
  {version:'10.0.1',date:'30.09.2026',current:false,title:'P0 Audio Compatibility • AAC-LC Final MP4',items:[
    'P0: исправлен финальный MP4 без слышимого звука в системных проигрывателях.',
    'Исходные MP3 сохраняют порядок и полную длительность, но финальный MP4 получает совместимую AAC-LC 320 кбит/с / 48 кГц / stereo дорожку вместо MP3-in-MP4.',
    'AAC-дорожка помечается default audio track; уже обработанный AAC повторно не перекодируется.',
    'Release gate дополнен нативным AVFoundation decode на macOS плюс проверкой громкости начала и середины.',
    'HEVC 1080p60, Effects, Subscribe, persistent visual cache, sample-table zero-copy и updater identity не изменены.'
  ]},
  {version:'10.0.0',date:'29.09.2026',current:false,title:'Grand Performance • Persistent Masters • Scheduling',items:[
    'Effects и Subscribe: ВЫКЛ / ВСЕГДА / ПО ИНТЕРВАЛУ.',
    'Subscribe: интервал, длительность показа, первое появление и live calculation.',
    'Persistent visual/Subscribe masters и zero-copy 10.0 performance path.',
    'P0 Audio: финальный gate теперь отклоняет silent/near-silent MP4 и не показывает ложное «Готово».',
    'Сохранены 1080p60 HEVC, Original MP3 packet-copy, проекты, лицензия и updater identity.'
  ]},
  {version:'1.0.0-alpha.8.67',date:'29.09.2026',current:false,title:'Render Performance • 30s Gate • Whole MP3 Fidelity',items:[
    'Реальный First Pour Jazz / 005 на TOSHIBA EXT ускорен с 112+ секунд до 28.51 секунды при сохранении HEVC 1920×1080/60.',
    'macOS periodic fast-path использует аппаратный hevc_videotoolbox с приоритетом скорости и реальным CBR video payload; software encoder остаётся только fallback.',
    'Strict whole-track для совместимых MP3 сохраняет исходные MP3 packets без AAC-перекодирования: crossfade/LUFS не применяются, потому что они изменяют сигнал и укорачивают песни.',
    'Все 10 исходных песен сохраняются целиком; финальная длительность строится только по полным track boundaries без early EOF.',
    'Effects и Subscribe остаются в lossless pre-render cache; финальный gate проверяет visual SSIM, HEVC 1080p60, аппаратный encoder, декодирование хвоста и размер около 500 МБ.',
    'Для точного проекта 005 подтверждено: 28.51 сек, 513.0 МБ, 537925718 bytes, Original MP3 packet-copy, hevc_videotoolbox.'
  ]},
  {version:'1.0.0-alpha.8.66',date:'29.09.2026',current:false,title:'Live Preview Recovery • Effects / Subscribe',items:[
    'Live Preview proxy теперь проверяется фактически: размер файла, FFprobe video stream / geometry / duration и декодирование стартового кадра.',
    'Если VideoToolbox завершился с exit code 0, но proxy пустой или повреждён, ENDLUME автоматически удаляет его и пробует libx264.',
    'Для проблемных Effects/Subscribe добавлен последний preview-only fallback: libx264 + обычный fps=60 без minterpolate; production render не переключается на этот путь.',
    'Битый live-preview-v6 cache больше не считается валидным и пересоздаётся; корректный cache повторно не кодируется.',
    'Production render, HEVC 1080p60, Original MP3 packet-copy, Effects/Subscribe compositing, расписание и updater feed сохранены без изменений.'
  ]},
  {version:'1.0.0-alpha.8.65',date:'26.09.2026',current:false,title:'Real Result State • FAST_ONE_IMAGE • Homer Startup',items:[
    'Успешный render теперь сохраняет точные resultPath и resultBytes прямо из RenderOutcome; поздний terminal snapshot больше не может затереть валидные данные null-значениями.',
    'Кнопки «Открыть видео» и «Открыть папку вывода» снова получают настоящий путь результата, а размер файла отображается из фактически созданного output.',
    'Обычный проект с одной картинкой без активных Effects/Subscribe переведён на короткий physical still + zero-copy sample-table вместо кодирования 12–60 секунд одинакового strict master.',
    'В сводке времени скрыты compatibility-alias тайминги, чтобы visual/audio/validation этапы не выглядели продублированными.',
    'При каждом запуске Homer splash виден минимум около 1.15 секунды и показывает полное название ENDLUME YT Studio PEISOV • Long Video Engine.',
    'Сохранены HEVC 1920×1080/60, Original MP3 packet-copy, whole-song, updater signature/SHA-256, queue recovery и cross-platform updater.'
  ]},
  {version:'1.0.0-alpha.8.64',date:'26.09.2026',current:false,title:'Windows Turbo Renderer • Full-screen Update Center',items:[
    'Windows fast-path ускорен: Original MP3 идёт packet-copy через direct concat-list без лишней полной промежуточной сборки аудиоплейлиста.',
    'MP3 metadata probing выполняется кэшированными ограниченно-параллельными FFprobe задачами; выбор NVENC / QSV / AMF сохраняется по GPU/driver fingerprint и пересчитывается при изменении железа.',
    'Убран искусственный hard-limit 700 МБ: размер остаётся целевым диапазоном, но исходная музыка не ухудшается и не отклоняется только ради размера файла.',
    'Финальная проверка дополнительно декодирует начало, середину, последние 10 секунд, хвост и переход между первой и второй песней.',
    'Обновления получили полноэкранный ENDLUME Update Center с реальным progress/speed/ETA, SHA-256 gate и локальным Homer asset; после фактической смены версии показывается компактное подтверждение.',
    'Сохранены 1920×1080, 60 FPS, HEVC/H.265, Original MP3 packet-copy, whole-song и zero-copy sample-table архитектура.'
  ]},
  {version:'1.0.0-alpha.8.63',date:'19.09.2026',current:false,title:'macOS Managed Access • Native Updater • PEISOV Parity',items:[
    'macOS Apple Silicon переведён на managed-license backend ENDLUME: уникальные customer keys, OWNER lifetime, device binding, heartbeat и remote revoke.',
    'Session token на Mac хранится в native Keychain через keyring apple-native; device_id сохраняется между перезапусками.',
    'macOS updater переведён с GitHub CLI/shell bootstrap на подписанный Tauri updater с обязательной SHA-256 проверкой перед install.',
    'Название приложения унифицировано: ENDLUME YT Studio PEISOV, включая bundle title и канонический /Applications path.',
    'Сохранены production fixes 8.62: queue dedupe, revoke-finalization hardening, 160-bit license keys и natural output без synthetic padding.'
  ]},
  {version:'1.0.0-alpha.8.62',date:'18.09.2026',current:false,title:'Production QA • License Security • Queue/Revoke Hardening',items:[
    'Managed License key generation hardened from 80-bit to 160-bit cryptographic keys while preserving activation of existing legacy keys.',
    'Database enforces owner/managed consistency, SHA-256 hash shape and device↔license isolation for sessions, renders and render events.',
    'Backend queue rejects duplicate project IDs even under repeated/direct Tauri enqueue calls and recovery.',
    'Remote revoke is enforced through final manifest/FFprobe/output finalization, not only while FFmpeg is running.',
    'Synthetic MOV free-atom/zero padding removed: output size now reflects actual media payload instead of artificial filler.',
    'Production 8.61 release remains immutable; these runtime fixes are isolated to the 8.62 patch candidate.'
  ]},
  {version:'1.0.0-alpha.8.61',date:'07.09.2026',current:false,title:'External Disk Render Stability',items:[
    'Рабочие master/audio/manifest файлы one-image рендера перенесены с внешнего output-диска в локальный cache Mac.',
    'На TOSHIBA/другой выбранный диск итоговый MOV записывается один раз после завершения локального zero-copy manifest.',
    'Убрано накопительное замедление проектов из-за многократной тяжёлой записи временных файлов на внешний диск.',
    'Сохранены HEVC VideoToolbox q:v100, GOP1800, 1920×1080 CFR60, original MP3 packet-copy, whole-song, Effects/Subscribe, 500–700 МБ и VYRON contracts.'
  ]},
  {version:'1.0.0-alpha.8.60',date:'07.09.2026',current:false,title:'Render Speed Stability • Equalizer Carry-Forward',items:[
    'Статичная картинка 1920×1080 масштабируется/crop один раз на проект вместо повторной обработки каждого кадра strict master.',
    'Физический gate проверяет 5 последовательных реальных master подряд с пределом 30 секунд на каждый, чтобы не возвращался рост времени очереди.',
    'Zero-copy manifest обновляет sample tables in-place без повторной полной перезаписи большого MOV.',
    'Круглый эквалайзер использует защищённый chromakey 0.18 / 0.03 и в Strict Effects cache, поэтому не становится тусклым в реальном рендере.',
    'Сохранены HEVC VideoToolbox q:v100, GOP1800, 1920×1080 CFR60, untouched MP3, whole-song, Effects/Subscribe, 500–700 МБ, VYRON и queue contracts.'
  ]},
  {version:'1.0.0-alpha.8.58',date:'06.09.2026',current:false,title:'Queue Finalization • Dual Terminal Ack',items:[
    'Исправлена гонка Render Center: отложенный requestAnimationFrame progress=97 больше не может перезаписать уже полученный render-done=100.',
    'Добавлен второй независимый terminal-ack от backend queue snapshot: даже если render-done задержан или потерян, готовый файл принудительно переводит карточку в Готово / 100%.',
    'Backend хранит до 500 terminal-состояний текущей сессии и восстанавливает resultPath/resultBytes по реально созданному MP4/MOV в папке результата.',
    'Статусы done/error остаются монотонными: поздние render-progress и queue-changed не возвращают завершённый проект в rendering/queued.',
    'Regression gate проверяет 40/40 проектов, потерю render-done, поздний 97%, stale queue snapshot и восстановление отсутствующей карточки.',
    'Render Core 8.57 не менялся: HEVC VideoToolbox q:v 100, GOP 1800, 1920×1080/60, untouched MP3, Effects/Subscribe и 500–700 МБ сохранены.'
  ]},
  {version:'1.0.0-alpha.8.57',date:'06.09.2026',current:false,title:'Strict Master Integrity • Safe VideoToolbox GOP',items:[
    'Исправлена отдельная ошибка lifetime keyed Effects: короткий cached Effect больше не завершает Strict master раньше базового таймлайна.',
    'Физическая диагностика Apple Silicon выявила отдельный HEVC VideoToolbox дефект длинного GOP: GOP 3381 записывал 3381 packets, но декодировались только 2048 frames с RPS/POC errors.',
    'Для HEVC VideoToolbox keyframe interval ограничен 1800 кадрами; полный master остаётся 3381 кадров, 1920×1080/60 FPS и q:v 100.',
    'Strict runtime проверяет decoded frames и encoded packets для master, Subscribe-сегментов и seed до zero-copy expansion.',
    'Перед render-done итог дополнительно проверяется: HEVC/yuv420p, 1920×1080/60, untouched MP3, 500–700 МБ, точная длительность и seek/decode в начале, середине и хвосте.',
    'Экран Обновления и О программе синхронизирован с текущей версией 8.57; VYRON bridge и updater identity сохранены.'
  ]},
  {version:'1.0.0-alpha.8.56',date:'05.09.2026',current:false,title:'Render Isolation • Strict Output Contract',items:[
    'Strict one-image render изолирован от software fallback и случайных legacy-путей.',
    'Whole-track audio и нулевой crossfade закреплены для производственного VYRON-пайплайна.',
    'Финальный файл проходит строгий контракт размера 400–700 МБ и проверку результата до публикации.'
  ]},
  {version:'1.0.0-alpha.8.41',date:'31.08.2026',current:false,title:'60 FPS • Stability • Gapless Audio • Chroma',items:[
    'Smart/Fidelity render снова работает в реальных 60 FPS без изменения проверенного 500k видеобюджета и быстрого short-master pipeline.',
    'Effects/Equalizer получают motion-interpolated 60 FPS cache и 60 FPS Live Preview вместо простого дублирования 25/30 FPS кадров.',
    'История 100+ рендеров больше не сериализуется в localStorage на каждом progress event; UI progress синхронизируется через requestAnimationFrame.',
    'Crossfade 3 сек восстановлен. Обработанная музыка — HQ 320 кбит/с с нормализованными timestamps и непрерывной long-audio дорожкой без секундных пауз.',
    'Chromakey получил despill с сохранением настройки, новый default 0.35 и отдельный регулятор для удаления зелёного/синего ореола.',
    'О программе: Kirill Peisov • peisov.business@gmail.com. Обновления устанавливаются штатным подписанным Tauri updater внутри ENDLUME.'
  ]},
  {version:'1.0.0-alpha.8.40',date:'31.08.2026',current:false,title:'Native Signed Updates',items:[
    'Чистый bootstrap интернет-обновлений на последней доказанно стабильной базе 8.38 — без запуска проблемной цепочки 8.39 при установке.',
    'Update Center переведён на официальный Tauri updater: проверка, скачивание, проверка подписи, установка и перезапуск выполняются внутри приложения.',
    'GitHub Actions, Cloudflare, VPS, IP и SSH больше не нужны установленному ENDLUME для получения обновлений.',
    'Исходный репозиторий остаётся приватным; публичный канал содержит только подписанные updater-пакеты и latest.json.',
    'Исправления 60 FPS/crossfade/chroma из ветки 8.39 будут возвращены отдельным удалённым релизом после перехода на новую систему обновлений.'
  ]},
  {version:'1.0.0-alpha.8.38',date:'27.08.2026',current:false,title:'YouTube Fill 16:9 — No Black Bars',items:[
    'One-image YouTube рендер всегда заполняет весь кадр 1920×1080 без letterbox/pillarbox.',
    'Вместо decrease + pad используется increase + center crop: изображения не 16:9 слегка обрезаются по краям, а не дополняются чёрными полосами.',
    'Lanczos + accurate rounding, x265-first CRF18, original MP3 bitstream-copy, Preview Shield и Remote Update Center сохранены.',
    'Release gate отдельно проверяет квадратный и вертикальный исходник: итог должен быть ровно 1920×1080 и pipeline не должен содержать pad.'
  ]},
  {version:'1.0.0-alpha.8.37',date:'27.08.2026',current:false,title:'Remote Update Center',items:[
    'ENDLUME больше не собирает обновления на пользовательском Mac: npm/Rust/Tauri-компиляция перенесена на удалённый macOS runner.',
    'Настройки → Обновления теперь разделены на Проверить обновления и Установить и перезапустить.',
    'Готовая .app скачивается из приватного GitHub release, проверяется SHA-256, Bundle ID, версия и codesign перед заменой.',
    'При установке используется atomic swap с предыдущей .app и rollback при ошибке.',
    '1080p Fidelity Lock, original MP3 bitstream-copy, Preview Shield и AppleDouble-защита сохранены.'
  ]},
  {version:'1.0.0-alpha.8.36',date:'27.08.2026',current:false,title:'1080p Fidelity Lock',items:[
    'One-image проекты теперь рендерятся строго 1920×1080: 4K больше не тратит битрейт впустую при лимите около 1 ГБ.',
    'Исходная картинка масштабируется один раз напрямую из оригинала фильтром Lanczos + accurate rounding.',
    'Короткий master кодируется x265-first: CRF 18 защищает первый I-frame от мозаики, VBV 550 кбит/с ограничивает динамические Effects, VideoToolbox остаётся fallback.',
    '30 FPS, H.265, original MP3 bitstream-copy, отключение crossfade/LUFS/ambient в one-image Fidelity Lock сохранены.',
    'Контрольный gate проверяет точные 1920×1080, SSIM первого кадра, динамический bitrate budget и скорость короткого master.',
    'AppleDouble build-workspace shield, Preview Shield v6, очередь, updater и удаление Noise 1/2 сохранены.'
  ]},
  {version:'1.0.0-alpha.8.35',date:'27.08.2026',current:false,title:'Strict Fidelity • 1-minute target',items:[
    'Для проекта 1 изображение + музыка Smart Repeat рендерится максимум в 30 FPS: статичная картинка не теряет деталей, а нагрузка Effects/Subscribe снижается примерно вдвое относительно старого 60 FPS профиля.',
    'Убран двухсекундный GOP, который создавал слишком много тяжёлых 4K I-кадров. Теперь один GOP покрывает полный short-master, а VideoToolbox получает увеличенный 64 MB buffer для чистого первого кадра.',
    '4K video budget настроен на 740 кбит/с; вместе с типичным оригинальным MP3 320 кбит/с расчётный двухчасовой payload около 0.954 GB, оставляя запас под контейнер.',
    'Strict Fidelity отключает crossfade/LUFS/ambient только для one-image профиля, чтобы музыка шла точным MP3 bitstream-copy без повторного lossy-кодирования и без многогигабайтного ALAC.',
    'Если исходные аудиофайлы невозможно объединить точным MP3 copy, ENDLUME теперь показывает понятную ошибку вместо скрытого перехода на большой ALAC-файл.',
    'Новые настройки по умолчанию: 4K, HEVC, 30 FPS, crossfade выключен. Старый сохранённый 4K60/crossfade=3 профиль мигрирует один раз.',
    'AppleDouble Preview Shield, Live Preview v6, удаление Noise 1/2, предыдущая ENDLUME infinity-иконка и все queue/updater исправления сохранены.'
  ]},
  {version:'1.0.0-alpha.8.34',date:'27.08.2026',current:false,title:'Preview Shield + 100/100 Stability Gate',items:[
    'Effects и Subscribe: кроме ._* ENDLUME теперь проверяет AppleDouble/resource-fork по сигнатуре файла, поэтому даже переименованный служебный файл не попадёт в FFmpeg.',
    'Live Preview cache переведён на v6, чтобы старые повреждённые preview-файлы не переиспользовались.',
    'Импорт Effects/Subscribe блокирует служебные macOS-файлы до копирования в постоянную библиотеку.',
    'Noise 1 и Noise 2 остаются полностью удалёнными.',
    'Сохранён Fast Fidelity: Apple HEVC VideoToolbox first, libx265 fallback, короткий master, повторное использование Subscribe и direct concat.',
    'Целевой профиль 1 изображение + 10–15 треков + 2 часа сохранён: 700–1000 МБ при типичном 320 кбит/с MP3 и компактном HEVC budget.',
    'Оригинальный MP3 идёт bitstream-copy; при реальном crossfade используется lossless ALAC.',
    'Возвращена прежняя прозрачная ENDLUME infinity-иконка без чёрного квадратного фона.',
    'Перед установкой выполняется отдельный 100/100 Effects+Subscribe preview stability smoke; при любом сбое старая ENDLUME не заменяется.'
  ]},
  {version:'1.0.0-alpha.8.33',date:'27.08.2026',current:false,title:'SSD Fast Fidelity + Effects/Subscribe Fix',items:[
    'Исправлена ошибка Live Preview Invalid PNG signature 0x516070020000: ENDLUME теперь игнорирует служебные macOS AppleDouble-файлы ._*, которые появляются на внешних SSD.',
    'Тяжёлый render-work для проекта создаётся на выбранном диске результата. При сохранении на внешний SSD внутренний диск Mac больше не используется под многогигабайтные промежуточные видео.',
    'Для проекта «1 изображение + Effects + Subscribe» первый проход использует аппаратный HEVC VideoToolbox; libx265 CRF14 остаётся автоматическим quality fallback.',
    'Effects и Subscribe в Smart Fidelity компонуются прямо из исходных файлов без огромного qtrle-cache на внутреннем диске и без лишнего поколения перекодирования.',
    'Длина короткого master подстраивается под длительность непрерывного Effect, чтобы не обрывать эффект.',
    'Повторяющиеся Subscribe-композиты переиспользуются, а финальный Smart Fidelity mux читает concat-сегменты напрямую — убрана одна полная дополнительная копия двухчасовой видеодорожки.',
    'Noise 1 и Noise 2 полностью удалены из UI, TypeScript, Rust settings и render filter.',
    'Кроссфейд, Original Audio MP3 bitstream-copy, lossless ALAC fallback, очередь и in-app updater сохранены.',
    'Возвращена фирменная ENDLUME infinity-иконка без чёрной квадратной рамки.'
  ]},
  {version:'1.0.0-alpha.8.32',date:'26.08.2026',current:false,title:'Queue Sync + обновления полностью внутри ENDLUME',items:[
    'Исправлена потеря второго и следующих проектов в окне Рендер: UI теперь синхронизируется с реальной backend-очередью через queue-changed и queue_snapshot.',
    'Каждое добавление в очередь получает уникальный job ID, поэтому одну и ту же папку можно отправить повторно, не скрывая новый рендер.',
    'Список рендеров сохраняется между переходами по вкладкам и перезапуском приложения; готовые проекты не исчезают при добавлении новой задачи.',
    'Добавлен приватный In-App Update Center: проверка, сборка, тесты и установка запускаются из ENDLUME без Terminal и без GitHub Actions.',
    'Обновление использует уже авторизованный GitHub CLI только как безопасный доступ к приватному release-каналу; исходное приложение не заменяется до прохождения всех gates.',
    'Во время обновления в приложении отображаются текущий этап и процент; в момент atomic swap ENDLUME перезапускается автоматически.',
    'Сохранены 8.31: живые этапы рендера, реальный lossless-crossfade, Noise 1/2, Effects/Subscribe и Hybrid Fidelity.'
  ]},
  {version:'1.0.0-alpha.8.31',date:'26.08.2026',current:false,title:'Render Center Live + рабочий lossless crossfade + встроенный Шум 1/2',items:[
    'Render Center теперь всегда показывает фактический текущий этап и процент, даже если backend использует новый Hybrid Fidelity stage.',
    'Кроссфейд в статичных проектах больше не игнорируется: переход реально строится через acrossfade.',
    'После кроссфейда музыка сохраняется в ALAC lossless, поэтому нет повторного AAC/MP3 lossy-сжатия. При выключенном кроссфейде совместимые MP3 остаются bitstream-copy.',
    'Добавлены встроенные эффекты «Шум 1» и «Шум 2» с отдельным ВКЛ/ВЫКЛ; внешний overlay-файл не нужен.',
    'Большой служебный блок ORIGINAL/HYBRID FIDELITY удалён из основного интерфейса.',
    'Сохранены fresh-clone builder, Effects/Subscribe gates, 4K SSIM gate, compact short-master и atomic install/rollback.'
  ]},
  {version:'1.0.0-alpha.8.30',date:'26.08.2026',current:false,title:'Stability Gate 2: установка без patch-drift + exact MP3 + компактный 2ч render',items:[
    'Установщик собирает проект только из чистого fresh-clone и не использует старый локальный source-cache.',
    'Hybrid Fidelity patcher стал идемпотентным: повторная установка не зависит от точной minified-строки Subscribe.',
    'Перед заменой приложения проходят Python syntax, TypeScript, Vite, Rust, Render, Effects, Subscribe, 4K fidelity и exact-MP3 runtime gates.',
    'Финальная ENDLUME Studio.app дополнительно проверяется уже со встроенными FFmpeg/FFprobe.',
    'Совместимые MP3 копируются без повторного lossy-кодирования; при несовместимости качество имеет приоритет над размером.',
    'Для типового проекта 1 картинка + небольшие Effects/Subscribe цель остаётся около 1 ГБ на 2 часа при visually-lossless 4K gate.'
  ]},
  {version:'1.0.0-alpha.8.28',date:'26.08.2026',current:false,title:'Hybrid Fidelity: маленький файл + живой MP3 + короткий master',items:[
    'Исправлена причина файла 14–17 ГБ: VideoToolbox q95 больше не кодирует весь повторяющийся визуальный master с огромным средним битрейтом.',
    'Для проекта «1 изображение + музыка + Effects/Subscribe» исходная картинка идёт напрямую в короткий 30-секундный x265 CRF14 master без предварительного пережатия.',
    'Короткий master повторяется через stream-copy; статичные пиксели и небольшие Effects хорошо сжимаются, поэтому двухчасовой проект больше не обязан занимать десятки гигабайт.',
    'Effects и Subscribe продолжают использовать lossless qtrle chromakey-cache, сохраняют aspect ratio и кодируются только в коротких сегментах/master.',
    'Совместимые MP3 сначала очищаются stream-copy от ID3/Xing, затем объединяются как непрерывный MP3-поток с новыми монотонными таймстампами. Аудиосэмплы не перекодируются.',
    'Original Fidelity теперь сохраняется в QuickTime MOV: это устраняет сценарий, когда MP3-трек присутствует в MP4, но QuickTime Player воспроизводит видео без звука.',
    'Перед успешным рендером ENDLUME не только видит аудиотрек через FFprobe, но и реально декодирует его тестовый фрагмент.',
    'Если MP3 имеют несовместимые параметры, остаётся ALAC lossless fallback вместо AAC.'
  ]},
  {version:'1.0.0-alpha.8.27',date:'25.08.2026',current:false,title:'Original Fidelity: музыка без повторного lossy-кодирования + quality-first видео',items:[
    'Для проектов «1 изображение + музыка + Effects/Subscribe» включён Original Fidelity.',
    'Совместимые MP3 с одинаковыми sample rate/channel layout объединяются через stream-copy: аудиокадры не перекодируются.',
    'Кроссфейд, LUFS-нормализация и ambient автоматически не применяются в Original Fidelity, потому что любая такая обработка требует изменения исходного аудиосигнала.',
    'Если MP3 нельзя безопасно stream-copy объединить, ENDLUME использует ALAC lossless fallback вместо AAC; файл может стать больше 1 ГБ.',
    'Убран жёсткий 520–700 кбит/с лимит для Smart Repeat: изображение и Effects больше не портятся ради размера.',
    'На Apple Silicon Original Fidelity использует HEVC VideoToolbox quality-first; software fallback — x265 CRF 14.',
    'Effects/Subscribe по-прежнему композятся из lossless qtrle chromakey-cache и сохраняют исходное соотношение сторон.',
    '20–30 секунд остаются архитектурной целью для короткого master + stream-copy mux, но качество имеет приоритет над обещанием размера или времени.'
  ]},
  {version:'1.0.0-alpha.8.26',date:'25.08.2026',current:false,title:'Smart Repeat: 2 часа около 700–1000 МБ и быстрый финальный mux',items:[
    'Smart Size теперь работает не только для чистой картинки, но и для проекта «1 изображение + Effects + Subscribe».',
    'Для 2 часов целевой бюджет видео: 520 кбит/с для 1080p, 600 кбит/с для 1440p и 700 кбит/с для 4K; вместе с AAC 320 кбит/с это примерно 700–1000 МБ.',
    'Постоянные Effects больше не переводят весь двухчасовой ролик на пользовательские 20–30 Мбит/с.',
    'Вариант Effects собирается напрямую из исходного изображения, чтобы не делать лишнее повторное сжатие фоновой картинки.',
    'ENDLUME учитывает длительность исходного Effect-loop до 60 секунд, чтобы длинная анимация не перезапускалась каждые 8–12 секунд.',
    'Финальный mux остаётся stream-copy: уменьшение визуального потока с десятков гигабайт до ~1 ГБ резко сокращает время последнего этапа.',
    'Для обычных видео-проектов Smart Repeat не включается: их пользовательский профиль качества остаётся без изменений.'
  ]},
  {version:'1.0.0-alpha.8.25',date:'25.08.2026',current:false,title:'Render Recovery + Effects/Subscribe Stability',items:[
    'Сборка больше не переписывает исходники Python-hotfix скриптами при каждом npm/Tauri build: TypeScript собирается из стабильного исходного кода.',
    'Рендер использует writable app-cache workspace и автоматически переключает недоступную папку результата на Movies/ENDLUME Studio.',
    'Первая попытка использует аппаратный кодировщик, вторая принудительно libx264/libx265 вместо повторения того же сломанного encoder.',
    'Сломанный или потерянный Effect/Subscribe пропускается с предупреждением и больше не валит весь проект.',
    'Effects и Subscribe используют одинаковую с Preview центрированную X/Y/SIZE геометрию и сохраняют исходное соотношение сторон.',
    'Subscribe импортируется в собственную managed-библиотеку, новые Effects/Subscribe автоматически ставятся по центру.',
    'MP3 до acrossfade нормализуются в 48 kHz stereo/fltp; stale пути проекта восстанавливаются повторным сканированием папки.',
    'Перед локальной установкой обязательны TypeScript, frontend, Rust, 100 Loop Mode тестов, Effects/Subscribe aspect test и финальный video+audio mux test.'
  ]},
  {version:'1.0.0-alpha.8.19',date:'24.08.2026',title:'Chromakey Fidelity + Render Recovery',items:[
    'Chromakey переведён на RGB colorkey: видимые пиксели Effects/Subscribe сохраняют исходный цвет без прежней глобальной saturation/despill коррекции.',
    'В Live Preview добавлена «ПИПЕТКА / КИСТЬ»: можно кликнуть или провести по фону overlay-видео и взять реальный цвет chromakey из исходного кадра.',
    'Старые пресеты с Similarity/Blend около 0.9–1.0 автоматически приводятся к безопасным значениям и получают новый fidelity-cache.',
    'Вторая попытка рендера теперь принудительно переключается с hardware encoder на libx264/libx265 software fallback.',
    'Финальный stream-copy mux получил безопасную генерацию timestamp без повторного кодирования видео или музыки.',
    'FFmpeg-ошибки теперь сохраняют название конкретного этапа, чтобы следующая ошибка была диагностируема, а не скрыта общим сообщением.',
    'Локальный release-gate дополнен отдельным green-screen/colorkey smoke-test и проверкой software encoder retry.'
  ]},
  {version:'1.0.0-alpha.8.18',date:'24.08.2026',title:'Render Recovery: обычные папки, managed overlays и updater timeout',items:[
    'Обычный проект «1 PNG + MP3» теперь входит в обязательный end-to-end release regression и должен собрать валидный MP4 с видео и аудио до публикации обновления.',
    'MP3 с разными sample rate, mono/stereo и Unicode/французскими именами нормализуются перед acrossfade к 48 kHz / stereo / fltp.',
    'Если сохранённые пути PNG/MP3 устарели после обновления или перемещения папки, ENDLUME повторно сканирует саму папку проекта и восстанавливает актуальные пути перед рендером.',
    'Выключенные Effects/Subscribe не обращаются к source-файлам. Включённый overlay с потерянным файлом пропускается с предупреждением и больше не валит основной рендер.',
    'Новые Effects, Subscribe и ambient копируются во внутреннюю managed-библиотеку ENDLUME и не зависят от Downloads/Desktop после импорта.',
    'Проверка обновлений ограничена 12 секундами и больше не должна навсегда оставлять кнопку в состоянии «ПРОВЕРЯЮ…».',
    'Перед созданием подписанного updater release pipeline принудительно применяет render hotfix, 100 Loop Mode smoke-checks, normal-folder regression, Motion/UI checks и Rust/Frontend checks.'
  ]},
  {version:'1.0.0-alpha.8.17',date:'24.08.2026',title:'Hotfix: обычный рендер, Effects/Subscribe и зависание обновлений',items:[
    'Подготовлены исправления stale overlay, mixed-MP3 и updater timeout.',
    'Добавлена managed-библиотека для Effects, Subscribe и ambient.',
    'Добавлено самовосстановление путей проекта перед рендером.'
  ]},
  {version:'1.0.0-alpha.8.16',date:'23.08.2026',title:'Fixed footer и безопасные route-анимации',items:[
    'Нижняя панель «Добавить в очередь» снова закреплена к viewport и не перекрывает параметры после прокрутки.',
    'Корневой route-wrapper больше не использует transform/filter/perspective, которые ломали position: fixed в macOS WKWebView.',
    'Переходы страниц сохранены через лёгкую opacity-анимацию; нативная прокрутка macOS и GPU Live Preview сохранены.',
    'Добавлены 16 обязательных motion/layout проверок release pipeline.'
  ]},
  {version:'1.0.0-alpha.8.15',date:'23.08.2026',title:'Нативная плавная прокрутка macOS',items:[
    'Убраны тяжёлые JS wheel/scroll перехваты и per-frame governor из обычной прокрутки.',
    'Скролл оставлен нативному WKWebView/macOS для максимально стабильного ощущения.',
    'Правый scrollbar скрыт, рабочая область очищена от лишнего визуального шума.'
  ]},
  {version:'1.0.0-alpha.8.14',date:'23.08.2026',title:'Motion Engine: плавная прокрутка и переходы',items:[
    'Добавлен Motion Layer для плавных переходов между разделами и hover/press-анимаций.',
    'Прокрутка и переходы оптимизированы под compositor-friendly свойства.',
    'Добавлены release-проверки motion-архитектуры.'
  ]},
  {version:'1.0.0-alpha.8.13',date:'23.08.2026',title:'GPU Live Preview, LoopForge-полировка и проверка Loop Mode',items:[
    'Effects и Subscribe переведены на GPU Live Preview без FFmpeg на каждом движении.',
    'Положение и размер двигаются вместе с реальным эффектом на частоте дисплея.',
    'Loop Mode проходит 100 FFmpeg smoke-тестов: Image, Crossfade, Ping-pong и Без обработки.',
    'Карточки, значения, пресеты и ползунки приведены к компактному dark-glass стилю.'
  ]},
  {version:'1.0.0-alpha.8.12',date:'15.08.2026',title:'Компактная neon-навигация',items:[
    'Проект, Рендер, Библиотека и Настройки стали компактнее.',
    'Активная вкладка получила cyan/violet/pink подсветку и тонкий градиентный контур.'
  ]},
  {version:'1.0.0-alpha.8.11',date:'15.08.2026',title:'Полная история релизов и нормализация имени',items:[
    'История обновлений вынесена в Настройки → Обновления.',
    'Каноническое имя macOS-приложения закреплено как ENDLUME Studio.app.'
  ]},
  {version:'1.0.0-alpha.8.10',date:'15.08.2026',title:'Fast Engine benchmark без ложных результатов',items:[
    'Benchmark выбирает кодировщик только после реального encode-test.',
    'Проверяются h264_videotoolbox, hevc_videotoolbox и libx264.'
  ]},
  {version:'1.0.0-alpha.8.9',date:'15.08.2026',title:'Одна установка и постоянные уведомления',items:[
    'Канонический путь на Mac: /Applications/ENDLUME Studio.app.',
    'Single App Guard удаляет старые дубликаты с тем же bundle ID.'
  ]},
  {version:'1.0.0-alpha.8.8',date:'15.08.2026',title:'История обновлений и нормальное имя приложения',items:[
    'Добавлена история alpha-релизов.',
    'ENDLUME приводит старые имена app-bundle к ENDLUME Studio.app.'
  ]},
  {version:'1.0.0-alpha.8.7',date:'15.08.2026',title:'Single App Guard и плавный редактор',items:[
    'Single App Guard оставляет одну актуальную ENDLUME.',
    'Drag/resize Effects/Subscribe вынесены из React-state на requestAnimationFrame.'
  ]},
  {version:'1.0.0-alpha.8.6',date:'14.08.2026',title:'Effects, Live Preview и ускорение overlay',items:[
    'Новая macOS-иконка ENDLUME.',
    'Subscribe, Effects и ambient получили ВКЛ/ВЫКЛ.',
    'Preview переведён на Apple VideoToolbox 60 FPS proxy 960×540.',
    'Render Center показывает реальный SSD.'
  ]},
  {version:'1.0.0-alpha.8.5',date:'13.08.2026',title:'Уведомление об обновлении',items:[
    'Добавлены Обновить и Обновить позже.',
    'Прогресс скачивания/установки показывается внутри приложения.'
  ]},
  {version:'1.0.0-alpha.8.4',date:'13.08.2026',title:'Подписанный встроенный Updater',items:[
    'Добавлен подписанный ENDLUME Updater.',
    'Update-пакеты проверяются криптографической подписью.'
  ]},
  {version:'1.0.0-alpha.8.3',date:'13.08.2026',title:'Smart Size и быстрый статичный master',items:[
    'Smart Size использует короткий 8–12-секундный master.',
    'Для статичной картинки применяется короткий master, затем stream-copy.'
  ]},
  {version:'1.0.0-alpha.8.2',date:'13.08.2026',title:'Render Center, таймеры и Static Master',items:[
    'Таймеры Прошло/Осталось идут непрерывно.',
    'Добавлены Static Master Engine и AudioToolbox AAC.'
  ]},
  {version:'1.0.0-alpha.8.1',date:'13.08.2026',title:'Standalone macOS и первый Fast Engine',items:[
    'Добавлена standalone .app-сборка без Terminal после установки.',
    'Добавлены Smart Size и Fast Engine для Apple Silicon M1+.'
  ]}
];

export function ReleaseHistory(){
  return <section style={{marginTop:28,borderTop:'1px solid #262c3d',paddingTop:20}}>
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:12,marginBottom:12}}>
      <div><h4 style={{margin:'0 0 5px',fontSize:13,letterSpacing:'.25px'}}>ИСТОРИЯ ОБНОВЛЕНИЙ</h4><p className="settingsNote" style={{margin:0}}>Все сохранённые релизы ENDLUME Studio. Нажмите на версию, чтобы посмотреть изменения.</p></div>
      <span style={{fontSize:10,color:'#8f98b4',border:'1px solid #30374d',borderRadius:999,padding:'6px 9px',whiteSpace:'nowrap'}}>{releases.length} версий</span>
    </div>
    <div style={{display:'grid',gap:8}}>{releases.map((release,index)=><details key={release.version} open={index===0} style={{border:'1px solid #292f42',borderRadius:10,background:'#0d111c',overflow:'hidden'}}>
      <summary style={{cursor:'pointer',listStyle:'none',display:'flex',alignItems:'center',justifyContent:'space-between',gap:12,padding:'12px 14px',userSelect:'none'}}>
        <span style={{display:'flex',alignItems:'center',gap:9,minWidth:0}}><strong style={{fontSize:11,color:'#eef1fa'}}>{release.version}</strong>{release.current&&<em style={{fontStyle:'normal',fontSize:8,color:'#43d5a0',border:'1px solid #285c4b',borderRadius:999,padding:'3px 6px'}}>ТЕКУЩАЯ</em>}<span style={{fontSize:9,color:'#77819e',whiteSpace:'nowrap'}}>{release.date}</span></span>
        <span style={{fontSize:10,color:'#8b85ff'}}>ПОКАЗАТЬ ▾</span>
      </summary>
      <div style={{padding:'0 14px 13px',borderTop:'1px solid #202638'}}><b style={{display:'block',fontSize:11,marginTop:12,color:'#dfe4f2'}}>{release.title}</b><ul style={{margin:'9px 0 0',paddingLeft:19,color:'#818ba8',fontSize:10,lineHeight:1.55}}>{release.items.map(item=><li key={item} style={{margin:'5px 0'}}>{item}</li>)}</ul></div>
    </details>)}</div>
  </section>
}
