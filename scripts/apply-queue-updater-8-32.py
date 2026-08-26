from pathlib import Path


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'8.32: marker missing: {label}')
    return text.replace(old, new, 1)

# ---- Zustand queue state: repeated renders get unique IDs and queue survives navigation/relaunch.
p=Path('src/store.ts'); s=p.read_text(encoding='utf-8')
s=replace_once(s,
'''  appendProjects:(p:RenderProject[])=>void;\n  patchProject:(id:string,p:Partial<RenderProject>)=>void;''',
'''  appendProjects:(p:RenderProject[])=>void;\n  syncQueueProjects:(p:RenderProject[])=>void;\n  patchProject:(id:string,p:Partial<RenderProject>)=>void;''','store interface')
s=replace_once(s,
'''  appendProjects:(v)=>set(s=>({projects:[...s.projects,...v.filter(n=>!s.projects.some(p=>p.path===n.path&&p.status!=='done'))]})),\n  patchProject:(id,patch)=>set(s=>({projects:s.projects.map(p=>p.id===id?{...p,...patch}:p)})),''',
'''  appendProjects:(v)=>set(s=>{const known=new Set(s.projects.map(p=>p.id));return {projects:[...s.projects,...v.filter(n=>!known.has(n.id))]}}),\n  syncQueueProjects:(incoming)=>set(s=>{\n    const incomingIds=new Set(incoming.map(p=>p.id));\n    const oldById=new Map(s.projects.map(p=>[p.id,p]));\n    const terminal=s.projects.filter(p=>['done','error'].includes(p.status)&&!incomingIds.has(p.id));\n    const live=incoming.map(p=>{const old=oldById.get(p.id);if(!old)return p;return {...old,...p,progress:p.status==='rendering'?Math.max(old.progress||0,p.progress||0):p.progress,stage:p.status==='rendering'&&old.stage?old.stage:p.stage,elapsedSec:p.status==='rendering'?Math.max(old.elapsedSec||0,p.elapsedSec||0):p.elapsedSec}});\n    return {projects:[...terminal,...live]};\n  }),\n  patchProject:(id,patch)=>set(s=>({projects:s.projects.map(p=>p.id===id?{...p,...patch}:p)})),''','store queue merge')
s=replace_once(s,
'''{name:'endlume-1-ui',partialize:(s)=>({settings:s.settings,lastRoot:s.lastRoot})}));''',
'''{name:'endlume-1-ui',version:2,partialize:(s)=>({settings:s.settings,lastRoot:s.lastRoot,projects:s.projects})}));''','store persistence')
p.write_text(s,encoding='utf-8')

# ---- Project page: every enqueue is a new queue job even when the same folder is rendered twice.
p=Path('src/pages/ProjectPage.tsx'); s=p.read_text(encoding='utf-8')
s=replace_once(s,
'''      const activeEffects=features.effects?effects.filter(e=>e.enabled):[];\n      const activeSubscribes=features.subscribe?subscribes.filter(e=>e.enabled):[];\n      const activeAmbient=features.ambient?ambient:undefined;\n      await api.enqueue(draftProjects,settings,activeEffects,activeSubscribes,activeAmbient);\n      appendProjects(draftProjects.map(p=>({...p,status:'queued',stage:'Ожидает в очереди'})));''',
'''      const activeEffects=features.effects?effects.filter(e=>e.enabled):[];\n      const activeSubscribes=features.subscribe?subscribes.filter(e=>e.enabled):[];\n      const activeAmbient=features.ambient?ambient:undefined;\n      const stamp=Date.now().toString(36);\n      const queuedProjects=draftProjects.map((p,i)=>({...p,id:`${p.id}-${stamp}-${i}-${Math.random().toString(36).slice(2,8)}`,status:'queued' as const,progress:0,stage:'Ожидает в очереди',elapsedSec:0}));\n      await api.enqueue(queuedProjects,settings,activeEffects,activeSubscribes,activeAmbient);\n      appendProjects(queuedProjects);''','unique enqueue ids')
p.write_text(s,encoding='utf-8')

# ---- App: reconcile UI with backend queue snapshot. This fixes invisible second/third jobs.
p=Path('src/pages/App.tsx'); s=p.read_text(encoding='utf-8')
helper='''\nfunction syncBackendQueue(snapshot:any){\n  const st=useApp.getState();\n  const old=new Map(st.projects.map(p=>[p.id,p]));\n  const items:any[]=[];\n  const push=(job:any,status:'rendering'|'queued')=>{\n    const project=job?.project;if(!project?.id)return;const prev=old.get(project.id);\n    items.push({...project,status,progress:status==='rendering'?(prev?.progress||0):0,stage:status==='rendering'?(prev?.stage||'Восстанавливаю текущий этап…'):'Ожидает в очереди',elapsedSec:prev?.elapsedSec||0,startedAt:prev?.startedAt,etaSec:prev?.etaSec,encoder:prev?.encoder,engineTimings:prev?.engineTimings});\n  };\n  if(snapshot?.active)push(snapshot.active,'rendering');\n  for(const job of snapshot?.pending||[])push(job,'queued');\n  st.syncQueueProjects(items);\n}\n'''
if 'function syncBackendQueue(' not in s:
    marker='''function compactPayload<T extends Record<string,any>>(value:T):Partial<T>{\n  return Object.fromEntries(Object.entries(value||{}).filter(([,v])=>v!==null&&v!==undefined)) as Partial<T>;\n}\n'''
    if marker not in s: raise SystemExit('8.32: App helper marker missing')
    s=s.replace(marker,marker+helper,1)
