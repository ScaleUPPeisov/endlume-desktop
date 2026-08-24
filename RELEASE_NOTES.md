# ENDLUME Studio 1.0.0-alpha.8.19 — 24.08.2026 · macOS Apple Silicon

- Исправлена визуальная разница Effects/Subscribe между исходником, Live Preview и финальным render-cache. Старый YUV chromakey заменён на RGB `colorkey`, поэтому видимые пиксели больше не перекрашиваются и сохраняют исходные цвета.
- GPU Live Preview больше не повышает saturation и не делает принудительный green-despill для Chromakey. Для видимой части overlay сохраняется оригинальный RGB; меняется только alpha выбранного фона.
- Добавлена настоящая «ПИПЕТКА / КИСТЬ» прямо поверх Live Preview. Можно нажать или провести по зелёному/синему фону исходного Effects/Subscribe, и ENDLUME возьмёт реальный цвет пикселя из overlay-видео.
- После выбора пипеткой ENDLUME ставит безопасные стартовые параметры Similarity 0.10 и Blend 0.06. В редакторе добавлен отдельный сброс Chromakey.
- Старые пресеты с очевидно повреждёнными значениями Similarity/Blend около 0.9–1.0 автоматически мигрируют на безопасные параметры. Старый render-cache инвалидируется и пересобирается в новой `effects-v3-fidelity` библиотеке.
- Вторая попытка рендера теперь действительно меняет движок: если hardware encoder не прошёл первый render, повтор выполняется на `libx264` / `libx265`, а не снова на том же неработающем VideoToolbox.
- Финальный stream-copy mux получил генерацию PTS, нормализацию отрицательных timestamp и faststart без повторного кодирования картинки или музыки.
- Ошибка FFmpeg теперь содержит название конкретного этапа рендера. В logs записываются реальные технические детали, а не только общий текст «Не удалось обработать проект».
- Локальный release-gate дополнен Chromakey fidelity smoke-test: создаётся green-screen clip с цветным объектом, RGB colorkey-cache и финальный overlay MP4. Также проверяется наличие software-encoder retry в production Rust pipeline.
- Сохранены исправления alpha.8.18: normal-folder regression, Unicode/французские имена файлов, mixed MP3 32/44.1/48 kHz, stale-path recovery, managed Effects/Subscribe/Ambient, 100 Loop Mode тестов, GPU Live drag/resize, плавный UI и локальная сборка без GitHub Actions.
