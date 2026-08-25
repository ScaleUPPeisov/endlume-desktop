from pathlib import Path

# React 19 requires an initial value for these mutable refs.
editors = Path('src/pages/Editors.tsx')
text = editors.read_text(encoding='utf-8')
text = text.replace('const pointerRef = useRef<globalThis.PointerEvent>();', 'const pointerRef = useRef<globalThis.PointerEvent | undefined>(undefined);')
text = text.replace('const rafRef = useRef<number>();', 'const rafRef = useRef<number | undefined>(undefined);')
if 'useRef<globalThis.PointerEvent>();' in text or 'useRef<number>();' in text:
    raise SystemExit('8.25 UI patch: unsafe React 19 useRef remains')
editors.write_text(text, encoding='utf-8')

# Local release number must be consistent in Settings and updater fallback.
for file_name in ['src/tauri.ts', 'src/pages/SettingsPage.tsx']:
    path = Path(file_name)
    value = path.read_text(encoding='utf-8')
    for old in ['1.0.0-alpha.8.19','1.0.0-alpha.8.20','1.0.0-alpha.8.21','1.0.0-alpha.8.22','1.0.0-alpha.8.23','1.0.0-alpha.8.24']:
        value = value.replace(old, '1.0.0-alpha.8.25')
    if file_name.endswith('SettingsPage.tsx'):
        value = value.replace('24.08.2026', '25.08.2026')
    path.write_text(value, encoding='utf-8')

history_path = Path('src/components/ReleaseHistory.tsx')
if history_path.exists():
    history = history_path.read_text(encoding='utf-8').replace('current:true,', '')
    if "version:'1.0.0-alpha.8.25'" not in history:
        marker = 'const releases:Release[]=[\n'
        entry = """  {version:'1.0.0-alpha.8.25',date:'25.08.2026',current:true,title:'Render Recovery + Effects/Subscribe Stability',items:[
    'Сборка больше не переписывает исходники Python-hotfix скриптами при каждом npm/Tauri build: TypeScript собирается из стабильного исходного кода.',
    'Рендер использует writable app-cache workspace и автоматически переключает недоступную папку результата на Movies/ENDLUME Studio.',
    'Первая попытка использует аппаратный кодировщик, вторая принудительно libx264/libx265 вместо повторения того же сломанного encoder.',
    'Сломанный или потерянный Effect/Subscribe пропускается с предупреждением и больше не валит весь проект.',
    'Effects и Subscribe используют одинаковую с Preview центрированную X/Y/SIZE геометрию и сохраняют исходное соотношение сторон.',
    'Subscribe импортируется в собственную managed-библиотеку, новые Effects/Subscribe автоматически ставятся по центру.',
    'MP3 до acrossfade нормализуются в 48 kHz stereo/fltp; stale пути проекта восстанавливаются повторным сканированием папки.',
    'Перед локальной установкой обязательны TypeScript, frontend, Rust, 100 Loop Mode тестов, Effects/Subscribe aspect test и финальный video+audio mux test.'
  ]},
"""
        if marker not in history:
            raise SystemExit('8.25 UI patch: release history marker missing')
        history = history.replace(marker, marker + entry, 1)
    history_path.write_text(history, encoding='utf-8')

print('ENDLUME alpha.8.25 UI/version patch applied')