s=replace_once(s,
'''  const page=useApp(s=>s.page),editor=useApp(s=>s.editor),patchProject=useApp(s=>s.patchProject),setLibrary=useApp(s=>s.setLibrary),appendProjects=useApp(s=>s.appendProjects);''',
'''  const page=useApp(s=>s.page),editor=useApp(s=>s.editor),patchProject=useApp(s=>s.patchProject),setLibrary=useApp(s=>s.setLibrary),appendProjects=useApp(s=>s.appendProjects);''','App destructure noop')
# startup snapshot after recovery read
needle="""    api.loadRecovery().then(r=>{if(r?.interrupted)setRecovery(r)}).catch(()=>{});\n"""
insert=needle+"    api.queueSnapshot().then(syncBackendQueue).catch(()=>{});\n"
if 'api.queueSnapshot().then(syncBackendQueue)' not in s:
    if needle not in s: raise SystemExit('8.32: startup snapshot marker missing')
    s=s.replace(needle,insert,1)
# queue-changed listener
needle="""    off.push(listen<any>('render-progress',e=>patchProject(e.payload.id,compactPayload(e.payload))));\n"""
insert="""    off.push(listen<any>('queue-changed',e=>syncBackendQueue(e.payload)));\n"""+needle
if "listen<any>('queue-changed'" not in s:
    if needle not in s: raise SystemExit('8.32: queue listener marker missing')
    s=s.replace(needle,insert,1)
# UpdateNotice stage UI
s=s.replace("const [progress,setProgress]=useState<number|null>(null),[error,setError]=useState('');","const [progress,setProgress]=useState<number|null>(null),[stage,setStage]=useState(''),[error,setError]=useState('');")
s=s.replace("{progress!==null&&<div className=\"updateNoticeProgress\"><i style={{width:`${progress}%`}}/><span>{progress<100?`Скачиваю ${progress.toFixed(0)}%`:'Устанавливаю…'}</span></div>}","{progress!==null&&<div className=\"updateNoticeProgress\"><i style={{width:`${progress}%`}}/><span>{stage||`Обновляю ${progress.toFixed(0)}%`}</span></div>}")
s=s.replace("await update.install((p:number)=>setProgress(p))","await update.install((p:number,s?:string)=>{setProgress(p);if(s)setStage(s)})")
p.write_text(s,encoding='utf-8')

# ---- Frontend API: use private local updater through gh auth, no Terminal and no GitHub Actions.
p=Path('src/tauri.ts'); s=p.read_text(encoding='utf-8')
s=s.replace("import { check } from '@tauri-apps/plugin-updater';\n",'')
s=s.replace("import { relaunch } from '@tauri-apps/plugin-process';\n",'')
start=s.find('  checkUpdate:async()=>{')
if start<0: raise SystemExit('8.32: checkUpdate start missing')
end=s.find('\n  }\n};',start)
if end<0: raise SystemExit('8.32: checkUpdate end missing')
new=r'''  checkUpdate:async()=>{
    type Info={supported:boolean;available:boolean;current:string;version?:string;notes?:string;date?:string;reason?:string};
    type Status={state:string;stage?:string;progress:number;message?:string;logPath?:string};
    const info=await withTimeout(invoke<Info>('local_update_check'),15000,'Проверка обновлений');
    if(!info.supported){return {none:true,current:info.current,channel:'private-local',warning:info.reason};}
    if(!info.available||!info.version)return {none:true,current:info.current,channel:'private-local'};
    return {
      version:info.version,date:info.date,body:info.notes||'',current:info.current,channel:'private-local',
      install:async(onProgress?:(percent:number,stage?:string)=>void)=>{
        await invoke<Status>('local_update_start');
        onProgress?.(1,'Подготавливаю обновление');
        for(;;){
          await new Promise(r=>window.setTimeout(r,900));
          const st=await invoke<Status>('local_update_status');
          onProgress?.(st.progress||0,st.stage||undefined);
          if(st.state==='failed')throw new Error(st.message||`Обновление остановлено. Лог: ${st.logPath||'ENDLUME update.log'}`);
          if(st.state==='success'){onProgress?.(100,'Обновление установлено');return;}
        }
      }
    };
  },
  updateStatus:()=>invoke<{state:string;stage?:string;progress:number;message?:string;logPath?:string}>('local_update_status')'''
s=s[:start]+new+s[end+4:]
# ensure object ending only once
if not s.rstrip().endswith('};'): raise SystemExit('8.32: tauri object malformed')
p.write_text(s,encoding='utf-8')

