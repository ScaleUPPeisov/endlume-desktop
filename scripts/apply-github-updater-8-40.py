from pathlib import Path
import json,re

BOOT=Path('updates/github/bootstrap.json')
if not BOOT.is_file():
    raise SystemExit('8.40: updates/github/bootstrap.json missing')
b=json.loads(BOOT.read_text(encoding='utf-8'))
endpoint=str(b.get('endpoint','')).strip()
pubkey=str(b.get('pubkey','')).strip()
if not endpoint.startswith('https://github.com/') or not endpoint.endswith('/latest.json'):
    raise SystemExit('8.40: invalid GitHub updater endpoint')
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
    s=s.replace(anchor,anchor+"import { check } from '@tauri-apps/plugin-updater';\nimport { relaunch } from '@tauri-apps/plugin-process';\n",1)

start=s.find('  checkUpdate:async()=>{')
if start<0: raise SystemExit('8.40: checkUpdate block missing')
end_marker="  updateStatus:()=>invoke<{state:string;stage?:string;progress:number;message?:string;logPath?:string}>('local_update_status')\n"
end=s.find(end_marker,start)
if end<0: raise SystemExit('8.40: historical updateStatus marker missing')
end+=len(end_marker)
new_block=r'''  checkUpdate:async()=>{
    const update=await withTimeout(check(),20000,'Проверка обновлений');
    if(!update)return {none:true,current:'current',channel:'github-signed'};
    return {
      version:update.version,
      date:update.date||'',
      body:update.body||'',
      current:update.currentVersion||'',
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

# No installed app update path may depend on local builder commands anymore.
if "local_update_check" in s or "local_update_start" in s or "local_update_status" in s:
    raise SystemExit('8.40: local_update_* frontend calls survived')
if "check()" not in s or 'downloadAndInstall' not in s or 'relaunch()' not in s:
    raise SystemExit('8.40: native updater wiring incomplete')
p.write_text(s,encoding='utf-8')

print('ENDLUME 8.40 native signed GitHub updater applied')
