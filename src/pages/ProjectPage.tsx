import React, { useCallback, useEffect, useState } from 'react';
import { getCurrentWebviewWindow } from '@tauri-apps/api/webviewWindow';
import { api } from '../tauri';
import { useApp } from '../store';
import type { LoopMode, RenderProject } from '../types';
import { Icon,Range,Toggle } from '../components/ui';

const resolutions=[{w:3840,h:2160,label:'4K UHD'},{w:2560,h:1440,label:'2K QHD'},{w:1920,h:1080,label:'1080P FULL HD'}];
const modes:Array<{id:LoopMode;title:string;subtitle:string;icon:'image'|'crossfade'|'pingpong'|'original'}>=[
  {id:'image',title:'Image',subtitle:'Зацикливание из статичной картинки',icon:'image'},
  {id:'crossfade',title:'Crossfade',subtitle:'Плавный переход между концом и началом',icon:'crossfade'},
  {id:'pingpong',title:'Ping-pong',subtitle:'Прямой ход + обратный ход',icon:'pingpong'},
  {id:'original',title:'Без обработки',subtitle:'Стыковка начала и конца без перехода',icon:'original'}
];

type FeatureFlags={subscribe:boolean;effects:boolean;ambient:boolean};
const featureKey='endlume-feature-flags-v2';
function loadFeatures():FeatureFlags{try{return {...{subscribe:true,effects:true,ambient:true},...JSON.parse(localStorage.getItem(featureKey)||'{}')}}catch{return {subscribe:true,effects:true,ambient:true}}}

