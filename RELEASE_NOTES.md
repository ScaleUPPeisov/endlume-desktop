# ENDLUME Studio 1.0.0-alpha.8.15 — 23.08.2026 · macOS Apple Silicon

- Полностью переделан Motion Layer после регрессии alpha.8.14: убраны глобальные scroll/wheel listeners, постоянный FPS governor и переключение CSS-классов во время каждого движения колеса/трекпада.
- Прокрутка снова полностью нативная для macOS WKWebView — без JavaScript на каждом кадре и без вмешательства в wheel/scroll.
- Убраны `content-visibility:auto` и тяжёлое layout/style/paint containment на секциях проекта, которые могли провоцировать повторные layout/paint при быстрой прокрутке.
- Правая полоса прокрутки WKWebView полностью скрыта; зарезервированный scrollbar gutter отключён. Белой полосы справа быть не должно.
- Переходы между Проектом / Рендером / Библиотекой / Настройками сохранены, но сокращены до лёгких compositor-only opacity + translate3d.
- Кнопки оставлены плавными, но из transition исключены filter и box-shadow; постоянная анимация свечения активной вкладки отключена ради стабильной частоты кадров.
- Добавлена release-защита от повторной регрессии: сборка падает, если в Motion Runtime снова появятся wheel/scroll listeners, per-frame governor, `content-visibility:auto`, стабильный scrollbar gutter или тяжёлые transition свойства.
- Все исправления alpha.8.13 сохранены: GPU Live Preview Effects/Subscribe, быстрый drag/resize без FFmpeg, Crossfade CFR fix и 100-прогонная проверка Loop Mode.
- Alpha.8.15 собирается отдельным macOS ARM64 release pipeline перед публикацией через встроенный updater.
