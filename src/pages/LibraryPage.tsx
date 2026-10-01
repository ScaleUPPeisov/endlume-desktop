import React, { useState } from 'react';
import { useApp } from '../store';
import { api } from '../tauri';
import { Icon } from '../components/ui';

type Tab='effects'|'subscribe'|'ambient'|'presets';
export function LibraryPage(){
  const [tab,setTab]=useState<Tab>('effects');
  const effects=useApp(s=>s.effects),subscribes=useApp(s=>s.subscribes),ambient=useApp(s=>s.ambient),setAmbient=useApp(s=>s.setAmbient),openEditor=useApp(s=>s.openEditor);
  return <div className="simplePage"><div className="simpleHeader"><div><small>ПОСТОЯННАЯ БИБЛИОТЕКА</small><h1>Библиотека</h1><p>Загруженные материалы и presets сохраняются между запусками ENDLUME.</p></div></div><div className="libraryTabs">{(['effects','subscribe','ambient','presets'] as Tab[]).map(t=><button key={t} className={tab===t?'active':''} onClick={()=>setTab(t)}>{t==='effects'?'Effects':t==='subscribe'?'Subscribe':t==='ambient'?'Background Music':'Presets'}</button>)}</div>
    {tab==='effects'&&<><div className="libraryTools"><b>{effects.length} эффектов</b><button onClick={()=>openEditor({kind:'effects'})}>+ ДОБАВИТЬ / НАСТРОИТЬ</button></div><div className="libraryCards">{effects.map(e=><button className="libraryAsset" onClick={()=>openEditor({kind:'effects',id:e.id})} key={e.id}><span className="libraryThumb"><Icon name="effects"/></span><b>{e.name}</b><small>{e.mode}</small><em className={e.cacheReady?'ready':'waiting'}>{e.cacheReady?'КЭШ ГОТОВ':'КЭШ ПОСЛЕ 1-ГО РЕНДЕРА'}</em></button>)}{!effects.length&&<Empty text="Эффекты ещё не добавлены"/>}</div></>}
    {tab==='subscribe'&&<><div className="libraryTools"><b>{subscribes.length} Subscribe presets</b><button onClick={()=>openEditor({kind:'subscribe'})}>+ ДОБАВИТЬ / НАСТРОИТЬ</button></div><div className="libraryCards">{subscribes.map(e=><button className="libraryAsset" onClick={()=>openEditor({kind:'subscribe',id:e.id})} key={e.id}><span className="libraryThumb pink"><Icon name="subscribe"/></span><b>{e.name}</b><small>каждые {Math.round(e.repeatEverySec/60)} мин</small><em className={e.cacheReady?'ready':'waiting'}>{e.cacheReady?'КЭШ ГОТОВ':'КЭШ ПОСЛЕ 1-ГО РЕНДЕРА'}</em></button>)}{!subscribes.length&&<Empty text="Subscribe presets ещё не добавлены"/>}</div></>}
    {tab==='ambient'&&<div className="ambientLibrary"><span className="featureIcon"><Icon name="ambient"/></span><div><b>{ambient?'Background Music сохранена':'Background Music не выбрана'}</b><p>{ambient||'Добавьте фоновую музыку. Её можно удалить в любой момент.'}</p></div><button onClick={async()=>{const p=await api.chooseAmbient();if(p){setAmbient(p);await api.saveLibrary({effects,subscribes,ambient:p})}}}>ВЫБРАТЬ</button>{ambient&&<button onClick={async()=>{setAmbient(undefined);await api.saveLibrary({effects,subscribes,ambient:undefined})}}>УДАЛИТЬ</button>}</div>}
    {tab==='presets'&&<div className="presetInfo"><Icon name="save"/><h3>Presets Effects и Subscribe</h3><p>Сохранённые настройки находятся внутри соответствующих библиотек. Профили каналов специально не добавляются — ENDLUME рассчитана на большое количество новых каналов.</p></div>}
  </div>
}
function Empty({text}:{text:string}){return <div className="libraryEmpty"><Icon name="library"/><b>{text}</b></div>}