export function ProjectPage(){
  const {
    draftProjects,setDraftProjects,invalidProjects,setInvalidProjects,appendProjects,
    settings,patchSettings,effects,subscribes,ambient,setAmbient,openEditor,setPage,setLastRoot
  }=useApp();
  const [busy,setBusy]=useState(false),[scanNote,setScanNote]=useState(''),[features,setFeatures]=useState<FeatureFlags>(loadFeatures);
  const setFeature=(key:keyof FeatureFlags,value:boolean)=>setFeatures(prev=>{const next={...prev,[key]:value};localStorage.setItem(featureKey,JSON.stringify(next));return next});

  const scanRoots=useCallback(async(roots:string[])=>{
    if(busy||!roots.length)return;setBusy(true);setScanNote('');setInvalidProjects([]);
    try{
      const all:any[]=[];const bad:any[]=[];
      for(const root of roots){
        setLastRoot(root);
        try{
          const items=await api.scanRoot(root);
          for(const x of items){
            if(x.valid)all.push({...x,status:'queued',progress:0,stage:'Ожидает добавления в очередь',elapsedSec:0} as RenderProject);
            else bad.push({name:x.name,path:x.path,error:x.error||'Ошибка проекта'});
          }
        }catch(e){bad.push({name:root.split(/[\\/]/).pop()||root,path:root,error:String(e)});}
      }
      const unique=Array.from(new Map(all.map(x=>[x.path,x])).values()) as RenderProject[];
      setDraftProjects(unique);setInvalidProjects(bad);
      setScanNote(`Найдено проектов: ${unique.length}${bad.length?` • ошибок: ${bad.length}`:''}`);
    }catch(e){await api.showError(String(e))}finally{setBusy(false)}
  },[busy,setDraftProjects,setInvalidProjects,setLastRoot]);

  const pick=async()=>{const roots=await api.chooseRoots();await scanRoots(roots)};

  useEffect(()=>{
    let unlisten:(()=>void)|undefined;
    getCurrentWebviewWindow().onDragDropEvent(event=>{
      if(event.payload.type==='drop'&&event.payload.paths?.length){void scanRoots(event.payload.paths)}
    }).then(fn=>{unlisten=fn}).catch(()=>{});
    return()=>unlisten?.();
  },[scanRoots]);

  const enqueue=async()=>{
    if(!draftProjects.length)return;
    if(!settings.outputDir){await api.showError('Сначала выберите папку результата.');return}
    try{
      try{
        const power=await api.powerStatus();
        if(power.supported&&power.onBattery){
          await api.showInfo(`MacBook работает от аккумулятора${power.percent!=null?` (${power.percent}%)`:''}. ENDLUME продолжит рендер на полной мощности — подключите питание, если очередь большая.`);
        }
      }catch{}
      const activeEffects=features.effects?effects.filter(e=>e.enabled):[];
      const activeSubscribes=features.subscribe?subscribes.filter(e=>e.enabled):[];
      const activeAmbient=features.ambient?ambient:undefined;
      await api.enqueue(draftProjects,settings,activeEffects,activeSubscribes,activeAmbient);
      appendProjects(draftProjects.map(p=>({...p,status:'queued',stage:'Ожидает в очереди'})));
      setDraftProjects([]);setInvalidProjects([]);setScanNote('');setPage('render');
    }catch(e){await api.showError(String(e))}
  };

  return <div className="projectColumn">
    <section className="sectionBlock first">
      <div className="sectionTitle">ИСХОДНЫЕ ФАЙЛЫ</div>
      <button className={`dropZone ${busy?'busy':''}`} onClick={pick}>
        <span className="folderRound"><Icon name="folder"/></span>
        <b>{busy?'Сканирую папки…':'Перетащите папки с файлами или нажмите для выбора'}</b>
        <small>{draftProjects.length?`${draftProjects.length} проектов готовы к добавлению в очередь`:'Можно выбрать корневую папку с любым количеством вложенных проектов'}</small>
        <span className="dropStats">{scanNote||'Картинки • Видео • Аудио • Подпапки'}</span>
      </button>
      {invalidProjects.length>0&&<div className="validationBox"><b>Не приняты:</b>{invalidProjects.slice(0,8).map(x=><div key={x.path}><strong>{x.name}</strong> — {x.error}</div>)}{invalidProjects.length>8&&<small>и ещё {invalidProjects.length-8}</small>}</div>}
    </section>

    <section className="sectionBlock">
      <div className="sectionTitle">РЕЖИМ ЗАЦИКЛИВАНИЯ</div>
      <div className="modeGrid">{modes.map(m=><button key={m.id} className={`modeCard ${settings.loopMode===m.id?'selected':''}`} onClick={()=>patchSettings({loopMode:m.id})}>
        <span className="modeVisual"><Icon name={m.icon}/></span><span><b>{m.title}</b><small>{m.subtitle}</small></span>
      </button>)}</div>
    </section>

    <section className="sectionBlock">
      <div className="sectionTitle">ПАРАМЕТРЫ РЕНДЕРА</div>
      <div className="renderCard">
        <div className="optionGroup"><span>Разрешение</span><div className="chipRow">{resolutions.map(r=><button key={r.w} className={settings.width===r.w?'selected':''} onClick={()=>patchSettings({width:r.w,height:r.h})}>{r.label}</button>)}</div></div>
        <div className="optionGroup"><span>FPS</span><div className="chipRow">{[24,30,60].map(v=><button key={v} className={settings.fps===v?'selected':''} onClick={()=>patchSettings({fps:v as 24|30|60})}>{v}</button>)}</div></div>
        <div className="optionGroup"><span>Кодек</span><div className="chipRow"><button className={settings.codec==='h264'?'selected':''} onClick={()=>patchSettings({codec:'h264'})}>H.264</button><button className={settings.codec==='h265'?'selected':''} onClick={()=>patchSettings({codec:'h265'})}>H.265</button></div></div>
        <div className="optionGroup"><span>Пресет</span><div className="chipRow">{(['ultrafast','superfast','fast','medium'] as const).map(v=><button key={v} className={settings.preset===v?'selected':''} onClick={()=>patchSettings({preset:v})}>{v.toUpperCase()}</button>)}</div></div>

        <div className="bigControl"><div><b>Длительность</b><small>Целевое время финального видео</small></div><div className="bigValue">{settings.durationHours} ч</div><Range value={settings.durationHours} min={.5} max={12} step={.5} onChange={v=>patchSettings({durationHours:v})} minLabel="0.5 ч" maxLabel="12 ч"/></div>
        <div className="durationPresets">{[1,1.5,2,3,4,8,10,12].map(v=><button className={settings.durationHours===v?'selected':''} key={v} onClick={()=>patchSettings({durationHours:v})}>{v}ч</button>)}</div>
        <div className="bigControl"><div><b>Битрейт</b><small>Для видео/эффектов. У проектов с одной картинкой Smart Size автоматически уменьшает размер без повторного многочасового кодирования.</small></div><div className="bigValue">{settings.bitrateMbps} Мбит/с</div><Range value={settings.bitrateMbps} min={1} max={100} onChange={v=>patchSettings({bitrateMbps:v})} minLabel="1 Мбит/с" maxLabel="100 Мбит/с"/></div>
        <div className="bigControl compactControl"><div><b>Кроссфейд между треками</b><small>Плавный переход без резкого стыка</small></div><div className="bigValue small">{settings.crossfadeSec} сек</div><Range value={settings.crossfadeSec} min={1} max={10} onChange={v=>patchSettings({crossfadeSec:v})} minLabel="1 сек" maxLabel="10 сек"/></div>

        <div className="toggles">
          <Toggle checked={settings.normalizeLufs} onChange={v=>patchSettings({normalizeLufs:v})} label="Нормализация звука до -14 LUFS"/>
          <Toggle checked={settings.durationMode==='whole-track'} onChange={v=>patchSettings({durationMode:v?'whole-track':'exact'})} label="Не обрезать последнюю песню" help="ENDLUME может увеличить итог на несколько минут, чтобы композиция закончилась естественно"/>
          <Toggle checked={settings.encoderPreference==='auto'} onChange={v=>patchSettings({encoderPreference:v?'auto':'quality'})} label="Автовыбор самого быстрого движка" help="NVENC / QSV / AMF / Apple VideoToolbox / CPU"/>
        </div>
      </div>
    </section>

    <section className="sectionBlock">
      <div className="sectionTitle">КНОПКА SUBSCRIBE</div>
      <div className="featureRow"><span className="featureIcon pink"><Icon name="subscribe"/></span><div><b>Subscribe Button</b><small>{!features.subscribe?'Отключено для текущих рендеров':subscribes.filter(s=>s.enabled).length?`Активно пресетов: ${subscribes.filter(s=>s.enabled).length}`:'Не настроено'}</small></div><div className="rowButtons"><button onClick={()=>setFeature('subscribe',!features.subscribe)}>{features.subscribe?'ВЫКЛЮЧИТЬ':'ВКЛЮЧИТЬ'}</button><button onClick={()=>openEditor({kind:'subscribe'})}>НАСТРОИТЬ →</button></div></div>
    </section>

    <section className="sectionBlock">
      <div className="sectionTitle">ЭФФЕКТЫ</div>
      <div className="featureRow"><span className="featureIcon blue"><Icon name="effects"/></span><div><b>Набор эффектов поверх видео</b><small>{!features.effects?'Отключено для текущих рендеров':effects.filter(e=>e.enabled).length?`Активно: ${effects.filter(e=>e.enabled).length} • сохранено: ${effects.length}`:'Эффекты не выбраны'}</small></div><div className="rowButtons"><button onClick={()=>setFeature('effects',!features.effects)}>{features.effects?'ВЫКЛЮЧИТЬ':'ВКЛЮЧИТЬ'}</button><button onClick={()=>openEditor({kind:'effects'})}>НАСТРОИТЬ →</button></div></div>
    </section>

    <section className="sectionBlock">
      <div className="sectionTitle">ФОНОВЫЙ ЗВУК</div>
      <div className="featureRow"><span className="featureIcon"><Icon name="ambient"/></span><div><b>Добавить ambient-звук</b><small>{!features.ambient?'Отключено для текущих рендеров':ambient||'Не выбран'}</small></div><div className="rowButtons"><button onClick={()=>setFeature('ambient',!features.ambient)}>{features.ambient?'ВЫКЛЮЧИТЬ':'ВКЛЮЧИТЬ'}</button><button onClick={async()=>{const p=await api.chooseAmbient();if(p)setAmbient(p)}}>ВЫБРАТЬ</button>{ambient&&<button className="dangerText" onClick={()=>setAmbient(undefined)}>УДАЛИТЬ</button>}</div></div>
    </section>

    <section className="sectionBlock outputSection">
      <div className="sectionTitle">ВЫБРАННЫЕ ПАПКИ</div>
      <div className="selectedFolders">{draftProjects.length?draftProjects.slice(0,8).map((p,i)=><div key={p.id}><span>{i+1}</span><b>{p.name}</b><small>{p.audio.length} треков • {p.media.length} медиа</small></div>):<p>Папки ещё не выбраны</p>}{draftProjects.length>8&&<p>+ ещё {draftProjects.length-8} проектов</p>}</div>
      <div className="sectionTitle outputTitle">СОХРАНИТЬ В</div>
      <button className="outputPicker" onClick={async()=>{const p=await api.chooseOutput();if(p)patchSettings({outputDir:p})}}><Icon name="folder"/><b>Нажмите для выбора папки результата</b><small>{settings.outputDir||'Папка не выбрана'}</small></button>
    </section>

    <div className="projectBottom"><span><b>{draftProjects.length}</b> проектов готово к очереди</span><button className="primaryQueue" disabled={!draftProjects.length} onClick={enqueue}>+ ДОБАВИТЬ В ОЧЕРЕДЬ</button></div>
  </div>
}
