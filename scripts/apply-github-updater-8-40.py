from pathlib import Path
import json,re

BOOT=Path('updates/github/bootstrap.json')
if not BOOT.is_file():
    raise SystemExit('8.40: updates/github/bootstrap.json missing')
b=json.loads(BOOT.read_text(encoding='utf-8'))
endpoint=str(b.get('endpoint','')).strip()
pubkey=str(b.get('pubkey','')).strip()
if endpoint!='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/latest.json':
    raise SystemExit('8.40: unexpected GitHub updater endpoint')
if not pubkey:
    raise SystemExit('8.40: updater public key missing')

# Configure official Tauri updater.
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
if start<0: raise SystemExit('8.40: checkUpdate block missing')
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

# Update Settings UI to a true two-step flow: check first, explicit install second.
p=Path('src/pages/SettingsPage.tsx')
ui=p.read_text(encoding='utf-8')
old_fn="""  const checkAndInstall=async()=>{\n    if(busy)return;setBusy(true);setUpdateProgress(null);\n    try{const u=await api.checkUpdate();setUpdate(u||{none:true});if(u?.version&&u?.install){setUpdateProgress(0);await u.install((p:number)=>setUpdateProgress(p));}}\n    catch(e){setUpdateProgress(null);setUpdate({error:String(e)});await api.showError(`Не удалось обновить ENDLUME: ${String(e)}`)}finally{setBusy(false)}\n  };\n"""
new_fn="""  const checkForUpdate=async()=>{\n    if(busy)return;setBusy(true);setUpdateProgress(null);setUpdate(undefined);\n    try{const u=await api.checkUpdate();setUpdate(u||{none:true});}\n    catch(e){setUpdateProgress(null);setUpdate({error:String(e)});await api.showError(`Не удалось проверить обновления ENDLUME: ${String(e)}`)}finally{setBusy(false)}\n  };\n  const installFoundUpdate=async()=>{\n    if(busy||!update?.install)return;setBusy(true);setUpdateProgress(0);\n    try{await update.install((p:number)=>setUpdateProgress(p));}\n    catch(e){setUpdateProgress(null);setUpdate((u:any)=>({...u,error:String(e)}));await api.showError(`Не удалось установить обновление ENDLUME: ${String(e)}`)}finally{setBusy(false)}\n  };\n"""
if old_fn not in ui: raise SystemExit('8.40: Settings checkAndInstall block missing')
ui=ui.replace(old_fn,new_fn,1)
old_note='<p className="settingsNote">Для текущего локального режима рекомендуем обновлять ENDLUME через локальный builder на Mac. Online updater можно оставить как резервный канал.</p>'
new_note='<p className="settingsNote">Подписанные обновления ENDLUME загружаются через интернет и устанавливаются внутри приложения. Terminal и локальный builder не используются.</p>'
if old_note not in ui: raise SystemExit('8.40: old local updater Settings note missing')
ui=ui.replace(old_note,new_note,1)
old_button='<button className="settingsAction" disabled={busy} onClick={checkAndInstall}>{busy?(updateProgress!==null?`ОБНОВЛЯЮ ${updateProgress.toFixed(0)}%`:\'ПРОВЕРЯЮ…\'):\'ПРОВЕРИТЬ И ОБНОВИТЬ\'}</button>'
new_button='<button className="settingsAction" disabled={busy} onClick={checkForUpdate}>{busy&&updateProgress===null?\'ПРОВЕРЯЮ…\':\'ПРОВЕРИТЬ ОБНОВЛЕНИЯ\'}</button>'
if old_button not in ui: raise SystemExit('8.40: old combined update button missing')
ui=ui.replace(old_button,new_button,1)
old_found='<div className="updateFound"><b>Устанавливается ENDLUME {update.version}</b>{update.date&&<small>{String(update.date)}</small>}<p>{update.body}</p><p className="settingsNote">Обновляется только /Applications/ENDLUME Studio.app. После установки приложение автоматически перезапустится.</p></div>'
new_found='<div className="updateFound"><b>Доступна ENDLUME {update.version}</b>{update.date&&<small>{String(update.date)}</small>}<p>{update.body}</p><button className="settingsAction" disabled={busy} onClick={installFoundUpdate}>{busy&&updateProgress!==null?`ОБНОВЛЯЮ ${updateProgress.toFixed(0)}%`:\'ОБНОВИТЬ\'}</button><p className="settingsNote">Пакет проверяется цифровой подписью. После установки ENDLUME автоматически перезапустится.</p></div>'
if old_found not in ui: raise SystemExit('8.40: old auto-install updateFound block missing')
ui=ui.replace(old_found,new_found,1)
if 'checkAndInstall' in ui or 'ПРОВЕРИТЬ И ОБНОВИТЬ' in ui or 'локальный builder' in ui:
    raise SystemExit('8.40: old combined/local updater UI survived')
if 'onClick={checkForUpdate}' not in ui or 'onClick={installFoundUpdate}' not in ui or 'Доступна ENDLUME' not in ui:
    raise SystemExit('8.40: two-step updater UI incomplete')
p.write_text(ui,encoding='utf-8')

print('ENDLUME 8.40 native signed GitHub updater + two-step Settings UI applied')
