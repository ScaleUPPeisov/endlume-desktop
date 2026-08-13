import React, { useEffect, useState } from 'react';
import { listen } from '@tauri-apps/api/event';
import { Topbar } from '../components/shell';
import { RecoveryModal } from '../components/recovery';
import { useApp } from '../store';
import { api } from '../tauri';
import type { LicenseStatus, RecoveryPayload } from '../types';
import { ProjectPage } from './ProjectPage';
import { RenderPage } from './RenderPage';
import { LibraryPage } from './LibraryPage';
import { SettingsPage } from './SettingsPage';
import { EditorRouter } from './Editors';

function compactPayload<T extends Record<string,any>>(value:T):Partial<T>{
  return Object.fromEntries(Object.entries(value||{}).filter(([,v])=>v!==null&&v!==undefined)) as Partial<T>;
}

export function App(){
  const page=useApp(s=>s.page),editor=useApp(s=>s.editor),patchProject=useApp(s=>s.patchProject),setLibrary=useApp(s=>s.setLibrary),appendProjects=useApp(s=>s.appendProjects);
  const [recovery,setRecovery]=useState<RecoveryPayload>();
  const [license,setLicense]=useState<LicenseStatus|null>(null);
  const [availableUpdate,setAvailableUpdate]=useState<any>(null);
  useEffect(()=>{
    api.license().then(setLicense).catch(()=>setLicense({valid:false}));
    api.loadLibrary().then(setLibrary).catch(()=>setLibrary({effects:[],subscribes:[]}));
    api.loadRecovery().then(r=>{if(r?.interrupted)setRecovery(r)}).catch(()=>{});
    const updateTimer=window.setTimeout(()=>{api.checkUpdate().then(u=>{if(u?.version)setAvailableUpdate(u)}).catch(()=>{})},2200);
    const off:Promise<()=>void>[]=[];
    off.push(listen<any>('render-progress',e=>patchProject(e.payload.id,compactPayload(e.payload))));
    off.push(listen<any>('render-done',e=>patchProject(e.payload.id,compactPayload(e.payload))));
    off.push(listen<any>('render-error',e=>patchProject(e.payload.id,compactPayload(e.payload))));
    off.push(listen<any>('queue-recovered',e=>{const p=(e.payload?.projects||[]).map((x:any)=>({...x,status:'queued',progress:0,stage:'Восстановлено после сбоя',elapsedSec:0}));appendProjects(p)}));
    off.push(listen<any>('engine-timing',e=>{const {id,key,seconds}=e.payload||{};if(id&&key)patchProject(id,{engineTimings:{...(useApp.getState().projects.find(p=>p.id===id)?.engineTimings||{}),[key]:seconds}})}));
    off.push(listen<any>('engine-profile',e=>{const {id,...rest}=e.payload||{};if(id)patchProject(id,compactPayload(rest))}));
    off.push(listen<any>('cache-updated',e=>{const {id,cacheKey,cacheReady}=e.payload||{};if(!id)return;const st=useApp.getState();const effects=st.effects.map(x=>x.id===id?{...x,cacheKey,cacheReady}:x);const subscribes=st.subscribes.map(x=>x.id===id?{...x,cacheKey,cacheReady}:x);st.setEffects(effects);st.setSubscribes(subscribes);api.saveLibrary({effects,subscribes,ambient:st.ambient}).catch(()=>{});}));
    return()=>{window.clearTimeout(updateTimer);off.forEach(p=>p.then(f=>f()))}
  },[]);
  if(!license)return <div className="bootScreen"><div className="bootPulse"/>ENDLUME</div>;
  if(!license.valid)return <ActivationScreen onActivated={setLicense}/>;
  return <div className="appShell"><Topbar/><div className="content">{page==='project'?<ProjectPage/>:page==='render'?<RenderPage/>:page==='library'?<LibraryPage/>:<SettingsPage/>}</div>{editor&&<EditorRouter/>}{recovery&&<RecoveryModal data={recovery} onClose={()=>setRecovery(undefined)}/>} {availableUpdate&&<UpdateNotice update={availableUpdate} onLater={()=>setAvailableUpdate(null)}/>}</div>
}

function ActivationScreen({onActivated}:{onActivated:(v:LicenseStatus)=>void}){
  const [key,setKey]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  return <div className="activationScreen"><div className="activationCard"><div className="activationBrand"><span className="activationInfinity">∞</span><div><b>ENDLUME</b><small>STUDIO</small></div></div><h1>Активация ENDLUME</h1><p>Для запуска введите ключ лицензии. После активации рендер работает локально и не требует постоянного интернета.</p><input autoFocus placeholder="ENDLUME-XXXX-XXXX-XXXX" value={key} onChange={e=>setKey(e.target.value)} onKeyDown={e=>e.key==='Enter'&&document.getElementById('activate')?.click()}/>{error&&<div className="activationError">{error}</div>}<button id="activate" disabled={busy||!key.trim()} onClick={async()=>{setBusy(true);setError('');try{onActivated(await api.activate(key))}catch(e){setError(String(e))}finally{setBusy(false)}}}>{busy?'ПРОВЕРЯЮ КЛЮЧ…':'АКТИВИРОВАТЬ →'}</button><small className="activationFoot">ENDLUME Studio 1.0 • Windows / macOS Apple Silicon</small></div></div>
}


function UpdateNotice({update,onLater}:{update:any;onLater:()=>void}){
  const [progress,setProgress]=useState<number|null>(null),[error,setError]=useState('');
  const installing=progress!==null;
  return <aside className="updateNotice" role="status" aria-live="polite">
    <div className="updateNoticeGlow"/>
    <div className="updateNoticeHead"><span className="updateNoticeDot"/><div><b>Вышло новое обновление</b><small>ENDLUME {update.version}{update.date?` • ${formatUpdateDate(update.date)}`:''}</small></div></div>
    <p>{shortUpdateText(update.body)}</p>
    {progress!==null&&<div className="updateNoticeProgress"><i style={{width:`${progress}%`}}/><span>{progress<100?`Скачиваю ${progress.toFixed(0)}%`:'Устанавливаю…'}</span></div>}
    {error&&<div className="updateNoticeError">{error}</div>}
    <div className="updateNoticeActions">
      <button className="later" disabled={installing} onClick={onLater}>ОБНОВИТЬ ПОЗЖЕ</button>
      <button className="updateNow" disabled={installing} onClick={async()=>{setError('');setProgress(0);try{await update.install((p:number)=>setProgress(p))}catch(e){setProgress(null);setError(`Не удалось обновить: ${String(e)}`)}}}>{installing?'ОБНОВЛЯЮ…':'ОБНОВИТЬ'}</button>
    </div>
  </aside>
}
function shortUpdateText(body?:string){
  const t=String(body||'Доступна новая версия ENDLUME Studio. Рекомендуется обновить приложение.').trim();
  const first=t.split(/\n+/).filter(Boolean).slice(0,2).join(' • ');
  return first.length>210?first.slice(0,207)+'…':first;
}
function formatUpdateDate(value:any){
  const d=new Date(String(value));
  if(Number.isNaN(d.getTime()))return String(value);
  return new Intl.DateTimeFormat('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric'}).format(d);
}
