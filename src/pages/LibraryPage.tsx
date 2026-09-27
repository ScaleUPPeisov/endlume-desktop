import React, { useRef, useState } from 'react';
import { useApp } from '../store';
import { api } from '../tauri';
import { Icon } from '../components/ui';

type Tab='effects'|'subscribe'|'ambient'|'presets';
export function LibraryPage(){
  const [tab,setTab]=useState<Tab>('effects');
  const effects=useApp(s=>s.effects),subscribes=useApp(s=>s.subscribes),ambient=useApp(s=>s.ambient),setAmbient=useApp(s=>s.setAmbient),openEditor=useApp(s=>s.openEditor);
  return <div className="simplePage"><div className="simpleHeader"><div><small>ПОСТОЯННАЯ БИБЛИОТЕКА</small><h1>Библиотека</h1><p>Загруженные материалы и presets сохраняются между запусками ENDLUME.</p></div></div><div className="libraryTabs">{(['effects','subscribe','ambient','presets'] as Tab[]).map(t=><button key={t} className={tab===t?'active':''} onClick={()=>setTab(t)}>{t==='effects'?'Effects':t==='subscribe'?'Subscribe':t==='ambient'?'Ambient':'Presets'}</button>)}</div>
    {tab==='effects'&&<><div className="libraryTools"><b>{effects.length} эффектов</b><span className="libraryCacheSummary"><i className="ready"/>{effects.filter(e=>e.cacheReady).length} кэшировано <i/>{effects.filter(e=>!e.cacheReady).length} ждут</span><button onClick={()=>openEditor({kind:'effects'})}>+ ДОБАВИТЬ / НАСТРОИТЬ</button></div><div className="libraryCards">{effects.map(e=><button className="libraryAsset" onClick={()=>openEditor({kind:'effects',id:e.id})} key={e.id}><LibraryVideo source={e.source} tone="blue"/><b>{e.name}</b><small>{e.mode} • {e.enabled?'включён':'выключен'}</small><em className={e.cacheReady?'ready':'waiting'}>{e.cacheReady?'● КЭШ ГОТОВ':'○ КЭШ ПОДГОТОВИТСЯ ПРИ РЕНДЕРЕ'}</em></button>)}{!effects.length&&<Empty text="Эффекты ещё не добавлены"/>}</div></>}
    {tab==='subscribe'&&<><div className="libraryTools"><b>{subscribes.length} Subscribe presets</b><span className="libraryCacheSummary"><i className="ready"/>{subscribes.filter(e=>e.cacheReady).length} кэшировано <i/>{subscribes.filter(e=>!e.cacheReady).length} ждут</span><button onClick={()=>openEditor({kind:'subscribe'})}>+ ДОБАВИТЬ / НАСТРОИТЬ</button></div><div className="libraryCards">{subscribes.map(e=><button className="libraryAsset" onClick={()=>openEditor({kind:'subscribe',id:e.id})} key={e.id}><LibraryVideo source={e.source} tone="pink"/><b>{e.name}</b><small>первое {Math.round(e.firstAtSec)}с • каждые {Math.round(e.repeatEverySec/60)} мин</small><em className={e.cacheReady?'ready':'waiting'}>{e.cacheReady?'● КЭШ ГОТОВ':'○ КЭШ ПОДГОТОВИТСЯ ПРИ РЕНДЕРЕ'}</em></button>)}{!subscribes.length&&<Empty text="Subscribe presets ещё не добавлены"/>}</div></>}
    {tab==='ambient'&&<div className="ambientLibrary"><span className="featureIcon"><Icon name="ambient"/></span><div><b>{ambient?'Ambient сохранён':'Ambient не выбран'}</b><p>{ambient||'Добавьте один фоновый звук. Его можно удалить в любой момент.'}</p></div><button onClick={async()=>{const p=await api.chooseAmbient();if(p){setAmbient(p);await api.saveLibrary({effects,subscribes,ambient:p})}}}>ВЫБРАТЬ</button>{ambient&&<button onClick={async()=>{setAmbient(undefined);await api.saveLibrary({effects,subscribes,ambient:undefined})}}>УДАЛИТЬ</button>}</div>}
    {tab==='presets'&&<div className="presetInfo"><Icon name="save"/><h3>Presets Effects и Subscribe</h3><p>Сохранённые настройки находятся внутри соответствующих библиотек. Профили каналов специально не добавляются — ENDLUME рассчитана на большое количество новых каналов.</p></div>}
  </div>
}
function LibraryVideo({source,tone}:{source:string;tone:'blue'|'pink'}){
  const ref=useRef<HTMLVideoElement>(null);
  const play=()=>{const video=ref.current;if(video){video.muted=true;void video.play().catch(()=>{})}};
  const reset=()=>{const video=ref.current;if(video){video.pause();try{video.currentTime=0}catch{}}};
  return <span className={`libraryThumb media ${tone}`} onMouseEnter={play} onMouseLeave={reset}>
    {source?<video ref={ref} src={api.previewUrl(source)} muted loop playsInline preload="metadata"/>:<Icon name={tone==='pink'?'subscribe':'effects'}/>}
    <i className="libraryPlay">▶ HOVER PREVIEW</i>
  </span>
}
function Empty({text}:{text:string}){return <div className="libraryEmpty"><Icon name="library"/><b>{text}</b></div>}