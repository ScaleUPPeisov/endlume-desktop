from pathlib import Path

version = '1.0.0-alpha.8.26'
date = '25.08.2026'

settings = Path('src/pages/SettingsPage.tsx')
text = settings.read_text(encoding='utf-8')
# SettingsPage still contains old hard-coded alpha labels from earlier releases.
import re
text = re.sub(r'ENDLUME Studio 1\.0\.0-alpha\.8\.\d+', f'ENDLUME Studio {version}', text)
text = re.sub(r"update\.current\|\|'1\.0\.0-alpha\.8\.\d+'", f"update.current||'{version}'", text)
text = re.sub(r'<b>1\.0\.0-alpha\.8\.\d+</b>', f'<b>{version}</b>', text)
text = re.sub(r'<b>\d{2}\.\d{2}\.2026</b>', f'<b>{date}</b>', text, count=1)
text = text.replace('Для текущего локального режима рекомендуем обновлять ENDLUME через локальный builder на Mac. Online updater можно оставить как резервный канал.', 'Smart Repeat автоматически ускоряет проекты «1 изображение + музыка + Effects/Subscribe». Локальный builder проверяет этот режим перед установкой.')
settings.write_text(text, encoding='utf-8')

history = Path('src/components/ReleaseHistory.tsx')
h = history.read_text(encoding='utf-8')
h = h.replace("current:true,", "current:false,", 1)
entry = """  {version:'1.0.0-alpha.8.26',date:'25.08.2026',current:true,title:'Smart Repeat: 2 часа около 700–1000 МБ и быстрый финальный mux',items:[
    'Smart Size теперь работает не только для чистой картинки, но и для проекта «1 изображение + Effects + Subscribe».',
    'Для 2 часов целевой бюджет видео: 520 кбит/с для 1080p, 600 кбит/с для 1440p и 700 кбит/с для 4K; вместе с AAC 320 кбит/с это примерно 700–1000 МБ.',
    'Постоянные Effects больше не переводят весь двухчасовой ролик на пользовательские 20–30 Мбит/с.',
    'Вариант Effects собирается напрямую из исходного изображения, чтобы не делать лишнее повторное сжатие фоновой картинки.',
    'ENDLUME учитывает длительность исходного Effect-loop до 60 секунд, чтобы длинная анимация не перезапускалась каждые 8–12 секунд.',
    'Финальный mux остаётся stream-copy: уменьшение визуального потока с десятков гигабайт до ~1 ГБ резко сокращает время последнего этапа.',
    'Для обычных видео-проектов Smart Repeat не включается: их пользовательский профиль качества остаётся без изменений.'
  ]},
"""
marker = 'const releases:Release[]=[\n'
if entry not in h:
    if marker not in h:
        raise SystemExit('8.26 UI: ReleaseHistory marker not found')
    h = h.replace(marker, marker + entry, 1)
history.write_text(h, encoding='utf-8')

print('ENDLUME alpha.8.26 UI/version history applied')
