import React, { useEffect, useRef, useState } from 'react';
import { listen } from '@tauri-apps/api/event';
import { Topbar } from '../components/shell';
import { RecoveryModal } from '../components/recovery';
import { VyronBatchBridge } from '../components/VyronBatchBridge';
import { useApp } from '../store';
import { api } from '../tauri';
import { watchManagedLicenseRealtime } from '../license-realtime';
import { installMotionRuntime } from '../motion';
import { applyProjectPatch,applyQueueSnapshot } from '../queue-state';
import type { LicenseStatus, RecoveryPayload } from '../types';
import { ProjectPage } from './ProjectPage';
import { RenderPage } from './RenderPage';
import { LibraryPage } from './LibraryPage';
import { SettingsPage } from './SettingsPage';
import { EditorRouter } from './Editors';
import { PostUpdateNotice, StartupSplash, UpdateExperience } from '../components/EndlumeUpdateExperience';
import { LiveCompositePreview, type LivePreviewAssets } from '../components/LiveCompositePreview';

function syncQueueSnapshot(snapshot:any){
  useApp.setState(state=>({projects:applyQueueSnapshot(state.projects,snapshot)}));
}

function compactPayload<T extends Record<string,any>>(value:T):Partial<T>{
  return Object.fromEntries(Object.entries(value||{}).filter(([,v])=>v!==null&&v!==undefined)) as Partial<T>;
}

function syncBackendQueue(snapshot:any){
  const st=useApp.getState();
  const old=new Map(st.projects.map(p=>[p.id,p]));
  const items:any[]=[];
  const push=(job:any,status:'rendering'|'queued')=>{
    const project=job?.project;if(!project?.id)return;const prev=old.get(project.id);
    items.push({...project,status,progress:status==='rendering'?(prev?.progress||0):0,stage:status==='rendering'?(prev?.stage||'Восстанавливаю текущий этап…'):'Ожидает в очереди',elapsedSec:prev?.elapsedSec||0,startedAt:prev?.startedAt,etaSec:prev?.etaSec,encoder:prev?.encoder,engineTimings:prev?.engineTimings});
  };
  if(snapshot?.active)push(snapshot.active,'rendering');
  for(const job of snapshot?.pending||[])push(job,'queued');
  st.syncQueueProjects(items);
}

