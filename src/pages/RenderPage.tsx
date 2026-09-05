import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useApp } from '../store';
import { api } from '../tauri';
import { finishAt,fmtBytes,fmtSeconds,Icon } from '../components/ui';

function useSmoothNumber(target:number,duration=220){
  const [value,setValue]=useState(target);
  const current=useRef(target),raf=useRef<number|undefined>(undefined);
  useEffect(()=>{
    const from=current.current,to=target,start=performance.now();
    if(raf.current)cancelAnimationFrame(raf.current);
    const tick=(now:number)=>{
      const t=Math.min(1,(now-start)/duration);
      const eased=1-Math.pow(1-t,3);
      current.current=from+(to-from)*eased;setValue(current.current);
      if(t<1)raf.current=requestAnimationFrame(tick);
    };
    raf.current=requestAnimationFrame(tick);
    return()=>{if(raf.current)cancelAnimationFrame(raf.current)};
  },[target,duration]);
  return value;
}

function fmtLiveSeconds(sec?:number){
  if(sec==null||!Number.isFinite(sec))return '—';
  const value=Math.max(0,sec),h=Math.floor(value/3600),m=Math.floor((value%3600)/60),x=value%60;
  return `${h>0?`${String(h).padStart(2,'0')}:`:''}${String(m).padStart(2,'0')}:${x.toFixed(1).padStart(4,'0')}`;
}

function SmoothPercent({target}:{target:number}){const value=useSmoothNumber(target,260);return <>{value.toFixed(2)}%</>}
function SmoothBar({target}:{target:number}){const value=useSmoothNumber(target,260);return <i style={{width:`${value}%`}}/>}

function LiveTelemetry({id,status,startedAt,elapsedSec,etaSec}:{id?:string;status?:string;startedAt?:number;elapsedSec:number;etaSec?:number}){
  const [now,setNow]=useState(()=>Date.now());
  const etaRef=useRef<{id?:string;eta?:number;at:number}>({id,eta:etaSec,at:Date.now()});
  useEffect(()=>{etaRef.current={id,eta:etaSec,at:Date.now()}},[id,etaSec]);
  useEffect(()=>{
    if(status!=='rendering'){setNow(Date.now());return;}
    let raf=0,last=0;
    const tick=(ts:number)=>{if(ts-last>=100){last=ts;setNow(Date.now())}raf=requestAnimationFrame(tick)};
    raf=requestAnimationFrame(tick);return()=>cancelAnimationFrame(raf);
  },[status,id]);
  const liveElapsed=status==='rendering'&&startedAt?Math.max(elapsedSec||0,(now-startedAt)/1000):elapsedSec;
  const liveEta=status==='rendering'&&etaRef.current.id===id&&etaRef.current.eta!=null?Math.max(0,etaRef.current.eta-(now-etaRef.current.at)/1000):etaSec;
  return <div className="renderTelemetry"><div><small>НАЧАЛО</small><b>{startedAt?new Date(startedAt).toLocaleTimeString():'—'}</b></div><div><small>ПРОШЛО</small><b className="liveClock">{status==='rendering'?fmtLiveSeconds(liveElapsed):fmtSeconds(elapsedSec)}</b></div><div><small>ОСТАЛОСЬ</small><b className="liveClock">{status==='rendering'?fmtLiveSeconds(liveEta):fmtSeconds(etaSec)}</b></div><div><small>≈ ЗАВЕРШЕНИЕ</small><b>{finishAt(liveEta)}</b></div></div>;
}

function useDiskStatus(path:string,status?:string){
  const [disk,setDisk]=useState<{totalBytes:number;freeBytes:number;usedBytes:number;mount:string}>();
  useEffect(()=>{
    let alive=true;let timer:number|undefined;
    const read=()=>api.diskStatus(path).then(v=>alive&&setDisk(v)).catch(()=>{});
    void read();
    if(status==='rendering')timer=window.setInterval(read,1000);
    return()=>{alive=false;if(timer)window.clearInterval(timer)};
  },[path,status]);
  return disk;
}

