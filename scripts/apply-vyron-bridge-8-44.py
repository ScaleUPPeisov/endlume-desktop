#!/usr/bin/env python3
from pathlib import Path
import re,shutil

ROOT=Path(__file__).resolve().parent.parent
PAYLOAD=ROOT/'scripts/vyron-bridge-8-40'


def need(path:Path):
    if not path.exists():
        raise SystemExit(f'8.44 VYRON bridge: missing {path}')
    return path


def write_payload(name:str,dst:str):
    src=need(PAYLOAD/name)
    out=ROOT/dst
    out.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,out)

# 8.44 is intentionally a post-8.43 integration-only patch. It must not alter
# the proven 8.43 render/FPS/audio/updater pipeline.
write_payload('vyron_bridge.rs','src-tauri/src/vyron_bridge.rs')
write_payload('vyron_bridge_tests.rs','src-tauri/src/vyron_bridge_tests.rs')
write_payload('VyronBatchBridge.tsx','src/components/VyronBatchBridge.tsx')

# Native module + commands.
p=need(ROOT/'src-tauri/src/lib.rs')
s=p.read_text(encoding='utf-8')
if 'mod vyron_bridge;' not in s:
    anchor='mod system;'
    if anchor not in s:
        raise SystemExit('8.44 VYRON bridge: lib.rs module anchor missing')
    s=s.replace(anchor,anchor+'\nmod vyron_bridge;\n#[cfg(test)]\nmod vyron_bridge_tests;',1)
if 'vyron_bridge::consume_vyron_batch_request' not in s:
    start=s.find('system::power_status')
    if start<0:
        raise SystemExit('8.44 VYRON bridge: lib.rs handler system anchor missing')
    end=s.find('\n    ])',start)
    if end<0:
        raise SystemExit('8.44 VYRON bridge: lib.rs handler close missing')
    before=s[:end]
    if not before.rstrip().endswith(','):
        before=before.rstrip()+','
    commands='\n      vyron_bridge::consume_vyron_batch_request,vyron_bridge::load_vyron_batch_manifest,vyron_bridge::report_vyron_render'
    s=before+commands+s[end:]
p.write_text(s,encoding='utf-8')

# Frontend native API surface.
p=need(ROOT/'src/tauri.ts')
s=p.read_text(encoding='utf-8')
if 'export type VyronBatchRequest=' not in s:
    anchor="export type LivePreviewAssetPaths={basePath:string;baseKind:'image'|'video';overlayPath:string};"
    if anchor not in s:
        raise SystemExit('8.44 VYRON bridge: tauri type anchor missing')
    types="\nexport type VyronBatchRequest={batchId:string;manifestPath:string;requestedAt?:string|null};\nexport type VyronBatchInfo={batchId:string;channelId:string;channelName:string;projectCount:number;tracksAssigned:number;rootPath:string;outputDir:string;statusPath:string;manifestPath:string;projectPaths:string[]};"
    s=s.replace(anchor,anchor+types,1)
if 'consumeVyronBatch:' not in s:
    anchor='  showError:(text:string)=>'
    if anchor not in s:
        raise SystemExit('8.44 VYRON bridge: tauri API insertion anchor missing')
    api="  consumeVyronBatch:()=>invoke<VyronBatchRequest|null>('consume_vyron_batch_request'),\n  loadVyronBatch:(manifestPath:string)=>invoke<VyronBatchInfo>('load_vyron_batch_manifest',{manifestPath}),\n  reportVyronRender:(manifestPath:string,projectPath:string,renderStatus:string,outputFile?:string|null,duration?:number|null,fileSize?:number|null,error?:string|null)=>invoke<void>('report_vyron_render',{manifestPath,projectPath,renderStatus,outputFile:outputFile??null,duration:duration??null,fileSize:fileSize??null,error:error??null}),\n"
    s=s.replace(anchor,api+anchor,1)
p.write_text(s,encoding='utf-8')