export function App(){
  const page=useApp(s=>s.page),editor=useApp(s=>s.editor),patchProject=useApp(s=>s.patchProject),setLibrary=useApp(s=>s.setLibrary),appendProjects=useApp(s=>s.appendProjects),queueDepth=useApp(s=>s.projects.filter(p=>p.status==='queued'||p.status==='rendering').length);
  const [recovery,setRecovery]=useState<RecoveryPayload>();
  const [license,setLicense]=useState<LicenseStatus|null>(null);
  const [availableUpdate,setAvailableUpdate]=useState<any>(null);
  const [postUpdateVersion,setPostUpdateVersion]=useState<string>();
  const [startupMinElapsed,setStartupMinElapsed]=useState(false);
  const [frontendPreviewFixture,setFrontendPreviewFixture]=useState<any|null|undefined>(undefined);
  const snoozeUntil=useRef(0),checkingUpdate=useRef(false),lastUpdateCheck=useRef(0);

  useEffect(()=>installMotionRuntime(),[]);
  useEffect(()=>{api.previewFrontendFixture().then(v=>setFrontendPreviewFixture(v??null)).catch(()=>setFrontendPreviewFixture(null))},[]);
  useEffect(()=>{const timer=window.setTimeout(()=>setStartupMinElapsed(true),1150);return()=>window.clearTimeout(timer)},[]);

  useEffect(()=>{
    let disposed=false,updateTimer:number|undefined,updateInterval:number|undefined;
    api.license().then(setLicense).catch(()=>setLicense({valid:false}));
    api.loadLibrary().then(setLibrary).catch(()=>setLibrary({effects:[],subscribes:[]}));
    api.loadRecovery().then(r=>{if(r?.interrupted)setRecovery(r)}).catch(()=>{});
    api.queueSnapshot().then(syncBackendQueue).catch(()=>{});
    api.queueSnapshot().then(syncQueueSnapshot).catch(()=>{});

    const checkForUpdate=async(force=false)=>{
      if(disposed||checkingUpdate.current)return;
      const now=Date.now();
      if(!force&&now<snoozeUntil.current)return;
      checkingUpdate.current=true;lastUpdateCheck.current=now;
      try{
        const u=await api.checkUpdate();
        if(disposed)return;
        if(u?.version)setAvailableUpdate((prev:any)=>prev?.version===u.version?prev:u);
        else if(force)setAvailableUpdate(null);
      }catch{}finally{checkingUpdate.current=false}
    };

    const startUpdateWatcher=()=>{
      updateTimer=window.setTimeout(()=>checkForUpdate(true),1800);
      updateInterval=window.setInterval(()=>checkForUpdate(false),5*60*1000);
    };

    api.cleanupDuplicateApps(false).then(async status=>{
      if(disposed)return;
      if(status.supported&&status.canonicalInstall===false&&status.currentPath&&!status.currentPath.startsWith('/Volumes/')){
        await api.normalizeAppName().catch(()=>{});
        return;
      }
      if(status.supported&&!status.singleApp){await api.cleanupDuplicateApps(true).catch(()=>{})}
      if(!disposed)startUpdateWatcher();
    }).catch(()=>{if(!disposed)startUpdateWatcher()});

    const onFocus=()=>{if(Date.now()-lastUpdateCheck.current>60_000)checkForUpdate(false)};
    const onVisibility=()=>{if(document.visibilityState==='visible'&&Date.now()-lastUpdateCheck.current>60_000)checkForUpdate(false)};
    const onManualUpdate=(event:Event)=>{const detail=(event as CustomEvent<any>).detail;if(detail?.version)setAvailableUpdate(detail)};
    window.addEventListener('focus',onFocus);document.addEventListener('visibilitychange',onVisibility);window.addEventListener('endlume-update-found',onManualUpdate as EventListener);

    const progressPending=new Map<string,any>();let progressRaf:number|undefined;
    const flushRenderProgress=()=>{
      progressRaf=undefined;if(progressPending.size===0)return;
      const batch=new Map(progressPending);progressPending.clear();
      useApp.setState(state=>{
        let projects:any[]=state.projects;
        for(const next of batch.values())projects=applyProjectPatch(projects,next.id,compactPayload(next));
        return {projects};
      });
    };
    const off:Promise<()=>void>[]=[];
    off.push(listen<any>('queue-changed',e=>syncQueueSnapshot(e.payload)));
    off.push(listen<LicenseStatus>('license-state-changed',e=>setLicense(e.payload)));
    off.push(listen<any>('render-progress',e=>{const p=e.payload;if(!p?.id)return;progressPending.set(p.id,p);if(progressRaf===undefined)progressRaf=requestAnimationFrame(flushRenderProgress)}));
    off.push(listen<any>('render-done',e=>{const p=e.payload;if(!p?.id)return;progressPending.delete(p.id);patchProject(p.id,{...compactPayload(p),status:'done',progress:100,stage:'Готово',etaSec:0})}));
    off.push(listen<any>('render-error',e=>{const p=e.payload;if(!p?.id)return;progressPending.delete(p.id);patchProject(p.id,{...compactPayload(p),status:'error',progress:100,etaSec:0})}));
    off.push(listen<any>('queue-recovered',e=>{const p=(e.payload?.projects||[]).map((x:any)=>({...x,status:'queued',progress:0,stage:'Восстановлено после сбоя',elapsedSec:0}));appendProjects(p)}));
    off.push(listen<any>('engine-timing',e=>{const {id,key,seconds}=e.payload||{};if(id&&key)patchProject(id,{engineTimings:{...(useApp.getState().projects.find(p=>p.id===id)?.engineTimings||{}),[key]:seconds}})}));
    off.push(listen<any>('engine-profile',e=>{const {id,...rest}=e.payload||{};if(id)patchProject(id,compactPayload(rest))}));
    off.push(listen<any>('cache-updated',e=>{const {id,cacheKey,cacheReady}=e.payload||{};if(!id)return;const st=useApp.getState();const effects=st.effects.map(x=>x.id===id?{...x,cacheKey,cacheReady}:x);const subscribes=st.subscribes.map(x=>x.id===id?{...x,cacheKey,cacheReady}:x);st.setEffects(effects);st.setSubscribes(subscribes);api.saveLibrary({effects,subscribes,ambient:st.ambient}).catch(()=>{});}));
    return()=>{
      disposed=true;if(updateTimer)window.clearTimeout(updateTimer);if(updateInterval)window.clearInterval(updateInterval);if(progressRaf!==undefined)cancelAnimationFrame(progressRaf);progressPending.clear();
      window.removeEventListener('focus',onFocus);document.removeEventListener('visibilitychange',onVisibility);window.removeEventListener('endlume-update-found',onManualUpdate as EventListener);off.forEach(p=>p.then(f=>f()));
    }
  },[]);


  useEffect(()=>{
    if(!license?.valid)return;
    const screen=editor?`editor:${editor.kind}`:`page:${page}`;
    api.setLicenseScreen(screen).catch(()=>{});
  },[license?.valid,page,editor?.kind]);

  useEffect(()=>{
    if(!license?.valid)return;
    api.setLicenseQueueDepth(queueDepth).catch(()=>{});
  },[license?.valid,queueDepth]);

  useEffect(()=>{
    if(!license)return;
    return watchManagedLicenseRealtime(license,()=>{api.license().then(setLicense).catch(()=>{});});
  },[license?.valid,license?.realtimeTopic]);

  useEffect(()=>{
    if(!license?.valid)return;
    api.appVersion().then(version=>{
      const key='endlume-last-seen-version';
      const seen=window.localStorage.getItem(key);
      // Fresh installs must not look like they have just completed an update.
      if(seen===null){window.localStorage.setItem(key,version);return}
      if(seen!==version)setPostUpdateVersion(version);
    }).catch(()=>{});
  },[license?.valid]);

  if(frontendPreviewFixture)return <FrontendPreviewHarness fixture={frontendPreviewFixture}/>;
    if(!startupMinElapsed||!license)return <StartupSplash/>;
  if(!license.valid)return <ActivationScreen onActivated={setLicense}/>;

  const pageView=page==='project'?<ProjectPage/>:page==='render'?<RenderPage/>:page==='library'?<LibraryPage/>:<SettingsPage/>;
  return <div className="appShell"><VyronBatchBridge/><Topbar/><div className="content"><div key={page} className="pageScene">{pageView}</div></div>{editor&&<EditorRouter/>}{recovery&&<RecoveryModal data={recovery} onClose={()=>setRecovery(undefined)}/>} {availableUpdate&&<UpdateExperience update={availableUpdate} onLater={()=>{snoozeUntil.current=Date.now()+60*60*1000;setAvailableUpdate(null)}}/>}{postUpdateVersion&&<PostUpdateNotice version={postUpdateVersion} onClose={()=>{window.localStorage.setItem('endlume-last-seen-version',postUpdateVersion);setPostUpdateVersion(undefined)}}/>}</div>
}

