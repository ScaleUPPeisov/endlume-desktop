#!/usr/bin/env python3
from pathlib import Path
import json,re,shutil

ROOT=Path(__file__).resolve().parent.parent
PAYLOAD=ROOT/'scripts/vyron-bridge-8-40'

def need(path:Path):
    if not path.exists(): raise SystemExit(f'8.40 VYRON bridge: missing {path}')
    return path

def write_payload(name:str,dst:str):
    src=need(PAYLOAD/name); out=ROOT/dst; out.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(src,out)

# This patch is intentionally post-migration. Raw release source stays untouched so 8.25→8.39 migrations remain deterministic.
write_payload('vyron_bridge.rs','src-tauri/src/vyron_bridge.rs')
write_payload('vyron_bridge_tests.rs','src-tauri/src/vyron_bridge_tests.rs')
write_payload('VyronBatchBridge.tsx','src/components/VyronBatchBridge.tsx')

# Native module + commands.
p=need(ROOT/'src-tauri/src/lib.rs'); s=p.read_text(encoding='utf-8')
if 'mod vyron_bridge;' not in s:
    anchor='mod system;'
    if anchor not in s: raise SystemExit('8.40 VYRON bridge: lib.rs module anchor missing')
    s=s.replace(anchor,anchor+'\nmod vyron_bridge;\n#[cfg(test)]\nmod vyron_bridge_tests;',1)
if 'vyron_bridge::consume_vyron_batch_request' not in s:
    start=s.find('system::power_status')
    if start<0: raise SystemExit('8.40 VYRON bridge: lib.rs handler system anchor missing')
    end=s.find('\n    ])',start)
    if end<0: raise SystemExit('8.40 VYRON bridge: lib.rs handler close missing')
    before=s[:end]
    if not before.rstrip().endswith(','): before=before.rstrip()+','
    commands='\n      vyron_bridge::consume_vyron_batch_request,vyron_bridge::load_vyron_batch_manifest,vyron_bridge::report_vyron_render'
    s=before+commands+s[end:]
p.write_text(s,encoding='utf-8')

# Frontend native API surface.
p=need(ROOT/'src/tauri.ts'); s=p.read_text(encoding='utf-8')
if 'export type VyronBatchRequest=' not in s:
    anchor="export type LivePreviewAssetPaths={basePath:string;baseKind:'image'|'video';overlayPath:string};"
    if anchor not in s: raise SystemExit('8.40 VYRON bridge: tauri type anchor missing')
    types="\nexport type VyronBatchRequest={batchId:string;manifestPath:string;requestedAt?:string|null};\nexport type VyronBatchInfo={batchId:string;channelId:string;channelName:string;projectCount:number;tracksAssigned:number;rootPath:string;outputDir:string;statusPath:string;manifestPath:string;projectPaths:string[]};"
    s=s.replace(anchor,anchor+types,1)
if 'consumeVyronBatch:' not in s:
    anchor='  showError:(text:string)=>'
    if anchor not in s: raise SystemExit('8.40 VYRON bridge: tauri API insertion anchor missing')
    api="  consumeVyronBatch:()=>invoke<VyronBatchRequest|null>('consume_vyron_batch_request'),\n  loadVyronBatch:(manifestPath:string)=>invoke<VyronBatchInfo>('load_vyron_batch_manifest',{manifestPath}),\n  reportVyronRender:(manifestPath:string,projectPath:string,renderStatus:string,outputFile?:string|null,duration?:number|null,fileSize?:number|null,error?:string|null)=>invoke<void>('report_vyron_render',{manifestPath,projectPath,renderStatus,outputFile:outputFile??null,duration:duration??null,fileSize:fileSize??null,error:error??null}),\n"
    s=s.replace(anchor,api+anchor,1)
p.write_text(s,encoding='utf-8')

# Mount invisible local bridge without redesigning the shell.
p=need(ROOT/'src/pages/App.tsx'); s=p.read_text(encoding='utf-8')
if "../components/VyronBatchBridge" not in s:
    anchor="import { RecoveryModal } from '../components/recovery';"
    if anchor not in s: raise SystemExit('8.40 VYRON bridge: App import anchor missing')
    s=s.replace(anchor,anchor+"\nimport { VyronBatchBridge } from '../components/VyronBatchBridge';",1)
if '<VyronBatchBridge/>' not in s:
    anchor='<div className="appShell">'
    if anchor not in s: raise SystemExit('8.40 VYRON bridge: App shell anchor missing')
    s=s.replace(anchor,anchor+'<VyronBatchBridge/>',1)
p.write_text(s,encoding='utf-8')

# Version 8.40 after the proven 8.39 stack.
version='1.0.0-alpha.8.40'
for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=need(ROOT/file_name); text=p.read_text(encoding='utf-8'); text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text); p.write_text(text,encoding='utf-8')

# Release history entry, leaving all previous history intact.
p=need(ROOT/'src/components/ReleaseHistory.tsx'); h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.40',date:'02.09.2026',current:true,title:'VYRON Batch Bridge',items:[
    'Добавлен локальный приём batch.json из VYRON Production Manager без YouTube API и без изменения ручного режима ENDLUME.',
    'Партия VYRON автоматически подставляет проекты и output-папку; Effects/Subscribe по-прежнему выбираются один раз штатным интерфейсом ENDLUME.',
    'Статусы Rendering / Completed / Error и готовый файл возвращаются в локальный status.json VYRON.',
    'Сохранён проверенный 8.39 render pipeline: 60 FPS, YouTube Fill, crossfade/audio, chroma/despill, быстрый mux и текущий дизайн.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.40'" not in h:
    if marker not in h: raise SystemExit('8.40 VYRON bridge: release history anchor missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')

# Strict local-only + wiring guards.
for f in ['src/components/VyronBatchBridge.tsx','src-tauri/src/vyron_bridge.rs']:
    text=(ROOT/f).read_text(encoding='utf-8').lower()
    forbidden=['youtube','googleapis','openai','claude','gemini']
    hit=[x for x in forbidden if x in text]
    if hit: raise SystemExit(f'8.40 VYRON bridge external API violation {f}: {hit}')
checks={
 'src-tauri/src/lib.rs':['mod vyron_bridge;','mod vyron_bridge_tests;','vyron_bridge::consume_vyron_batch_request','vyron_bridge::load_vyron_batch_manifest','vyron_bridge::report_vyron_render'],
 'src/tauri.ts':['consumeVyronBatch:','loadVyronBatch:','reportVyronRender:'],
 'src/pages/App.tsx':['VyronBatchBridge','<VyronBatchBridge/>'],
}
for f,markers in checks.items():
    text=(ROOT/f).read_text(encoding='utf-8')
    missing=[m for m in markers if m not in text]
    if missing: raise SystemExit(f'8.40 VYRON bridge wiring failed {f}: {missing}')

print('ENDLUME alpha.8.40 VYRON post-migration bridge applied: PASS')
