#!/usr/bin/env python3
from pathlib import Path
import json,re

ROOT=Path(__file__).resolve().parents[1]

# 8.58 is intentionally UI/queue-state only. Do not touch render.rs, Effects,
# Subscribe, VYRON, audio, codec, GOP, bitrate, sample-table or updater logic.
Q=ROOT/'src/queue-state.ts'
S=ROOT/'src/store.ts'
A=ROOT/'src/pages/App.tsx'
for p in (Q,S,A):
    if not p.is_file(): raise SystemExit(f'8.58: missing {p.relative_to(ROOT)}')
q=Q.read_text();s=S.read_text();a=A.read_text()
required={
  'queue terminal guard':"status==='done'||status==='error'",
  'terminal patch helper':'export function applyProjectPatch',
  'queue snapshot helper':'export function applyQueueSnapshot',
  'store uses guarded patch':'applyProjectPatch(s.projects,id,patch)',
  'App removes pending done progress':'progressPending.delete(p.id)',
  'App normalizes done to 100':"status:'done',progress:100,stage:'Готово',etaSec:0",
  'App guarded RAF flush':'projects=applyProjectPatch(projects,next.id,compactPayload(next))',
}
combined='\n'.join((q,s,a))
for label,needle in required.items():
    if needle not in combined: raise SystemExit(f'8.58: missing guard: {label}')

# Version manifests after the 8.57 migration has produced the effective source.
for rel in ['package.json','src-tauri/tauri.conf.json']:
    p=ROOT/rel; d=json.loads(p.read_text()); d['version']='1.0.0-alpha.8.58'; p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

p=ROOT/'src-tauri/Cargo.toml'; txt=p.read_text()
txt,n=re.subn(r'(?m)^version\s*=\s*"1\.0\.0-alpha\.8\.57"$', 'version = "1.0.0-alpha.8.58"',txt,count=1)
if n!=1: raise SystemExit('8.58: Cargo 8.57 version anchor missing')
p.write_text(txt)

p=ROOT/'package-lock.json'
if p.exists():
    d=json.loads(p.read_text()); d['version']='1.0.0-alpha.8.58'
    if isinstance(d.get('packages'),dict) and '' in d['packages']: d['packages']['']['version']='1.0.0-alpha.8.58'
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

P=ROOT/'src/pages/SettingsPage.tsx'; ui=P.read_text()
if '1.0.0-alpha.8.57' not in ui: raise SystemExit('8.58: Settings 8.57 anchor missing')
ui=ui.replace('1.0.0-alpha.8.57','1.0.0-alpha.8.58')
P.write_text(ui)

H=ROOT/'src/components/ReleaseHistory.tsx'; h=H.read_text()
old="version:'1.0.0-alpha.8.57',date:'06.09.2026',current:true"
if old not in h: raise SystemExit('8.58: ReleaseHistory 8.57 current anchor missing')
h=h.replace(old,"version:'1.0.0-alpha.8.57',date:'06.09.2026',current:false",1)
anchor='const releases:Release[]=[\n'
entry="""const releases:Release[]=[
  {version:'1.0.0-alpha.8.58',date:'06.09.2026',current:true,title:'Queue Finalization • 100% Result Lock',items:[
    'Исправлена гонка Render Center: отложенный requestAnimationFrame progress=97 больше не может перезаписать уже полученный render-done=100.',
    'Статусы done/error стали монотонными: поздние render-progress и queue-changed не возвращают завершённый проект в rendering/queued.',
    'Перед фиксацией done удаляется ожидающий progress-event этого job ID, а resultPath/resultBytes сохраняются для кнопок открытия результата.',
    'Добавлен regression gate на очередь 40/40 проектов с намеренно неправильным порядком событий 97% → done → поздний 97%.',
    'Render Core 8.57 не менялся: HEVC VideoToolbox q:v 100, GOP 1800, 1920×1080/60, untouched MP3, Effects/Subscribe и 500–700 МБ сохранены.'
  ]},
"""
if anchor not in h: raise SystemExit('8.58: ReleaseHistory list anchor missing')
h=h.replace(anchor,entry,1)
H.write_text(h)

print('PASS: ENDLUME 8.58 queue finalization hotfix metadata applied; render core untouched')