function ActivationScreen({onActivated}:{onActivated:(v:LicenseStatus)=>void}){
  const [key,setKey]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const windows=api.isWindows();
  const product='ENDLUME YT Studio PEISOV';
  return <div className="activationScreen"><div className="activationCard"><div className="activationBrand"><span className="activationInfinity">∞</span><div><b>ENDLUME</b><small>YT STUDIO PEISOV</small></div></div><h1>Активация {product}</h1><p>Для запуска введите ключ лицензии. После активации рендер работает локально; при временном отсутствии сети действует ограниченный offline grace.</p><input autoFocus placeholder="ENDLUME-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX" value={key} onChange={e=>setKey(e.target.value)} onKeyDown={e=>e.key==='Enter'&&document.getElementById('activate')?.click()}/>{error&&<div className="activationError">{error}</div>}<button id="activate" disabled={busy||!key.trim()} onClick={async()=>{setBusy(true);setError('');try{onActivated(await api.activate(key))}catch(e){setError(String(e))}finally{setBusy(false)}}}>{busy?'ПРОВЕРЯЮ КЛЮЧ…':'АКТИВИРОВАТЬ →'}</button><small className="activationFoot">ENDLUME YT Studio PEISOV • {windows?'Windows x64':'macOS Apple Silicon'}</small></div></div>
}

function FrontendPreviewHarness({fixture}:{fixture:any}){
  const overlayRef=useRef<HTMLDivElement>(null);
  const reported=useRef(false);
  const effect=fixture.effect;
  const assets:LivePreviewAssets={
    basePath:api.previewUrl(String(fixture.basePath)),
    baseFilePath:String(fixture.basePath),
    baseKind:fixture.baseKind==='video'?'video':'image',
    overlayPath:api.previewUrl(String(fixture.overlayPath)),
    overlayFilePath:String(fixture.overlayPath),
    baseBytes:Number(fixture.baseBytes||0),
    overlayBytes:Number(fixture.overlayBytes||0),
    requestId:String(fixture.requestId||'frontend-e2e'),
    previewType:fixture.previewType==='Subscribe'?'Subscribe':'Effects',
  };
  const overlayStyle:React.CSSProperties=effect.fullscreen?{left:'0%',top:'0%',width:'100%',height:'100%',transform:'none'}:{
    left:`${Number(effect.x||0.5)*100}%`,
    top:`${Number(effect.y||0.5)*100}%`,
    width:`${Math.max(5,Number(effect.scale||0.32)*100)}%`,
    transform:'translate(-50%, -50%)',
  };
  return <div style={{position:'fixed',inset:0,background:'#05070d'}}>
    <LiveCompositePreview assets={assets} effect={effect} active={true} busy={false} overlayRef={overlayRef} overlayStyle={overlayStyle}
      onDragStart={()=>{}} onResizeStart={()=>{}} onPickColor={()=>{}}
      onFrameState={payload=>{if(reported.current)return;reported.current=true;void api.previewFrontendReport({...payload,PREVIEW_APPLIED:payload.status==='GREEN',IMAGE_LOAD:payload.status,IMAGE_NATURAL_WIDTH:payload.width,IMAGE_NATURAL_HEIGHT:payload.height,FRONTEND_PAYLOAD_BYTES:payload.payloadBytes})}}/>
  </div>;
}

