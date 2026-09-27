from pathlib import Path
import json,re

BOOT=Path('updates/github/bootstrap.json')
if not BOOT.is_file(): raise SystemExit('8.42: bootstrap missing')
b=json.loads(BOOT.read_text(encoding='utf-8'))
endpoint=str(b.get('endpoint','')).strip()
pubkey=str(b.get('pubkey','')).strip()
EXPECTED='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/latest.json'
if endpoint!=EXPECTED: raise SystemExit('8.42: updater endpoint mismatch')
if not pubkey: raise SystemExit('8.42: updater pubkey empty')

# Official Tauri updater config only.
p=Path('src-tauri/tauri.conf.json')
cfg=json.loads(p.read_text(encoding='utf-8'))
cfg.setdefault('bundle',{})['createUpdaterArtifacts']=True
up=cfg.setdefault('plugins',{}).setdefault('updater',{})
up['pubkey']=pubkey
up['endpoints']=[endpoint]
if cfg.get('identifier')!='studio.endlume.desktop': raise SystemExit('8.42: bundle identifier changed')
p.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# Canonical frontend updater: check -> signed downloadAndInstall -> relaunch.
p=Path('src/tauri.ts')
s=p.read_text(encoding='utf-8')
imports=[
 ("import { invoke, convertFileSrc } from '@tauri-apps/api/core';\n","import { invoke, convertFileSrc } from '@tauri-apps/api/core';\nimport { getVersion } from '@tauri-apps/api/app';\n"),
 ("import { open, message } from '@tauri-apps/plugin-dialog';\n","import { open, message } from '@tauri-apps/plugin-dialog';\nimport { check } from '@tauri-apps/plugin-updater';\nimport { relaunch } from '@tauri-apps/plugin-process';\n")
]
for anchor,insert in imports:
    if insert.splitlines()[-1] not in s:
        if anchor not in s: raise SystemExit('8.42: tauri import anchor missing')
        s=s.replace(anchor,insert,1)
start=s.find('  checkUpdate:async()=>{')
if start<0: raise SystemExit('8.42: checkUpdate missing')
# Support either historical/native updateStatus tail.
end=s.find('\n};',start)
if end<0: raise SystemExit('8.42: api object end missing')
# Replace from checkUpdate through the final updateStatus member without touching earlier APIs.
prefix=s[:start]
block=r'''  appVersion:()=>getVersion(),
  checkUpdate:async()=>{
    const current=await getVersion();
    const update=await withTimeout(check(),20000,'Проверка обновлений');
    if(!update)return {none:true,current,channel:'github-signed'};
    return {
      version:update.version,
      date:update.date||'',
      body:update.body||'',
      current,
      channel:'github-signed',
      install:async(onProgress?:(percent:number,stage?:string)=>void)=>{
        let total=0;
        let downloaded=0;
        onProgress?.(1,'Подготавливаю подписанное обновление');
        await update.downloadAndInstall((event)=>{
          if(event.event==='Started'){
            total=event.data.contentLength||0;
            downloaded=0;
            onProgress?.(3,'Скачиваю обновление');
          }else if(event.event==='Progress'){
            downloaded+=event.data.chunkLength||0;
            const pct=total>0?Math.min(94,3+Math.round(downloaded/total*91)):25;
            onProgress?.(pct,'Скачиваю обновление');
          }else if(event.event==='Finished'){
            onProgress?.(97,'Устанавливаю обновление');
          }
        });
        onProgress?.(100,'Обновление установлено');
        await relaunch();
      }
    };
  },
  updateStatus:async()=>({state:'native',stage:'Tauri signed updater',progress:0})
'''
s=prefix+block+s[end:]
if any(x in s for x in ('local_update_check','local_update_start','local_update_status')):
    raise SystemExit('8.42: legacy frontend updater survived')
for x in ("@tauri-apps/plugin-updater","@tauri-apps/plugin-process","@tauri-apps/api/app","check()","downloadAndInstall","relaunch()","getVersion()"):
    if x not in s: raise SystemExit('8.42: native updater wiring incomplete: '+x)
p.write_text(s,encoding='utf-8')

