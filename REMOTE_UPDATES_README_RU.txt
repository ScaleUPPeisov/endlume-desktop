ENDLUME Remote Updates — bootstrap alpha.8.4

1. Один раз запустить ENABLE_REMOTE_UPDATES_M1.command.
2. Скрипт создаёт постоянную пару ключей Tauri Updater в:
   ~/Library/Application Support/ENDLUME Studio/updater-keys/
3. PRIVATE KEY endlume-updater.key НИКОМУ НЕ ПЕРЕДАВАТЬ и не удалять.
4. ENDLUME проверяет канал https://endlume-updates.vercel.app при запуске и вручную в Настройках.
5. После alpha.8.4 обычные пользователи обновляются внутри приложения без Terminal.
6. Новые updater-пакеты должны ВСЕГДА подписываться тем же приватным ключом.
