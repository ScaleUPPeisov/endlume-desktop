import React, { useEffect, useState } from 'react';
import type { RecoveryPayload } from '../types';
import { api } from '../tauri';

export function RecoveryModal({data,onClose}:{data:RecoveryPayload;onClose:()=>void}){
  const name=data.active?.project?.name;
  const count=(data.pending?.length||0)+(data.active?1:0);
  const [seconds,setSeconds]=useState(5),[running,setRunning]=useState(false);
  const resume=async()=>{if(running)return;setRunning(true);try{await api.resumeRecovery();onClose()}finally{setRunning(false)}};
  useEffect(()=>{
    if(running)return;
    if(seconds<=0){void resume();return}
    const t=setTimeout(()=>setSeconds(v=>v-1),1000);return()=>clearTimeout(t);
  },[seconds,running]);
  return <div className="modalBackdrop"><div className="dialogCard">
    <small>ВОССТАНОВЛЕНИЕ ОЧЕРЕДИ</small><h2>Предыдущая работа была прервана</h2>
    <p>ENDLUME обнаружила незавершённую очередь из <b>{count}</b> проектов{name?<>. Компьютер/приложение выключилось на проекте <b>«{name}»</b></>:null}. Проверь результат этого проекта после завершения очереди.</p>
    <p>Рендер автоматически продолжится через <b>{seconds}</b> сек. Уже готовые проекты повторно не запускаются.</p>
    <div className="dialogActions"><button className="ghost" onClick={async()=>{await api.dismissRecovery();onClose()}}>Отменить восстановление</button><button className="primary" disabled={running} onClick={resume}>{running?'ВОССТАНАВЛИВАЮ…':'ПРОДОЛЖИТЬ СЕЙЧАС →'}</button></div>
  </div></div>
}
