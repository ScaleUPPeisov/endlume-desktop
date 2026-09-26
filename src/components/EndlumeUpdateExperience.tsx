import React, { useMemo, useState } from 'react';
import { api } from '../tauri';

const HOMER_URL = new URL('../assets/endlume-homer.png', import.meta.url).href;

const STARTUP_LINES = [
  'Ща всё будет.',
  'Гомер запускает FFmpeg...',
  'Не трогай, оно рендерится.',
  'Разгоняем пиксели...',
  'Готовим абсолютное кино.',
  'FFmpeg уже проснулся.',
  'Проверяем, не решил ли Windows всё сломать.',
  'Сейчас будет быстро. Наверное.',
  'ENDLUME просыпается...',
  'Гомер уже нажал Render.'
];

const UPDATE_LINES = [
  'Качаем новую магию...',
  'Гомер следит за прогрессом.',
  'FFmpeg будет доволен.',
  'Старые баги пакуют чемоданы.',
  'Обновляем турбину.',
  'Ещё чуть-чуть...',
  'Windows пока держится.',
  'Готовим новый ENDLUME.'
];

function humanBytes(value?:number|null){
  if(!value||value<=0)return '—';
  const units=['Б','КБ','МБ','ГБ'];let n=value,idx=0;
  while(n>=1024&&idx<units.length-1){n/=1024;idx++}
  return `${n>=100||idx===0?n.toFixed(0):n.toFixed(1)} ${units[idx]}`;
}

function humanRate(value?:number|null){
  if(!value||value<=0)return '—';
  return `${humanBytes(value)}/с`;
}

function stateFromNative(value?:string){
  const v=String(value||'').toUpperCase();
  if(['DOWNLOADING','VERIFYING','READY_TO_INSTALL','INSTALLING','RESTART_REQUIRED','FAILED'].includes(v))return v;
  return '';
}

function changelog(body?:string){
  const rows=String(body||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean)
    .map(x=>x.replace(/^[-*•]\s*/,'')).filter(x=>x.length>2);
  return (rows.length?rows:[
    'Turbo Renderer for Windows',
    'Faster 1–3 hour renders',
    'Original MP3 packet-copy',
    'Better NVENC / QSV / AMF selection',
    'No song trimming',
    'Faster validation',
    'Windows 10 / 11 improvements'
  ]).slice(0,7);
}

export function StartupSplash(){
  const phrase=useMemo(()=>STARTUP_LINES[Math.floor(Math.random()*STARTUP_LINES.length)],[]);
  return <div className="endlumeStartup" role="status" aria-live="polite">
    <div className="endlumeAmbient endlumeAmbientA"/>
    <div className="endlumeAmbient endlumeAmbientB"/>
    <div className="endlumeStartupInner">
      <div className="endlumeMascotFrame startupMascot"><img src={HOMER_URL} alt="ENDLUME mascot"/></div>
      <div className="endlumeBrandLockup"><strong>ENDLUME</strong><span>YT Studio PEISOV</span></div>
      <p>{phrase}</p>
      <div className="endlumeBootLine"><i/></div>
    </div>
  </div>;
}

