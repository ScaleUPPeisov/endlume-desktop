# ENDLUME Studio 1.0.0-alpha.8.7 — 14.08.2026 · Windows x64

- Убрано отдельное окно командной строки: release-сборка запускается как одно приложение ENDLUME Studio.
- Новая Windows-иконка ENDLUME генерируется из чистого цветного interlocking-loop без старой рамки.
- Render Center показывает реальный диск папки вывода: использовано / свободно / всего.
- Добавлен Original Fast Path для «1 изображение + музыка» без активных Effects/Subscribe/ambient/LUFS.
- Совместимые исходные аудиотреки (одинаковый codec/sample rate/channels) идут в итоговый MP4 через bitstream copy: без повторного AAC-кодирования и без длинного промежуточного аудио-кэша.
- Статичное изображение один раз превращается в короткий HQ master (Lanczos, CRF 12/14), затем длинный ролик собирается video stream-copy.
- Если безопасный original-audio stream-copy невозможен, ENDLUME автоматически возвращается к обычному проверенному render engine.
- Перенесены исправления macOS alpha.8.6: быстрый Live Preview, React 19 drag/resize, включение/выключение и удаление Effects/Subscribe, ускоренный lossless overlay-cache.
- Windows NSIS собирается с Tauri updater-подписью; обновление устанавливается из «Настройки → Обновления → Проверить и обновить» с автоматическим перезапуском.
