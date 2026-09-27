from pathlib import Path
import json

BOOT=Path('updates/github/bootstrap.json')
if not BOOT.is_file():
    raise SystemExit('8.40: updates/github/bootstrap.json missing')
b=json.loads(BOOT.read_text(encoding='utf-8'))
endpoint=str(b.get('endpoint','')).strip()
pubkey=str(b.get('pubkey','')).strip()
EXPECTED='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/latest.json'
if endpoint!=EXPECTED:
    raise SystemExit('8.40: unexpected GitHub updater endpoint')
if not pubkey:
    raise SystemExit('8.40: updater public key missing')

# Configure official Tauri updater from the bootstrap generated on the owner Mac.
p=Path('src-tauri/tauri.conf.json')
cfg=json.loads(p.read_text(encoding='utf-8'))
plugins=cfg.setdefault('plugins',{})
up=plugins.setdefault('updater',{})
up['pubkey']=pubkey
up['endpoints']=[endpoint]
p.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# Replace historical local updater frontend with official Tauri updater API.
p=Path('src/tauri.ts')
s=p.read_text(encoding='utf-8')
if "@tauri-apps/plugin-updater" not in s:
    anchor="import { open, message } from '@tauri-apps/plugin-dialog';\n"
    if anchor not in s: raise SystemExit('8.40: tauri.ts dialog import anchor missing')
    s=s.replace(anchor,anchor+"import { check } from '@tauri-apps/plugin-updater';\nimport { relaunch } from '@tauri-apps/plugin-process';\nimport { getVersion } from '@tauri-apps/api/app';\n",1)
elif "@tauri-apps/api/app" not in s:
    anchor="import { relaunch } from '@tauri-apps/plugin-process';\n"
    if anchor not in s: raise SystemExit('8.40: process import anchor missing')
    s=s.replace(anchor,anchor+"import { getVersion } from '@tauri-apps/api/app';\n",1)

start=s.find('  checkUpdate:async()=>{')
if start<0: raise SystemExit('8.40: checkUpdate API block missing')
end_marker="  updateStatus:()=>invoke<{state:string;stage?:string;progress:number;message?:string;logPath?:string}>('local_update_status')\n"
end=s.find(end_marker,start)
if end<0: raise SystemExit('8.40: historical updateStatus marker missing')
end+=len(end_marker)
new_block=r'''  checkUpdate:async()=>{
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
s=s[:start]+new_block+s[end:]
if "local_update_check" in s or "local_update_start" in s or "local_update_status" in s:
    raise SystemExit('8.40: local_update_* frontend calls survived')
if "check()" not in s or 'downloadAndInstall' not in s or 'relaunch()' not in s or 'getVersion()' not in s:
    raise SystemExit('8.40: native updater wiring incomplete')
p.write_text(s,encoding='utf-8')

# 8.37 already converts Settings to a two-step check/install UI. Keep that
# structure; only normalize the wording away from obsolete updater models.
p=Path('src/pages/SettingsPage.tsx')
ui=p.read_text(encoding='utf-8')
if 'const checkUpdate=async()=>{' not in ui or 'const installUpdate=async()=>{' not in ui:
    raise SystemExit('8.40: expected 8.37 two-step Settings handlers missing')
if 'onClick={checkUpdate}' not in ui or 'onClick={installUpdate}' not in ui:
    raise SystemExit('8.40: expected two-step Settings buttons missing')

old_notes=[
 '<p className="settingsNote">Для текущего локального режима рекомендуем обновлять ENDLUME через локальный builder на Mac. Online updater можно оставить как резервный канал.</p>',
 '<p className="settingsNote">Обновления собираются на удалённом macOS-сервере. Этот Mac только скачивает проверенную готовую ENDLUME, устанавливает её и перезапускает приложение — без npm, Rust и Terminal.</p>'
]
new_note='<p className="settingsNote">Подписанные обновления ENDLUME проверяются и устанавливаются через интернет внутри приложения. Terminal и ручная сборка для обновления не нужны.</p>'
for old in old_notes:
    ui=ui.replace(old,new_note)

# Last-resort normalization for historical wording variants. These replacements
# intentionally remove only obsolete updater wording, not functional JSX.
ui=ui.replace('ПРОВЕРИТЬ И ОБНОВИТЬ','ПРОВЕРИТЬ ОБНОВЛЕНИЯ')
ui=ui.replace('локальный builder','ручная сборка')
ui=ui.replace('удалённом macOS-сервере','подписанном интернет-канале')
ui=ui.replace('Обновляется только /Applications/ENDLUME Studio.app. После установки приложение автоматически перезапустится.','Пакет проверяется цифровой подписью. После установки ENDLUME автоматически перезапустится.')
ui=ui.replace('УСТАНОВИТЬ И ПЕРЕЗАПУСТИТЬ','ОБНОВИТЬ')

if new_note not in ui:
    # If wording was structurally different, inject the canonical note directly
    # into the updates card after the version line instead of failing on copy text.
    marker="{tab==='updates'&&<div className=\"settingsCard\"><h3>Обновления</h3>"
    mi=ui.find(marker)
    if mi<0: raise SystemExit('8.40: updates card missing')
    p_end=ui.find('</p>',mi)
    if p_end<0: raise SystemExit('8.40: updates version line missing')
    ui=ui[:p_end+4]+new_note+ui[p_end+4:]

if 'ПРОВЕРИТЬ ОБНОВЛЕНИЯ' not in ui or 'Доступна ENDLUME' not in ui:
    raise SystemExit('8.40: two-step updater UI text incomplete')
if 'ПРОВЕРИТЬ И ОБНОВИТЬ' in ui or 'локальный builder' in ui or 'удалённом macOS-сервере' in ui:
    raise SystemExit('8.40: obsolete updater UI text survived after normalization')
p.write_text(ui,encoding='utf-8')

print('ENDLUME 8.40 native signed GitHub updater normalized; obsolete UI self-trigger removed')