# ---- Settings: update entirely in app, no command-line wording.
p=Path('src/pages/SettingsPage.tsx'); s=p.read_text(encoding='utf-8')
s=s.replace("[updateProgress,setUpdateProgress]=useState<number|null>(null)","[updateProgress,setUpdateProgress]=useState<number|null>(null)")
# add stage state by targeting large declaration suffix
s=s.replace("[update,setUpdate]=useState<any>(),[updateProgress,setUpdateProgress]=useState<number|null>(null),[cache,setCache]", "[update,setUpdate]=useState<any>(),[updateProgress,setUpdateProgress]=useState<number|null>(null),[updateStage,setUpdateStage]=useState(''),[cache,setCache]")
s=s.replace("if(busy)return;setBusy(true);setUpdateProgress(null);", "if(busy)return;setBusy(true);setUpdateProgress(null);setUpdateStage('');")
s=s.replace("await u.install((p:number)=>setUpdateProgress(p));", "await u.install((p:number,s?:string)=>{setUpdateProgress(p);if(s)setUpdateStage(s)});")
# replace updates tab wholesale between tab updates and about marker
start=s.find("    {tab==='updates'&&")
end=s.find("    {tab==='about'&&",start)
if start<0 or end<0: raise SystemExit('8.32: Settings updates block missing')
block='''    {tab==='updates'&&<div className="settingsCard"><h3>Обновления</h3><p>ENDLUME Studio 1.0.0-alpha.8.32</p><p className="settingsNote">Обновление устанавливается прямо внутри ENDLUME Studio. Terminal и командная строка не открываются. Исходники берутся из приватного release-канала, проходят проверки и только после этого заменяется одно приложение в /Applications.</p><button className="settingsAction" disabled={busy} onClick={checkAndInstall}>{busy?(updateStage||'ПРОВЕРЯЮ…'):'ПРОВЕРИТЬ И ОБНОВИТЬ'}</button>{updateProgress!==null&&<div className="updateProgress"><i style={{width:`${updateProgress}%`}}/><span>{updateProgress.toFixed(0)}%{updateStage?` • ${updateStage}`:''}</span></div>}{update?.none&&<div><p className="updateOk">Установлена актуальная версия: {update.current||'1.0.0-alpha.8.32'}.</p>{update.warning&&<p className="settingsNote">{update.warning}</p>}</div>}{update?.version&&<div className="updateFound"><b>Устанавливается ENDLUME {update.version}</b>{update.date&&<small>{String(update.date)}</small>}<p>{update.body}</p><p className="settingsNote">Во время сборки ENDLUME остаётся рабочей. В момент финальной замены приложение закроется и автоматически откроется уже новой версией.</p></div>}{update?.error&&<p className="updateError">Ошибка обновления: {update.error}</p>}<div className="whatsNew"><h4>SINGLE APP GUARD</h4><p className={appHealthy?'updateOk':'settingsNote'}>{appGuard?.supported===false?'На этой системе не требуется.':appHealthy?'✓ Одна установка: /Applications/ENDLUME Studio.app.':appGuard?.canonicalInstall===false?`ENDLUME запущена не из канонического места. Нужно: /Applications/ENDLUME Studio.app.`:appGuard?`Найдено копий: ${appGuard.remaining?.length||appGuard.found?.length||0}.`:'Проверяю приложения…'}</p>{appGuard?.supported!==false&&appGuard?.canonicalInstall===false&&<button className="settingsAction" disabled={busy} onClick={normalizeName}>ЗАКРЕПИТЬ В /APPLICATIONS КАК ENDLUME STUDIO</button>}{appGuard?.supported!==false&&!appGuard?.singleApp&&<button className="settingsAction" disabled={busy} onClick={cleanDuplicates}>УДАЛИТЬ КЛОНЫ ENDLUME</button>}<ReleaseHistory/></div></div>}\n'''
s=s[:start]+block+s[end:]
# about version
s=s.replace('Версия <b>1.0.0-alpha.8.19</b>','Версия <b>1.0.0-alpha.8.32</b>').replace('Обновлено <b>24.08.2026</b>','Обновлено <b>26.08.2026</b>')
p.write_text(s,encoding='utf-8')

# ---- Rust command registration.
p=Path('src-tauri/src/lib.rs'); s=p.read_text(encoding='utf-8')
if 'mod updater_local;' not in s:s=s.replace('mod system;','mod system;\nmod updater_local;')
needle='system::power_status,system::disk_status,system::cleanup_duplicate_apps,system::normalize_current_app_name,system::open_result_path,system::reveal_result_path'
repl=needle+',\n      updater_local::local_update_check,updater_local::local_update_start,updater_local::local_update_status'
if 'updater_local::local_update_check' not in s:
    if needle not in s:raise SystemExit('8.32: lib invoke marker missing')
    s=s.replace(needle,repl,1)
p.write_text(s,encoding='utf-8')

print('ENDLUME alpha.8.32 queue visibility + in-app updater patch applied')
