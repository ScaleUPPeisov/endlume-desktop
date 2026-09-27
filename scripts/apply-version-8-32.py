from pathlib import Path
import re

version='1.0.0-alpha.8.32'

for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

for file_name in ['src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.32',date:'26.08.2026',current:true,title:'Queue Sync + обновления полностью внутри ENDLUME',items:[
    'Исправлена потеря второго и следующих проектов в окне Рендер: UI теперь синхронизируется с реальной backend-очередью через queue-changed и queue_snapshot.',
    'Каждое добавление в очередь получает уникальный job ID, поэтому одну и ту же папку можно отправить повторно, не скрывая новый рендер.',
    'Список рендеров сохраняется между переходами по вкладкам и перезапуском приложения; готовые проекты не исчезают при добавлении новой задачи.',
    'Добавлен приватный In-App Update Center: проверка, сборка, тесты и установка запускаются из ENDLUME без Terminal и без GitHub Actions.',
    'Обновление использует уже авторизованный GitHub CLI только как безопасный доступ к приватному release-каналу; исходное приложение не заменяется до прохождения всех gates.',
    'Во время обновления в приложении отображаются текущий этап и процент; в момент atomic swap ENDLUME перезапускается автоматически.',
    'Сохранены 8.31: живые этапы рендера, реальный lossless-crossfade, Noise 1/2, Effects/Subscribe и Hybrid Fidelity.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.32'" not in h:
    if marker not in h:raise SystemExit('8.32: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')

print('ENDLUME alpha.8.32 version synced')