const stageNames=[
  'Анализ файлов','Проверяю самый быстрый движок','Подготавливаю медиа','Собираю master-loop','Проверяю кэш Effects и Subscribe','Кэш Effects и Subscribe готов','Подготавливаю музыку','Аудио-цикл готов — без лишней многочасовой копии','Собираю длинный аудио-кэш','Подготавливаю вариант Effects','Собираю визуальные сегменты','Добавляю Subscribe','Склеиваю визуальную дорожку','Собираю итоговое видео','Финальная проверка FFprobe','Готово'
];

export function RenderPage(){
  const projects=useApp(s=>s.projects),settings=useApp(s=>s.settings),setPage=useApp(s=>s.setPage),removeProject=useApp(s=>s.removeProject),clearFinished=useApp(s=>s.clearFinished),setDraftProjects=useApp(s=>s.setDraftProjects),patchProject=useApp(s=>s.patchProject);
  const [selected,setSelected]=useState<string|undefined>();
  const active=projects.find(p=>p.id===selected)||projects.find(p=>p.status==='rendering')||projects.find(p=>p.status==='done')||projects[0];
  const disk=useDiskStatus(settings.outputDir,active?.status);
  const done=projects.filter(p=>p.status==='done').length, errors=projects.filter(p=>p.status==='error').length;
  const remain=projects.filter(p=>!['done','error'].includes(p.status)).length;
  const avg=useMemo(()=>{const a=projects.filter(p=>p.status==='done'&&p.elapsedSec>0);return a.length?a.reduce((s,p)=>s+p.elapsedSec,0)/a.length:undefined},[projects]);
  const queueEta=avg?avg*remain:undefined;
  const totalElapsed=projects.filter(p=>['done','error'].includes(p.status)).reduce((sum,p)=>sum+(p.elapsedSec||0),0);
  const overall=projects.length?projects.reduce((s,p)=>s+(p.status==='done'||p.status==='error'?100:p.progress),0)/projects.length:0;
  const reorder=async(dragId:string,targetId:string)=>{
    if(dragId===targetId)return;
    const queued=projects.filter(p=>p.status==='queued');
    const ids=queued.map(p=>p.id);const a=ids.indexOf(dragId),b=ids.indexOf(targetId);if(a<0||b<0)return;
    const [id]=ids.splice(a,1);ids.splice(b,0,id);await api.reorderQueue(ids);
  };
  const openResult=async(path?:string)=>{if(!path)return;try{await api.openPath(path)}catch(e){await api.showError(`Не удалось открыть видео.\n${String(e)}`)}};
  const revealResult=async(path?:string)=>{if(!path)return;try{await api.reveal(path)}catch(e){await api.showError(`Не удалось открыть папку результата.\n${String(e)}`)}};
  return <div className="renderPage">
    <div className="renderHeader"><div><small>РЕНДЕР ОЧЕРЕДИ · {done+errors} ИЗ {projects.length}</small><h1>{projects.length>0&&done+errors===projects.length?'Все рендеры завершены':'Рендер очереди'}</h1></div><button className="backProject endlumeAction ghostAction" onClick={()=>setPage('project')}>← ВЕРНУТЬСЯ К ПРОЕКТУ</button></div>
    <div className="renderWorkspace">
      <aside className="queuePanel">
        <div className="queueTitle">ОЧЕРЕДЬ · {projects.length}</div>
        <div className="queueCards">{projects.map(p=><div key={p.id} className={`queueCard ${active?.id===p.id?'active':''} ${p.status}`} onClick={()=>setSelected(p.id)} draggable={p.status==='queued'} onDragStart={e=>e.dataTransfer.setData('text/endlume',p.id)} onDragOver={e=>p.status==='queued'&&e.preventDefault()} onDrop={e=>reorder(e.dataTransfer.getData('text/endlume'),p.id)}>
          <span className="queueRail"><i/></span><div className="queueCardBody"><div className="queueName"><b>{p.name}</b><strong>{p.progress.toFixed(2)}%</strong></div><small>{p.media.length?`${p.media.length} медиа`:''} • {p.audio.length} треков</small><em>{p.status==='done'?'ГОТОВ':p.status==='error'?'ОШИБКА':p.stage}</em><div className="queueMini"><i style={{width:`${p.progress}%`}}/></div></div>
        </div>)}</div>
        <div className="queueCount"><b>{done} готово</b><span>•</span><b className={errors?'bad':''}>{errors} ошибок</b></div>
      </aside>

      <section className="renderDetails">{active?<>
        <div className="selectedRenderHead"><div><small>{active.status==='done'?'ГОТОВЫЙ ПРОЕКТ':'СЕЙЧАС РЕНДЕРИТСЯ'}</small><h2>{active.name}</h2><p>{active.media.length} медиа • {active.audio.length} аудиотреков{active.encoder?` • ${active.encoder}`:''}</p></div><div className="progressNumber"><SmoothPercent target={active.progress}/></div></div>
        <div className="mainProgress"><SmoothBar target={active.progress}/></div>
        <LiveTelemetry id={active.id} status={active.status} startedAt={active.startedAt} elapsedSec={active.elapsedSec} etaSec={active.etaSec}/>
        <div className="renderBodyGrid">
          <div className="stageCard"><div className="stageCardTitle">ПРОЦЕСС</div><div style={{margin:"0 0 12px",padding:"12px 14px",border:"1px solid #344064",borderRadius:10,background:"rgba(83,94,255,.07)",display:"grid",gridTemplateColumns:"1fr auto",gap:"4px 12px"}}><small style={{gridColumn:"1 / -1",color:"#7f8aa8"}}>СЕЙЧАС ВЫПОЛНЯЕТСЯ</small><b style={{color:"#eef2ff",fontSize:13}}>{active.stage||'Подготовка'}</b><strong style={{color:"#8d7cff"}}>{active.progress.toFixed(2)}%</strong></div>{(()=>{const lower=(active.stage||'').toLowerCase();const exact=stageNames.findIndex(s=>lower.includes(s.toLowerCase()));const fallback=Math.max(0,Math.min(stageNames.length-1,Math.floor((active.progress/100)*(stageNames.length-1))));const currentIndex=active.status==='done'?stageNames.length-1:(exact>=0?exact:fallback);return stageNames.map((s,i)=>{const cur=i===currentIndex;const completed=active.status==='done'||(currentIndex>=0&&i<currentIndex);return <div className={`stageLine ${cur?'current':''} ${completed?'complete':''}`} key={s}><span>{completed?'✓':cur?'●':i+1}</span><b>{s}</b>{cur&&<em>выполняется</em>}</div>})})()}</div>
          <div className="systemCard"><div className="stageCardTitle">РЕСУРСЫ</div><Metric name="CPU" value={active.cpuPct} unit="%"/><Metric name="RAM ENDLUME" value={active.ramBytes&&active.ramTotalBytes?Math.min(100,(active.ramBytes/active.ramTotalBytes)*100):undefined} label={active.ramBytes?fmtBytes(active.ramBytes):'—'}/><div className="memoryStats"><span><small>ДИСК · ИСПОЛЬЗОВАНО</small><b>{fmtBytes(disk?.usedBytes)}</b></span><span><small>ДИСК · СВОБОДНО</small><b>{fmtBytes(disk?.freeBytes)}</b></span><span><small>ДИСК · ВСЕГО</small><b>{fmtBytes(disk?.totalBytes)}</b></span></div><Metric name="GPU" value={active.gpuPct} unit="%"/><div className="engineName"><small>ДВИЖОК</small><b>{active.encoder||'Автовыбор'}</b>{disk?.mount&&<small>{disk.mount}</small>}</div></div>
        </div>
        {active.status==='rendering'&&<div className="activeRenderActions"><button className="endlumeAction dangerAction" onClick={async()=>{await api.cancelProject(active.id);patchProject(active.id,{stage:'Останавливаю FFmpeg…'})}}>ОСТАНОВИТЬ ТЕКУЩИЙ</button><button className="endlumeAction ghostAction" onClick={()=>setPage('project')}>← ВЕРНУТЬСЯ К ПРОЕКТУ</button></div>}
        {active.status==='queued'&&<div className="activeRenderActions"><button className="endlumeAction dangerAction" onClick={async()=>{await api.cancelProject(active.id);removeProject(active.id)}}>УДАЛИТЬ ИЗ ОЧЕРЕДИ</button></div>}
        {active.status==='done'&&<div className="resultCard"><div><b>Время рендера: {fmtSeconds(active.elapsedSec)}</b><span>Размер файла: {fmtBytes(active.resultBytes)}</span><span>Аудиотреков: {active.audio.length}</span>{active.actualVideoBitrate&&<span>Фактический битрейт: {(active.actualVideoBitrate/1_000_000).toFixed(2)} Мбит/с</span>}{active.engineTimings&&<span>Engine: {Object.entries(active.engineTimings as Record<string,number>).map(([k,v])=>`${k} ${v.toFixed(1)}с`).join(' • ')}</span>}<span className="resultPath">{active.resultPath}</span></div><div className="resultButtons"><button className="endlumeAction primaryAction" disabled={!active.resultPath} onClick={()=>openResult(active.resultPath)}>Открыть видео</button><button className="endlumeAction ghostAction" disabled={!active.resultPath} onClick={()=>revealResult(active.resultPath)}>Открыть папку вывода</button><button className="endlumeAction ghostAction" onClick={async()=>{try{const found=await api.scanRoot(active.path);const same=found.find(x=>x.path===active.path)||found.find(x=>x.valid);if(same)setDraftProjects([{...same,status:'validating',progress:0,stage:'Готов к повтору',elapsedSec:0}]);setPage('project')}catch{setPage('project')}}}>Повторить</button><button className="endlumeAction dangerAction" onClick={()=>removeProject(active.id)}>Удалить</button></div></div>}
        {active.status==='error'&&<div className="errorResult"><b>{active.stage}</b><p>Проект пропущен. ENDLUME продолжает следующую задачу в очереди.</p></div>}
      </>:<div className="emptyRender"><Icon name="render"/><h2>Очередь пуста</h2><p>Вернитесь в проект и добавьте папки.</p></div>}</section>
    </div>
    <footer className="queueFooter"><span>ПРОГРЕСС ОЧЕРЕДИ</span><b>{projects.length?`${done+errors} ИЗ ${projects.length}`:'0 ИЗ 0'}</b><strong><SmoothPercent target={overall}/></strong><div className="footerBar"><SmoothBar target={overall}/></div><span>СРЕДНЕЕ {fmtSeconds(avg)}</span><span>ОСТАЛОСЬ {remain}</span><span>≈ {fmtSeconds(queueEta)}</span><span>ЗАВЕРШИТСЯ ≈ {finishAt(queueEta)}</span><span>ОБЩЕЕ ВРЕМЯ {fmtSeconds(totalElapsed)}</span>{done+errors>0&&<button className="endlumeAction miniAction" onClick={clearFinished}>Очистить готовые</button>}</footer>
  </div>;
}

function Metric({name,value,unit,label}:{name:string;value?:number;unit?:string;label?:string}){const v=value==null?0:Math.max(0,Math.min(100,value));return <div className="metric"><div><span>{name}</span><b>{label||(value==null?'—':`${value.toFixed(0)}${unit||''}`)}</b></div><div className="metricBar"><i style={{width:`${v}%`}}/></div></div>}
