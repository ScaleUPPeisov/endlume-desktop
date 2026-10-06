import React, { useCallback, useEffect, useRef, useState } from 'react';
import { getCurrentWebviewWindow } from '@tauri-apps/api/webviewWindow';
import { api } from '../tauri';
import { useApp } from '../store';
import type { EffectPreset, LoopMode, RenderProject } from '../types';
import { Icon,Range,Toggle } from '../components/ui';

const resolutions=[{w:1920,h:1080,label:'1080P FULL HD'},{w:2560,h:1440,label:'2K QHD'},{w:3840,h:2160,label:'4K UHD'}];
const modes:Array<{id:LoopMode;title:string;subtitle:string;icon:'image'|'crossfade'|'pingpong'|'original'}>=[
  {id:'image',title:'Image',subtitle:'Зацикливание из статичной картинки',icon:'image'},
  {id:'crossfade',title:'Crossfade',subtitle:'Плавный переход между концом и началом',icon:'crossfade'},
  {id:'pingpong',title:'Ping-pong',subtitle:'Прямой ход + обратный ход',icon:'pingpong'},
  {id:'original',title:'Без обработки',subtitle:'Стыковка начала и конца без перехода',icon:'original'}
];

type FeatureFlags={subscribe:boolean;effects:boolean;ambient:boolean};
const featureKey='endlume-feature-flags-v2';
function loadFeatures():FeatureFlags{try{return {...{subscribe:true,effects:true,ambient:true},...JSON.parse(localStorage.getItem(featureKey)||'{}')}}catch{return {subscribe:true,effects:true,ambient:true}}}
const NO_EFFECT_SELECTION='__none__';
const imageExt=new Set(['jpg','jpeg','png','webp','bmp','tif','tiff','heic','avif']);
function isImagePath(path:string){const clean=path.split(/[?#]/)[0]||'';const ext=clean.includes('.')?clean.split('.').pop()?.toLowerCase()||'':'';return imageExt.has(ext)}
function effectNeedsRepair(effect:EffectPreset){return effect.assetState==='repair-required'||!effect.source?.trim()}
function effectIsSelectable(effect:EffectPreset){return effect.enabled&&effect.usageMode!=='off'&&!effectNeedsRepair(effect)}
function effectStatusLabel(effect:EffectPreset){
  if(effectNeedsRepair(effect))return '⚠ REPAIR REQUIRED';
  if(!effect.enabled||effect.usageMode==='off')return 'ВЫКЛЮЧЕН';
  return 'ГОТОВ';
}

export function ProjectPage(){
  const {
    draftProjects,setDraftProjects,invalidProjects,setInvalidProjects,appendProjects,
    settings,patchSettings,effects,subscribes,ambient,setAmbient,ambientSettings,patchAmbientSettings,openEditor,setPage,setLastRoot,setPreviewProjectPath,
    selectedEffectByPath,setSelectedEffectForProject
  }=useApp();
  const [busy,setBusy]=useState(false),[scanNote,setScanNote]=useState(''),[features,setFeatures]=useState<FeatureFlags>(loadFeatures);
  const librarySaveQueue=useRef<Promise<void>>(Promise.resolve());
  const setFeature=(key:keyof FeatureFlags,value:boolean)=>setFeatures(prev=>{const next={...prev,[key]:value};localStorage.setItem(featureKey,JSON.stringify(next));return next});
  const selectableEffects=effects.filter(effectIsSelectable);
  const repairRequiredEffects=effects.filter(effectNeedsRepair);
  const effectIdCounts=effects.reduce<Record<string,number>>((acc,e)=>{const id=e.id.trim();if(id)acc[id]=(acc[id]||0)+1;return acc},{});
  const duplicateEffectIds=Object.entries(effectIdCounts).filter(([,count])=>count>1).map(([id])=>id);
  const selectedEffectIdForPath=(path:string)=>selectedEffectByPath[path]||'';
  const selectionIssueForPath=(path:string)=>{
    const selectedId=selectedEffectIdForPath(path);
    if(!selectedId||selectedId===NO_EFFECT_SELECTION)return '';
    const effect=effects.find(item=>item.id===selectedId);
    if(!effect)return `Сохранённый effect ID ${selectedId} больше не существует после migration. ENDLUME не будет угадывать замену — выберите эффект заново.`;
    if(effectNeedsRepair(effect))return `${effect.name}: ${effect.assetError||'файл эффекта недоступен; требуется восстановить источник.'}`;
    if(!effect.enabled||effect.usageMode==='off')return `${effect.name}: эффект выключен. Включите его или выберите другой.`;
    return '';
  };
  const persistCurrentLibrary=()=>{
    librarySaveQueue.current=librarySaveQueue.current.catch(()=>undefined).then(()=>{
      const state=useApp.getState();
      return api.saveLibrary({effects:state.effects,subscribes:state.subscribes,ambient:state.ambient,ambientSettings:state.ambientSettings});
    });
    return librarySaveQueue.current;
  };
  const saveAmbient=async(next?:string)=>{setAmbient(next);await persistCurrentLibrary();};
  const saveAmbientSettings=async(patch:Partial<typeof ambientSettings>)=>{patchAmbientSettings(patch);await persistCurrentLibrary();};
  const repairEffectSource=async(effect:EffectPreset)=>{
    const source=await api.chooseVideo('effects');
    if(!source)return;
    const previous=effects;
    const next=effects.map(item=>item.id===effect.id?{...item,source,assetState:'ready' as const,assetError:undefined,cacheReady:false,cacheKey:undefined}:item);
    useApp.getState().setEffects(next);
    const state=useApp.getState();
    try{
      await api.saveLibrary({effects:next,subscribes:state.subscribes,ambient:state.ambient,ambientSettings:state.ambientSettings});
    }catch(error){
      useApp.getState().setEffects(previous);
      await api.showError(`Не удалось сохранить восстановленный файл эффекта.\n${String(error)}`);
    }
  };

  const scanRoots=useCallback(async(roots:string[])=>{
    if(busy||!roots.length)return;setBusy(true);setScanNote('');setInvalidProjects([]);setDraftProjects([]);setPreviewProjectPath(undefined);
    try{
      const all:any[]=[];const bad:any[]=[];const savedAnchors=useApp.getState().sceneAnchorsByPath;
      for(const root of roots){
        setLastRoot(root);
        try{
          const items=await api.scanRoot(root);
          for(const x of items){
            if(x.valid)all.push({...x,anchors:savedAnchors[x.path]||x.anchors,status:'queued',progress:0,stage:'Ожидает добавления в очередь',elapsedSec:0} as RenderProject);
            else bad.push({name:x.name,path:x.path,error:x.error||'Ошибка проекта'});
          }
        }catch(e){bad.push({name:root.split(/[\\/]/).pop()||root,path:root,error:String(e)});}
      }
      const unique=Array.from(new Map(all.map(x=>[x.path,x])).values()) as RenderProject[];
      setDraftProjects(unique);setPreviewProjectPath(unique[0]?.path);setInvalidProjects(bad);
      setScanNote(`Найдено проектов: ${unique.length}${bad.length?` • ошибок: ${bad.length}`:''}`);
    }catch(e){await api.showError(String(e))}finally{setBusy(false)}
  },[busy,setDraftProjects,setInvalidProjects,setLastRoot,setPreviewProjectPath]);

  const pick=async()=>{const roots=await api.chooseRoots();await scanRoots(roots)};

  useEffect(()=>{
    let unlisten:(()=>void)|undefined;
    getCurrentWebviewWindow().onDragDropEvent(event=>{if(event.payload.type==='drop'&&event.payload.paths?.length){void scanRoots(event.payload.paths)}}).then(fn=>{unlisten=fn}).catch(()=>{});
    return()=>unlisten?.();
  },[scanRoots]);

  const enqueue=async()=>{
    if(!draftProjects.length)return;
    if(!settings.outputDir){await api.showError('Сначала выберите папку результата.');return}
    try{
      try{const power=await api.powerStatus();if(power.supported&&power.onBattery){await api.showInfo(`MacBook работает от аккумулятора${power.percent!=null?` (${power.percent}%)`:''}. ENDLUME продолжит рендер на полной мощности — подключите питание, если очередь большая.`);}}catch{}
      const effectRegistry=features.effects?selectableEffects:[];
      if(features.effects&&duplicateEffectIds.length){throw new Error(`Effects registry повреждён: повторяются ID ${duplicateEffectIds.join(', ')}. ENDLUME не будет угадывать или рендерить не тот эффект.`);}
      const activeSubscribes=features.subscribe?subscribes.filter(e=>e.enabled):[];
      const activeAmbient=features.ambient?ambient:undefined;
      const resolved=draftProjects.map(project=>{
        if(!features.effects)return {project,selectedEffect:undefined};
        const selectedId=selectedEffectIdForPath(project.path);
        if(!selectedId){throw new Error(`Выберите эффект для проекта «${project.name}» или явно укажите «Без эффекта».`);}
        if(selectedId===NO_EFFECT_SELECTION)return {project,selectedEffect:undefined};
        const persistedEffect=effects.find(effect=>effect.id===selectedId);
        if(!persistedEffect){throw new Error(`Сохранённый effect ID ${selectedId} для проекта «${project.name}» больше не существует. Возможна migration старого duplicate ID. ENDLUME не будет угадывать замену — выберите эффект заново.`);}
        if(effectNeedsRepair(persistedEffect)){throw new Error(`Эффект «${persistedEffect.name}» (${persistedEffect.id}) требует восстановления файла. ${persistedEffect.assetError||'Выберите исходный файл заново в настройках Effects.'}`);}
        if(!persistedEffect.enabled||persistedEffect.usageMode==='off'){throw new Error(`Эффект «${persistedEffect.name}» (${persistedEffect.id}) выключен. Включите его или выберите другой эффект.`);}
        const selectedEffect=effectRegistry.find(effect=>effect.id===selectedId);
        if(!selectedEffect){throw new Error(`Эффект ${selectedId} для проекта «${project.name}» недоступен. ENDLUME не будет подставлять другой эффект.`);}
        return {project,selectedEffect};
      });
      const fastStaticProjects=resolved.filter(({project,selectedEffect})=>project.media.length>0&&project.media.every(isImagePath)&&(project.media.length===1||(!selectedEffect&&activeSubscribes.length===0)));
      if(fastStaticProjects.length&&(settings.crossfadeSec>0||settings.normalizeLufs||!!activeAmbient)){
        await api.showInfo(`Processed Audio включён для ${fastStaticProjects.length} статичных проектов. Быстрый visual/manifest pipeline сохраняется, но музыка будет реально декодирована и обработана (crossfade / LUFS / ambient), поэтому MP3 packet-copy отключается и рендер может быть медленнее или больше. Чтобы получить Original MP3 bitstream-copy, выключите audio processing.`);
      }
      const stamp=Date.now().toString(36);
      const queuedProjects=resolved.map(({project,selectedEffect},i)=>({...project,selectedEffectId:selectedEffect?.id||NO_EFFECT_SELECTION,id:`${project.id}-${stamp}-${i}-${Math.random().toString(36).slice(2,8)}`,status:'queued' as const,progress:0,stage:'Ожидает в очереди',elapsedSec:0}));
      await api.enqueue(queuedProjects,settings,effectRegistry,activeSubscribes,activeAmbient,ambientSettings);
      appendProjects(queuedProjects);setDraftProjects([]);setPreviewProjectPath(undefined);setInvalidProjects([]);setScanNote('');setPage('render');
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
      <div className="modeGrid">{modes.map(m=><button key={m.id} className={`modeCard ${settings.loopMode===m.id?'selected':''}`} onClick={()=>patchSettings({loopMode:m.id})}><span className="modeVisual"><Icon name={m.icon}/></span><span><b>{m.title}</b><small>{m.subtitle}</small></span></button>)}</div>
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
        <div className="bigControl"><div><b>Битрейт</b><small>Для обычных видео-проектов. Для статичного проекта ENDLUME автоматически выбирает компактный режим без жёсткого ухудшения качества.</small></div><div className="bigValue">{settings.bitrateMbps} Мбит/с</div><Range value={settings.bitrateMbps} min={1} max={100} onChange={v=>patchSettings({bitrateMbps:v})} minLabel="1 Мбит/с" maxLabel="100 Мбит/с"/></div>
        <div className="bigControl compactControl"><div><b>Кроссфейд между треками</b><small>{settings.crossfadeSec>0?'Processed Audio: переход реально сводится; MP3 packet-copy отключён. Быстрый static visual/manifest path остаётся, но обработка музыки может занять больше времени.':'Original Audio: совместимые MP3 идут bitstream-copy без повторного кодирования. Fast static path сохраняет музыку в исходном виде.'}</small></div><div className="bigValue small">{settings.crossfadeSec>0?`${settings.crossfadeSec} сек`:'Выкл'}</div><Range value={settings.crossfadeSec} min={0} max={10} step={0.5} onChange={v=>patchSettings({crossfadeSec:v})} minLabel="Выкл" maxLabel="10 сек"/></div><div className="durationPresets"><button className={settings.crossfadeSec===0?'selected':''} onClick={()=>patchSettings({crossfadeSec:0})}>ВЫКЛ</button>{[1,2,3,5,7,10].map(v=><button className={settings.crossfadeSec===v?'selected':''} key={`cf-${v}`} onClick={()=>patchSettings({crossfadeSec:v})}>{v}с</button>)}</div>
        <div className="toggles"><Toggle checked={settings.normalizeLufs} onChange={v=>patchSettings({normalizeLufs:v})} label="Нормализация звука до -14 LUFS"/><Toggle checked={settings.durationMode==='whole-track'} onChange={v=>patchSettings({durationMode:v?'whole-track':'exact'})} label="Не обрезать последнюю песню" help="ENDLUME может увеличить итог на несколько минут, чтобы композиция закончилась естественно"/><Toggle checked={settings.encoderPreference==='auto'} onChange={v=>patchSettings({encoderPreference:v?'auto':'quality'})} label="Автовыбор самого быстрого движка" help="NVENC / QSV / AMF / Apple VideoToolbox / CPU"/></div>
      </div>
    </section>

    <section className="sectionBlock"><div className="sectionTitle">КНОПКА SUBSCRIBE</div><div className="featureRow"><span className="featureIcon pink"><Icon name="subscribe"/></span><div><b>Subscribe Button</b><small>{!features.subscribe?'Отключено для текущих рендеров':subscribes.filter(s=>s.enabled).length?`Активно пресетов: ${subscribes.filter(s=>s.enabled).length}`:'Не настроено'}</small></div><div className="rowButtons"><button onClick={()=>setFeature('subscribe',!features.subscribe)}>{features.subscribe?'ВЫКЛЮЧИТЬ':'ВКЛЮЧИТЬ'}</button><button onClick={()=>openEditor({kind:'subscribe'})}>НАСТРОИТЬ →</button></div></div></section>

    <section className="sectionBlock">
      <div className="sectionTitle">ЭФФЕКТЫ</div>
      <div className="featureRow"><span className="featureIcon blue"><Icon name="effects"/></span><div><b>Эффект для каждого проекта</b><small>{!features.effects?'Отключено для текущих рендеров':effects.length?`В библиотеке: ${effects.length} • доступно: ${selectableEffects.length}${repairRequiredEffects.length?` • восстановить: ${repairRequiredEffects.length}`:''}`:'Эффекты в библиотеке не настроены'}</small></div><div className="rowButtons"><button onClick={()=>setFeature('effects',!features.effects)}>{features.effects?'ВЫКЛЮЧИТЬ':'ВКЛЮЧИТЬ'}</button><button onClick={()=>openEditor({kind:'effects'})}>НАСТРОИТЬ →</button></div></div>
      {features.effects&&repairRequiredEffects.length>0&&<div className="validationBox"><b>Effects требуют восстановления:</b>{repairRequiredEffects.map((effect,index)=><div key={`repair-${effect.id}-${index}`}><strong>{effect.name}</strong> — ⚠ REPAIR REQUIRED{effect.assetError?` • ${effect.assetError}`:''} <button onClick={()=>void repairEffectSource(effect)}>ВОССТАНОВИТЬ ФАЙЛ</button></div>)}</div>}
      {features.effects&&duplicateEffectIds.length>0&&<div className="validationBox"><b>Effects registry заблокирован:</b><div>Одинаковый ID назначен нескольким эффектам: {duplicateEffectIds.join(', ')}. Рендер с эффектами запрещён, чтобы ENDLUME не подставил другой эффект.</div></div>}
      {features.effects&&draftProjects.length>0&&<div className="renderCard">
        <div className="optionGroup"><span>Применить ко всем найденным проектам</span><div className="chipRow"><button onClick={()=>draftProjects.forEach(p=>setSelectedEffectForProject(p.path,NO_EFFECT_SELECTION))}>БЕЗ ЭФФЕКТА</button>{effects.map((effect,index)=>{const selectable=effectIsSelectable(effect)&&!duplicateEffectIds.includes(effect.id);return <button key={`all-${effect.id}-${index}`} disabled={!selectable} title={effect.assetError||effectStatusLabel(effect)} onClick={()=>selectable&&draftProjects.forEach(p=>setSelectedEffectForProject(p.path,effect.id))}>{effect.name} • {effectStatusLabel(effect)}</button>})}</div></div>
        {draftProjects.map(project=>{const selectionIssue=selectionIssueForPath(project.path);return <div className="optionGroup" key={`effect-${project.path}`}><span>{project.name}</span><div className="chipRow"><button className={selectedEffectIdForPath(project.path)===NO_EFFECT_SELECTION?'selected':''} onClick={()=>setSelectedEffectForProject(project.path,NO_EFFECT_SELECTION)}>БЕЗ ЭФФЕКТА</button>{effects.map((effect,index)=>{const duplicate=duplicateEffectIds.includes(effect.id);const selectable=effectIsSelectable(effect)&&!duplicate;return <button key={`${project.path}-${effect.id}-${index}`} disabled={!selectable} title={effect.assetError||effectStatusLabel(effect)} className={selectedEffectIdForPath(project.path)===effect.id&&!duplicate?'selected':''} onClick={()=>selectable&&setSelectedEffectForProject(project.path,effect.id)}>{effect.name} • {effectStatusLabel(effect)}</button>})}</div>{selectionIssue&&<small>⚠ {selectionIssue}</small>}</div>})}
      </div>}
    </section>

    <section className="sectionBlock">
      <div className="sectionTitle">BACKGROUND MUSIC</div>
      <div className="featureRow"><span className="featureIcon"><Icon name="ambient"/></span><div><b>Фоновая музыка</b><small>{!features.ambient?'Отключено для текущих рендеров':ambient||'Не выбрана'}</small></div><div className="rowButtons"><button onClick={()=>setFeature('ambient',!features.ambient)}>{features.ambient?'ВЫКЛЮЧИТЬ':'ВКЛЮЧИТЬ'}</button><button onClick={async()=>{const p=await api.chooseAmbient();if(p)await saveAmbient(p)}}>ВЫБРАТЬ</button>{ambient&&<button className="dangerText" onClick={()=>void saveAmbient(undefined)}>УДАЛИТЬ</button>}</div></div>
      {ambient&&<div className="renderCard">
        <div className="bigControl compactControl"><div><b>ГРОМКОСТЬ</b><small>Только фоновая музыка. Основные песни не меняются.</small></div><div className="bigValue small">{Math.round(ambientSettings.volumePct)}%</div><Range value={ambientSettings.volumePct} min={0} max={100} step={1} onChange={v=>void saveAmbientSettings({volumePct:v})} minLabel="0%" maxLabel="100%"/></div>
        <div className="bigControl compactControl"><div><b>НИЗКИЕ / BASS</b><small>3-band EQ фоновой музыки</small></div><div className="bigValue small">{ambientSettings.bassDb.toFixed(1)} dB</div><Range value={ambientSettings.bassDb} min={-12} max={12} step={0.5} onChange={v=>void saveAmbientSettings({bassDb:v})} minLabel="-12 dB" maxLabel="+12 dB"/></div>
        <div className="bigControl compactControl"><div><b>СРЕДНИЕ / MID</b><small>Нейтральное значение: 0 dB</small></div><div className="bigValue small">{ambientSettings.midDb.toFixed(1)} dB</div><Range value={ambientSettings.midDb} min={-12} max={12} step={0.5} onChange={v=>void saveAmbientSettings({midDb:v})} minLabel="-12 dB" maxLabel="+12 dB"/></div>
        <div className="bigControl compactControl"><div><b>ВЫСОКИЕ / TREBLE</b><small>Нейтральное значение: 0 dB</small></div><div className="bigValue small">{ambientSettings.trebleDb.toFixed(1)} dB</div><Range value={ambientSettings.trebleDb} min={-12} max={12} step={0.5} onChange={v=>void saveAmbientSettings({trebleDb:v})} minLabel="-12 dB" maxLabel="+12 dB"/></div>
        <p className="editorHint">Фоновая музыка автоматически зацикливается до MASTER duration и обрезается ровно на конце видео.</p>
      </div>}
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
