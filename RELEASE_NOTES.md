# ENDLUME Studio 1.0.0-alpha.8.16 — 23.08.2026 · macOS Apple Silicon

- Исправлена критическая ошибка экрана «Проект», при которой нижняя панель «Добавить в очередь» после прокрутки оказывалась внутри страницы и перекрывала параметры рендера, Subscribe и Effects.
- Причина найдена точно: route-анимация `.pageScene` использовала `transform`. В macOS WKWebView transformed ancestor меняет containing block для `position: fixed`, поэтому `.projectBottom` переставал быть привязан к окну и начинал двигаться вместе с прокручиваемой страницей.
- Переходы между Проект / Рендер / Библиотека / Настройки теперь для корневой страницы выполняются только через лёгкую opacity-анимацию. На корневом route-wrapper принудительно запрещены `transform`, `filter`, `perspective` и `contain`, чтобы fixed-панель больше не могла сломаться.
- Нижняя панель проекта дополнительно закреплена к viewport через `position: fixed`, `bottom: 0` и отдельный z-index; под неё всегда резервируется 105 px пространства, поэтому контент не уходит под панель.
- Нативная прокрутка macOS и скрытый правый scrollbar из alpha.8.15 сохранены. JS wheel/scroll listeners и per-frame FPS governor не возвращались.
- Добавлены 16 обязательных motion/layout release-проверок. Сборка блокируется, если route-wrapper снова получит transform, fixed footer потеряет viewport-позиционирование, исчезнет нижний отступ, вернутся scroll listeners, scrollbar rail или тяжёлые transition-параметры.
- Сохраняются все предыдущие исправления: GPU Live Preview Effects/Subscribe, быстрый drag/resize без FFmpeg, Crossfade CFR fix и 100 реальных Loop Mode smoke-прогонов.
