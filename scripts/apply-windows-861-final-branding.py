#!/usr/bin/env python3
from pathlib import Path
p=Path('src/pages/SettingsPage.tsx')
s=p.read_text(encoding='utf-8')
if "../platform-brand" not in s:
    s=s.replace("import { ReleaseHistory } from '../components/ReleaseHistory';", "import { ReleaseHistory } from '../components/ReleaseHistory';\nimport { IS_WINDOWS, PRODUCT_KICKER, PRODUCT_NAME } from '../platform-brand';")
s=s.replace('<small>ENDLUME STUDIO</small><h1>Настройки</h1>', '<small>{PRODUCT_KICKER}</small><h1>Настройки</h1>')
s=s.replace('каждый движком и выбирает только тот кодировщик, который действительно отработал на этом Mac.', 'каждый движком и выбирает только тот кодировщик, который действительно отработал на этой системе.')
s=s.replace('<p>ENDLUME Studio 1.0.0-alpha.8.61</p>', '<p>{PRODUCT_NAME} 1.0.0-alpha.8.61</p>')
s=s.replace('<p className="settingsNote">Скачивается готовая сборка. Локальная компиляция на Mac больше не используется.</p>', '<p className="settingsNote">Скачивается готовая подписанная сборка. Локальная компиляция пользователю не требуется.</p>')
s=s.replace('<h2>ENDLUME Studio</h2><p>Long Video Engine</p>', '<h2>{PRODUCT_NAME}</h2><p>Long Video Engine</p>')
s=s.replace('<span>Windows <b>10 / 11</b></span><span>macOS <b>Apple Silicon M1+</b></span>', '<span>Windows <b>10 / 11 x64</b></span>{!IS_WINDOWS&&<span>macOS <b>Apple Silicon M1+</b></span>}')
p.write_text(s,encoding='utf-8')
print('ENDLUME_WINDOWS_FINAL_BRANDING_APPLIED')
