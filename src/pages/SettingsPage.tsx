import React, { useEffect, useState } from 'react';
import { api, type SingleAppStatus } from '../tauri';
import type { BenchmarkResult, LicenseStatus } from '../types';
import { ReleaseHistory } from '../components/ReleaseHistory';

type Tab='general'|'engine'|'updates'|'about';
export function SettingsPage(){
  const [tab,setTab]=useState<Tab>('general'),[license,setLicense]=useState<LicenseStatus>({valid:true,type:'development'}),[key,setKey]=useState(''),[bench,setBench]=useState<BenchmarkResult>(),[busy,setBusy]=useState(false),[update,setUpdate]=useState<any>(),[updateProgress,setUpdateProgress]=useState<number|null>(null),[cache,setCache]=useState<{count:number;bytes:number}>({count:0,bytes:0}),[appGuard,setAppGuard]=useState<SingleAppStatus>();
  useEffect(()=>{api.license().then(setLicense).catch(()=>{});api.cacheStats().then(setCache).catch(()=>{});api.cleanupDuplicateApps(false).then(setAppGuard).catch(()=>{})},[]);
  const checkAndInstall=async()=>{
    if(busy)return;setBusy(true);setUpdateProgress(null);
    try{
      const u=await api.checkUpdate();setUpdate(u||{none:true});
      if(u?.version&&u?.install){setUpdateProgress(0);await u.install((p:number)=>setUpdateProgress(p));}
    }catch(e){setUpdateProgress(null);setUpdate({error:String(e)});await api.showError(`Не удалось обновить ENDLUME: ${String(e)}`)}finally{setBusy(false)}
  };
  const cleanDuplicates=async()=>{
    if(busy)return;setBusy(true);try{const result=await api.cleanupDuplicateApps(true);setAppGuard(result);if(result.failed?.length)await api.showError(`Не удалось удалить ${result.failed.length} коп. ENDLUME.\n${result.failed.map(x=>`${x.path}: ${x.error}`).join('\n')}`)}catch(e){await api.showError(String(e))}finally{setBusy(false)}
  };
  const normalizeName=async()=>{
    if(busy)return;setBusy(true);try{await api.normalizeAppName()}catch(e){setBusy(false);await api.showError(`Не удалось переименовать приложение в ENDLUME Studio.\n${String(e)}`)}
  };
  const appHealthy=appGuard?.singleApp&&appGuard?.canonicalName!==false;
  return <div className="simplePage settingsPage"><div className="simpleHeader"><div><small>ENDLUME STUDIO</small><h1>Настройки</h1><p>Обновления, лицензия, Fast Engine и информация о программе.</p></div></div><div className="settingsTabs">{(['general','engine','updates','about'] as Tab[]).map(t=><button className={tab===t?'active':''} onClick={()=>setTab(t)} key={t}>{t==='general'?'ОБЩИЕ':t==='engine'?'FAST ENGINE':t==='updates'?'ОБНОВЛЕНИЯ':'О ПРОГРАММЕ'}</button>)}</div>
    {tab==='general'&&<div className="settingsCard"><h3>Лицензия</h3><div className="licenseStatus"><i className={license.valid?'ok':'bad'}/><div><b>{license.valid?'ENDLUME активирована':'Нужна активация'}</b><small>{license.type==='owner-lifetime'?'Бессрочная лицензия владельца':license.type==='monthly'?'Месячная лицензия':license.type==='development'?'Development build':'Лицензия не найдена'}</small></div></div>{!license.valid&&<div className="activationLine"><input placeholder="Введите ключ ENDLUME" value={key} onChange={e=>setKey(e.target.value)}/><button onClick={async()=>{try{setLicense(await api.activate(key))}catch(e){await api.showError(String(e))}}}>АКТИВИРОВАТЬ</button></div>}<p className="settingsNote">Рендер работает локально. Интернет нужен только для активации/проверки лицензии и обновлений.</p></div>}
    {tab==='engine'&&<div className="settingsCard"><h3>ENDLUME Fast Engine</h3><p>Benchmark проверяет доступные аппаратные кодировщики и выбирает самый быстрый рабочий вариант.</p><button className="settingsAction" disabled={busy} onClick={async()=>{setBusy(true);try{setBench(await api.benchmark())}finally{setBusy(false)}}}>{busy?'ПРОВЕРЯЮ…':'ЗАПУСТИТЬ BENCHMARK'}</button>{bench&&<div className="bench"><b>Выбран: {bench.selected}</b>{bench.candidates.map(x=><div key={x.encoder}><span>{x.encoder}</span><em className={x.ok?'ok':'bad'}>{x.ok?`${x.seconds?.toFixed(2)||'?'} сек`:'недоступен'}</em></div>)}</div>}<p className="settingsNote">Кэш Effects: {cache.count} файлов • {(cache.bytes/1024/1024).toFixed(1)} МБ.</p></div>}
    {tab==='updates'&&<div className="settingsCard"><h3>Обновления</h3><p>ENDLUME Studio 1.0.0-alpha.8.8</p><button className="settingsAction" disabled={busy} onClick={checkAndInstall}>{busy?(updateProgress!==null?`ОБНОВЛЯЮ ${updateProgress.toFixed(0)}%`:'ПРОВЕРЯЮ…'):'ПРОВЕРИТЬ И ОБНОВИТЬ'}</button>{updateProgress!==null&&<div className="updateProgress"><i style={{width:`${updateProgress}%`}}/><span>{updateProgress.toFixed(0)}%</span></div>}{update?.none&&<div><p className="updateOk">Установлена актуальная alpha-версия: {update.current||'1.0.0-alpha.8.8'}.</p></div>}{update?.version&&<div className="updateFound"><b>Устанавливается ENDLUME {update.version}</b>{update.date&&<small>{String(update.date)}</small>}<p>{update.body}</p><p className="settingsNote">Обновляется текущая ENDLUME Studio.app. После установки приложение автоматически перезапустится.</p></div>}{update?.error&&<p className="updateError">Ошибка обновления: {update.error}</p>}
      <div className="whatsNew"><h4>SINGLE APP GUARD</h4><p className={appHealthy?'updateOk':'settingsNote'}>{appGuard?.supported===false?'На этой системе не требуется.':appHealthy?'✓ Найдена одна ENDLUME Studio.app с правильным именем.':appGuard?.canonicalName===false?`Имя приложения сейчас: ${appGuard.currentName||'неизвестно'}. Нужно: ENDLUME Studio.app.`:appGuard?`Найдено копий: ${appGuard.remaining?.length||appGuard.found?.length||0}. Текущая: ${appGuard.currentPath||'—'}`:'Проверяю приложения…'}</p>
      {appGuard?.supported!==false&&appGuard?.canonicalName===false&&<button className="settingsAction" disabled={busy} onClick={normalizeName}>ИСПРАВИТЬ ИМЯ → ENDLUME Studio</button>}
      {appGuard?.supported!==false&&!appGuard?.singleApp&&<button className="settingsAction" disabled={busy} onClick={cleanDuplicates}>УДАЛИТЬ СТАРЫЕ КОПИИ ENDLUME</button>}
      {appGuard?.currentPath&&<p className="settingsNote">Текущее приложение: {appGuard.currentPath}</p>}
      {appGuard?.skipped?.some(x=>x.reason==='canonical-applications-copy')&&<p className="settingsNote">Текущая ENDLUME запущена не из /Applications, поэтому системная копия в /Applications не удаляется автоматически. Это защита от удаления основной установки.</p>}
      <ReleaseHistory/></div></div>}
    {tab==='about'&&<div className="settingsCard about"><div className="aboutLogo"><span className="infinity"><i/><i/></span></div><h2>ENDLUME Studio</h2><p>Long Video Engine</p><div className="aboutRows"><span>Версия <b>1.0.0-alpha.8.8</b></span><span>Обновлено <b>15.08.2026</b></span><span>Windows <b>10 / 11</b></span><span>macOS <b>Apple Silicon M1+</b></span><span>Render Core <b>Rust + FFmpeg</b></span><span>UI <b>Tauri 2</b></span></div></div>}
  </div>
}
