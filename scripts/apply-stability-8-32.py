from pathlib import Path
import re

VERSION='1.0.0-alpha.8.32'

def require(cond,msg):
    if not cond: raise SystemExit(msg)

# Remove experimental Noise 1/2 after the 8.31 compatibility patch has run.
types=Path('src/types.ts'); t=types.read_text(encoding='utf-8')
t=t.replace('  noise1?: boolean;\n','').replace('  noise2?: boolean;\n',''); types.write_text(t,encoding='utf-8')
store=Path('src/store.ts'); s=store.read_text(encoding='utf-8').replace(',noise1:false,noise2:false',''); store.write_text(s,encoding='utf-8')
model=Path('src-tauri/src/model.rs'); m=model.read_text(encoding='utf-8')
m=re.sub(r'\n\s*#\[serde\(default\)\]\s*pub noise1:bool,','',m); m=re.sub(r'\n\s*#\[serde\(default\)\]\s*pub noise2:bool,','',m); model.write_text(m,encoding='utf-8')
project=Path('src/pages/ProjectPage.tsx'); p=project.read_text(encoding='utf-8')
p=re.sub(r'\n\s*<section className="sectionBlock">\s*<div className="sectionTitle">ВСТРОЕННЫЕ ЭФФЕКТЫ</div>.*?</section>\n','\n',p,count=1,flags=re.S); project.write_text(p,encoding='utf-8')

render=Path('src-tauri/src/render.rs'); r=render.read_text(encoding='utf-8')
clean_base='fn base_filter(s:&RenderSettings,label:&str)->String{format!("[{label}]scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2,fps={},setsar=1",s.width,s.height,s.width,s.height,s.fps)}'
r,n=re.subn(r'fn base_filter\(s:&RenderSettings,label:&str\)->String\{.*?\n\}',clean_base,r,count=1,flags=re.S)
if n==0:r=re.sub(r'fn base_filter\(s:&RenderSettings,label:&str\)->String\{format!\([^\n]+\)\}',clean_base,r,count=1)
require('s.noise1' not in r and 's.noise2' not in r,'8.32: noise render path survived')

# Strict ENDLUME fast path: static 4K image + music + small overlays.
# Only the short 30-second master is encoded; the two-hour visual timeline is stream-copy.
hybrid='''fn hybrid_fidelity_args(s:&RenderSettings,encoder:&str)->Vec<String>{
  let g=(s.fps.max(1)*10).to_string();
  if encoder=="hevc_videotoolbox"{
    vec!["-c:v","hevc_videotoolbox","-realtime","1","-b:v","740k","-maxrate","1100k","-bufsize","2200k","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }else{
    let x265=format!("keyint={}:min-keyint={}:scenecut=0:open-gop=0",g,g);
    vec!["-c:v","libx265","-preset","ultrafast","-crf","16","-x265-params",&x265,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }
}'''
r,n=re.subn(r'fn hybrid_fidelity_args\(s:&RenderSettings\)->Vec<String>\{.*?\n\}',hybrid,r,count=1,flags=re.S)
if n==0 and 'fn hybrid_fidelity_args(s:&RenderSettings,encoder:&str)' not in r:raise SystemExit('8.32: hybrid fidelity marker missing')
r=r.replace('hybrid_fidelity_args(&job.settings)','hybrid_fidelity_args(&job.settings,encoder)')
r=r.replace('let encoder=if smart_repeat{"libx265".to_string()}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};','let encoder=if smart_repeat{if attempt==1{"hevc_videotoolbox".to_string()}else{"libx265".to_string()}}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};')
require('hybrid_fidelity_args(&job.settings,encoder)' in r,'8.32: hybrid calls not migrated')
require('"hevc_videotoolbox".to_string()' in r,'8.32: VideoToolbox fast path missing')
render.write_text(r,encoding='utf-8')

# Updater copy: after 8.32 no visible Terminal for normal updates.
settings=Path('src/pages/SettingsPage.tsx'); ss=settings.read_text(encoding='utf-8')
ss=ss.replace('Для текущего локального режима рекомендуем обновлять ENDLUME через локальный builder на Mac. Online updater можно оставить как резервный канал.','Обновления устанавливаются прямо внутри ENDLUME в фоне. Terminal больше не открывается.')
ss=ss.replace('Online updater можно оставить как резервный канал.','Terminal не требуется: ENDLUME сама проверяет и устанавливает обновление в фоне.')
settings.write_text(ss,encoding='utf-8')

# Version sync.
for name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/RenderPage.tsx','src/pages/ProjectPage.tsx']:
    f=Path(name); x=f.read_text(encoding='utf-8'); x=re.sub(r'1\.0\.0-alpha\.8\.\d+',VERSION,x); f.write_text(x,encoding='utf-8')

history=Path('src/components/ReleaseHistory.tsx'); h=history.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.32',date:'27.08.2026',current:true,title:'Stability Core: Live Preview, очередь, скорость, updater и фирменная иконка',items:[
    'Исправлен macOS AppleDouble-баг: ._*.png больше не принимаются за исходную картинку. Effects/Subscribe Live Preview больше не падают с Invalid PNG signature 0x00051607.',
    'Шум 1 и Шум 2 полностью удалены из интерфейса и рендера.',
    'Render Center синхронизируется с backend-очередью: второй и следующие проекты видны сразу и восстанавливаются после перезапуска UI.',
    'Статичный 4K short-master сначала кодируется аппаратно HEVC VideoToolbox около 740 кбит/с; двухчасовая визуальная дорожка повторяется stream-copy. libx265 остаётся quality fallback.',
    'Crossfade OFF сохраняет совместимые MP3 bitstream-copy; Crossfade ON остаётся lossless ALAC после сведения.',
    'Последующие обновления ставятся внутри ENDLUME без Terminal: скрытая сборка, gates, atomic swap и rollback.',
    'Возвращена фирменная иконка ENDLUME без чёрной квадратной рамки.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.32'" not in h:
    require(marker in h,'8.32: history marker missing'); h=h.replace(marker,marker+entry,1)
history.write_text(h,encoding='utf-8')

# Hard gates that must survive all legacy compatibility patches.
require('ВСТРОЕННЫЕ ЭФФЕКТЫ' not in project.read_text(encoding='utf-8'),'8.32: Noise UI survived')
require('noise1' not in types.read_text(encoding='utf-8') and 'noise2' not in types.read_text(encoding='utf-8'),'8.32: Noise TS survived')
require('live-preview-v5' in Path('src-tauri/src/live_preview.rs').read_text(encoding='utf-8'),'8.32: Live Preview v5 missing')
require('hidden_sidecar(&p)' in Path('src-tauri/src/scan.rs').read_text(encoding='utf-8'),'8.32: AppleDouble scanner guard missing')
require("'queue-changed'" in Path('src/pages/App.tsx').read_text(encoding='utf-8'),'8.32: queue sync listener missing')
require('local_update::local_update_check' in Path('src-tauri/src/lib.rs').read_text(encoding='utf-8'),'8.32: in-app updater missing')
print('ENDLUME alpha.8.32 stability/speed/updater patch applied')
