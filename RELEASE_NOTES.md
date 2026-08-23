# ENDLUME Studio 1.0.0-alpha.8.14 — 23.08.2026 · macOS Apple Silicon

- Добавлен отдельный ENDLUME Motion Layer для плавного интерфейса без вмешательства в render/editor-логику.
- Переходы между Проектом, Рендером, Библиотекой и Настройками теперь выполняются через compositor-friendly opacity + transform вместо резких переключений.
- Прокрутка вниз/вверх остаётся нативной для macOS WebView: smooth scroll, overscroll containment, scrollbar-gutter и тонкий cyan/violet/pink scrollbar. JavaScript не перехватывает wheel и не вызывает preventDefault.
- Все функциональные кнопки получили единый короткий press/hover motion; Настройки, Editor и раскрытие истории обновлений больше не появляются жёстким скачком.
- Во время активной прокрутки ENDLUME автоматически приостанавливает декоративные блики и упрощает тяжёлые тени, чтобы отдавать GPU/CPU самой прокрутке.
- Добавлен адаптивный requestAnimationFrame FPS governor: при устойчивой просадке ниже примерно 48 FPS отключается только тяжёлая декоративная анимация; функциональность, preview и рендер не меняются. После восстановления частоты кадров декорация возвращается.
- Большие независимые UI-блоки получили paint/layout containment, а секции проекта используют content-visibility для снижения лишней отрисовки вне экрана.
- Добавлена отдельная release-проверка motion-архитектуры: passive native scroll, compositor transforms, adaptive fallback, reduced-motion и запрет transition: all в Motion Layer.
- Сохранены все исправления alpha.8.13: GPU Live Preview Effects/Subscribe, быстрый drag без FFmpeg, исправленный Crossfade CFR и 100-прогонная проверка Loop Mode.
