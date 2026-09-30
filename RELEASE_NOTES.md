# ENDLUME YT Studio PEISOV 10.0.2 — 30.09.2026 · macOS Apple Silicon

- P0 Apple Audio: финальный MP4 теперь содержит AAC-LC 320 кбит/с / 48 кГц / stereo с default audio track и проверкой совместимости структуры.
- Исправлен режим короткого видео Ping-Pong: физический цикл остаётся коротким, а длинный финальный таймлайн создаётся zero-copy через sample-table.
- Добавлен persistent AAC cache для Ping-Pong; аудио строится параллельно visual cache и повторно используется на следующих рендерах.
- Финальный Ping-Pong mux выполняет packet-copy видео и готового AAC без повторного двухчасового encode.
- Сохранены HEVC 1080p60, качество картинки, Effects, Subscribe, полные песни, target-size и встроенный updater.