# Mount the invisible local bridge without changing ENDLUME navigation or design.
p=need(ROOT/'src/pages/App.tsx')
s=p.read_text(encoding='utf-8')
if "../components/VyronBatchBridge" not in s:
    anchor="import { RecoveryModal } from '../components/recovery';"
    if anchor not in s:
        raise SystemExit('8.44 VYRON bridge: App import anchor missing')
    s=s.replace(anchor,anchor+"\nimport { VyronBatchBridge } from '../components/VyronBatchBridge';",1)
if '<VyronBatchBridge/>' not in s:
    anchor='<div className="appShell">'
    if anchor not in s:
        raise SystemExit('8.44 VYRON bridge: App shell anchor missing')
    s=s.replace(anchor,anchor+'<VyronBatchBridge/>',1)
p.write_text(s,encoding='utf-8')

# Final version is above the already-installed 8.43. Never downgrade the user.
version='1.0.0-alpha.8.44'
for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=need(ROOT/file_name)
    text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

# Release history: preserve every prior entry and add only 8.44.
p=need(ROOT/'src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.44',date:'02.09.2026',current:true,title:'VYRON Batch Bridge',items:[
    'Добавлен локальный приём batch.json из VYRON Production Manager без внешних API и без изменения ручного режима ENDLUME.',
    'Партия VYRON автоматически подставляет проекты и output-папку; Effects и Subscribe продолжают работать через штатный интерфейс ENDLUME.',
    'Статусы Rendering / Completed / Error и готовый файл возвращаются в локальный status.json VYRON.',
    'Полностью сохранён проверенный 8.43 pipeline: настоящий CFR 30/60 FPS, YouTube Fill 1920×1080, audio/crossfade, chroma/despill, быстрый stream-copy final и подписанный online updater.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.44'" not in h:
    if marker not in h:
        raise SystemExit('8.44 VYRON bridge: release history anchor missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')

# Strict local-only + wiring guards.
for f in ['src/components/VyronBatchBridge.tsx','src-tauri/src/vyron_bridge.rs']:
    text=(ROOT/f).read_text(encoding='utf-8').lower()
    forbidden=['youtube','googleapis','openai','claude','gemini']
    hit=[x for x in forbidden if x in text]
    if hit:
        raise SystemExit(f'8.44 VYRON bridge external API violation {f}: {hit}')

checks={
 'src-tauri/src/lib.rs':['mod vyron_bridge;','mod vyron_bridge_tests;','vyron_bridge::consume_vyron_batch_request','vyron_bridge::load_vyron_batch_manifest','vyron_bridge::report_vyron_render'],
 'src/tauri.ts':['consumeVyronBatch:','loadVyronBatch:','reportVyronRender:'],
 'src/pages/App.tsx':['VyronBatchBridge','<VyronBatchBridge/>'],
 'src/pages/ProjectPage.tsx':['onClick={enqueue}',"openEditor({kind:'subscribe'})","openEditor({kind:'effects'})"],
}
for f,markers in checks.items():
    text=(ROOT/f).read_text(encoding='utf-8')
    missing=[m for m in markers if m not in text]
    if missing:
        raise SystemExit(f'8.44 VYRON bridge wiring failed {f}: {missing}')

# Explicitly prove that the 8.43 real-FPS contract is still present after 8.44.
r=(ROOT/'src-tauri/src/render.rs').read_text(encoding='utf-8')
for marker in [
    'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};',
    'fn cfr_output_args(',
    '"-fps_mode".into(),"cfr".into()',
    '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"',
    'r_frame_rate,avg_frame_rate,nb_frames,nb_read_packets,duration',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
    'force_original_aspect_ratio=increase',
    'materialize_continuous_audio',
]:
    if marker not in r:
        raise SystemExit('8.44 VYRON bridge: 8.43 render invariant missing: '+marker)

print('ENDLUME alpha.8.44 VYRON post-8.43 bridge applied: PASS')