# Remove legacy backend from runtime. File may remain historical but is not compiled or invoked.
p=Path('src-tauri/src/lib.rs')
r=p.read_text(encoding='utf-8')
r=r.replace('mod updater_local;\n','')
r=re.sub(r'\s*updater_local::local_update_check,updater_local::local_update_start,updater_local::local_update_status\n','\n',r)
r=r.replace(',\n    ])','\n    ])')
if 'updater_local::' in r or 'mod updater_local;' in r: raise SystemExit('8.42: legacy backend still registered')
for x in ('tauri_plugin_process::init()','tauri_plugin_updater::Builder::new().build()'):
    if x not in r: raise SystemExit('8.42: required Rust plugin missing: '+x)
p.write_text(r,encoding='utf-8')

# Settings: runtime version from getVersion, two-step check/install, no local-builder wording.
p=Path('src/pages/SettingsPage.tsx')
ui=p.read_text(encoding='utf-8')
fn='export function SettingsPage(){\n'
if fn not in ui: raise SystemExit('8.42: SettingsPage function marker missing')
if 'const [appVersion,setAppVersion]' not in ui:
    ui=ui.replace(fn,fn+"  const [appVersion,setAppVersion]=useState('');\n",1)
old_effect='useEffect(()=>{api.license().then(setLicense).catch(()=>{});api.cacheStats().then(setCache).catch(()=>{});api.cleanupDuplicateApps(false).then(setAppGuard).catch(()=>{})},[]);'
if old_effect in ui:
    ui=ui.replace(old_effect,"useEffect(()=>{api.license().then(setLicense).catch(()=>{});api.cacheStats().then(setCache).catch(()=>{});api.cleanupDuplicateApps(false).then(setAppGuard).catch(()=>{});api.appVersion().then(setAppVersion).catch(()=>{})},[]);",1)
elif 'api.appVersion().then(setAppVersion)' not in ui:
    raise SystemExit('8.42: Settings useEffect marker missing')
ui=re.sub(r'<p>ENDLUME Studio 1\.0\.0-alpha\.8\.\d+</p>',"<p>ENDLUME Studio {appVersion||'—'}</p>",ui,count=1)
ui=re.sub(r'<span>Версия <b>1\.0\.0-alpha\.8\.\d+</b></span>',"<span>Версия <b>{appVersion||'—'}</b></span>",ui,count=1)
ui=ui.replace('Подписанные обновления ENDLUME проверяются и устанавливаются через интернет внутри приложения. Terminal и ручная сборка для обновления не нужны.','ENDLUME Studio автоматически проверяет подписанные обновления через интернет.')
ui=ui.replace('Для текущего локального режима рекомендуем обновлять ENDLUME через локальный builder на Mac. Online updater можно оставить как резервный канал.','ENDLUME Studio автоматически проверяет подписанные обновления через интернет.')
ui=ui.replace('Обновления собираются на подписанном интернет-канале. Этот Mac только скачивает проверенную готовую ENDLUME, устанавливает её и перезапускает приложение — без npm, Rust и Terminal.','ENDLUME Studio автоматически проверяет подписанные обновления через интернет.')
ui=ui.replace('ПРОВЕРИТЬ И ОБНОВИТЬ','ПРОВЕРИТЬ ОБНОВЛЕНИЯ')
ui=ui.replace('УСТАНОВИТЬ И ПЕРЕЗАПУСТИТЬ','ОБНОВИТЬ')
ui=ui.replace("'ОБНОВИТЬ'","`ОБНОВИТЬ ДО ${update.version}`")
if 'ПРОВЕРИТЬ ОБНОВЛЕНИЯ' not in ui: raise SystemExit('8.42: check button missing')
if 'Доступна ENDLUME' not in ui: raise SystemExit('8.42: available-update UI missing')
if 'локальный builder' in ui: raise SystemExit('8.42: obsolete builder wording survived')
if 'appVersion' not in ui: raise SystemExit('8.42: dynamic runtime version missing')
p.write_text(ui,encoding='utf-8')

print('ENDLUME 8.42 native online updater-only migration applied')