export function UpdateExperience({update,onLater}:{update:any;onLater:()=>void}){
  const [state,setState]=useState('UPDATE_AVAILABLE');
  const [progress,setProgress]=useState(0);
  const [stage,setStage]=useState('');
  const [detail,setDetail]=useState<any>({});
  const [error,setError]=useState('');
  const installing=!['UPDATE_AVAILABLE','FAILED','RESTART_REQUIRED'].includes(state);
  const bullets=useMemo(()=>changelog(update?.body),[update?.body]);
  const humor=UPDATE_LINES[Math.min(UPDATE_LINES.length-1,Math.floor(progress/14))]||UPDATE_LINES[0];

  const install=async()=>{
    setError('');setState('DOWNLOADING');setProgress(1);setStage('Подготавливаю подписанное обновление');
    try{
      await update.install((p:number,s?:string,d?:any)=>{
        setProgress(Math.max(0,Math.min(100,Number(p)||0)));
        if(s)setStage(s);
        if(d){
          setDetail(d);
          const native=stateFromNative(d.state);
          if(native)setState(native);
        }
      });
      setState('RESTART_REQUIRED');setProgress(100);setStage('Обновление установлено');
    }catch(e){
      setState('FAILED');setProgress(0);setError(String(e));
    }
  };

  const available=state==='UPDATE_AVAILABLE';
  const failed=state==='FAILED';
  const complete=state==='RESTART_REQUIRED';
  const downloaded=detail.downloadedBytes;
  const total=detail.totalBytes;

  return <div className="endlumeUpdateExperience" role="dialog" aria-modal="true" aria-label="Обновление ENDLUME">
    <div className="endlumeAmbient endlumeAmbientA"/>
    <div className="endlumeAmbient endlumeAmbientB"/>
    <div className="endlumeUpdateLayout">
      <section className="endlumeUpdateHero">
        <div className="endlumeMascotFrame"><img src={HOMER_URL} alt="ENDLUME Homer mascot"/></div>
        <div className="endlumeUpdateBadge">{complete?'UPDATE COMPLETE':failed?'UPDATE FAILED':available?'NEW ENDLUME':'ENDLUME UPDATE'}</div>
        <h1>{complete?'ENDLUME ОБНОВЛЁН':failed?'ОБНОВЛЕНИЕ ОСТАНОВЛЕНО':available?'Доступно обновление':'ENDLUME обновляется'}</h1>
        <div className="endlumeVersionRow"><span>{update.current||'текущая версия'}</span><b>→</b><strong>{update.version}</strong></div>
        <p className="endlumeReleaseTitle">{available?'Windows Turbo Renderer':complete?'Гомер сделал свою работу.':failed?'Ничего не устанавливаем, пока проверка не пройдёт.':humor}</p>

        {!available&&!failed&&<div className="endlumeProgressCard">
          <div className="endlumeProgressTop"><strong>{stage||state.replaceAll('_',' ')}</strong><b>{progress.toFixed(0)}%</b></div>
          <div className="endlumeProgressTrack"><i style={{width:`${progress}%`}}/></div>
          <div className="endlumeProgressMeta">
            <span>{downloaded||total?`${humanBytes(downloaded)} / ${humanBytes(total)}`:'Подготовка пакета'}</span>
            <span>Скорость: {humanRate(detail.bytesPerSecond)}</span>
            <span>Осталось: {detail.etaSeconds!=null?`~${Math.max(0,Math.ceil(detail.etaSeconds))} сек`:'—'}</span>
          </div>
          <small>{state==='INSTALLING'?'Windows может автоматически закрыть ENDLUME, чтобы завершить установку. После запуска новая версия покажет подтверждение.':'Не закрывайте ENDLUME во время загрузки и проверки.'}</small>
        </div>}

        {error&&<div className="endlumeUpdateError">Файл обновления не установлен: {error}</div>}

        <div className="endlumeUpdateActions">
          {available&&<><button className="endlumeSecondary" onClick={onLater}>ПОЗЖЕ</button><button className="endlumePrimary" onClick={install}>ОБНОВИТЬ</button></>}
          {failed&&<><button className="endlumeSecondary" onClick={onLater}>ЗАКРЫТЬ</button><button className="endlumePrimary" onClick={install}>ПОВТОРИТЬ</button></>}
          {complete&&<button className="endlumePrimary" onClick={()=>api.restartApp()}>RESTART ENDLUME</button>}
          {installing&&<button className="endlumeSecondary" disabled>ИДЁТ ОБНОВЛЕНИЕ…</button>}
        </div>
      </section>

      <aside className="endlumeWhatsNew">
        <small>WHAT'S NEW</small>
        <h2>{update.version}</h2>
        {update.date&&<div className="endlumeReleaseDate">{String(update.date)}</div>}
        <div className="endlumeChangeList">{bullets.map((x,i)=><div key={i}><i>✓</i><span>{x}</span></div>)}</div>
        <div className="endlumeIntegrity"><span>SECURITY</span><b>Signed package + SHA-256 verification</b><small>Установка блокируется при несовпадении хэша.</small></div>
      </aside>
    </div>
  </div>;
}

export function PostUpdateNotice({version,onClose}:{version:string;onClose:()=>void}){
  return <div className="endlumePostUpdate" role="status" aria-live="polite">
    <div className="endlumePostUpdateMascot"><img src={HOMER_URL} alt="ENDLUME Homer mascot"/></div>
    <div><b>ENDLUME обновлён до {version}</b><strong>Гомер сделал свою работу.</strong><span>Turbo Renderer • Original MP3 packet-copy • faster validation • Windows 10/11</span></div>
    <button onClick={onClose} aria-label="Закрыть">×</button>
  </div>;
}
