const isTerminal=(status?:string)=>status==='done'||status==='error';

export function applyProjectPatch(projects:any[],id:string,patch:any){
  return projects.map(project=>{
    if(project.id!==id)return project;
    const incomingStatus=patch?.status as string|undefined;
    if(isTerminal(project.status)){
      if(incomingStatus===project.status){
        const safePatch={...patch};
        for(const key of ['resultPath','resultBytes','actualVideoBitrate','encoder','startedAt','elapsedSec']){
          if(safePatch[key]===null||safePatch[key]===undefined)delete safePatch[key];
        }
        const merged={...project,...safePatch,progress:100};
        if(project.status==='done'){merged.stage=safePatch?.stage||project.stage||'Готово';merged.etaSec=0;}
        if(project.status==='error'){merged.etaSec=0;}
        return merged;
      }
      // A late FFmpeg/progress/queue event must never downgrade a finalized job.
      // Keep harmless telemetry fields, but freeze lifecycle/result state.
      const safe={...patch};
      for(const key of ['status','progress','stage','etaSec','startedAt','resultPath','resultBytes'])delete safe[key];
      return {...project,...safe};
    }
    const merged:any={...project,...patch};
    if(incomingStatus==='done'){
      merged.status='done';merged.progress=100;merged.stage=patch?.stage||'Готово';merged.etaSec=0;
    }else if(incomingStatus==='error'){
      merged.status='error';merged.progress=100;merged.etaSec=0;
    }else if(incomingStatus==='rendering'){
      merged.progress=Math.max(Number(project.progress)||0,Number(patch?.progress)||0);
      merged.elapsedSec=Math.max(Number(project.elapsedSec)||0,Number(patch?.elapsedSec)||0);
    }
    return merged;
  });
}

export function applyQueueSnapshot(projects:any[],snapshot:any){
  const active=snapshot?.active;
  const pending=Array.isArray(snapshot?.pending)?snapshot.pending:[];
  const finished=Array.isArray(snapshot?.finished)?snapshot.finished:[];
  let next=[...projects];

  // Backend terminal snapshots are an independent completion acknowledgement.
  // If render-done is delayed or lost, the queue snapshot still forces 100%/done.
  for(const terminal of finished){
    const project=terminal?.project;
    const terminalId=String(terminal?.id||project?.id||'');
    if(!terminalId)continue;
    const patch:any={...terminal};delete patch.project;delete patch.id;
    let idx=next.findIndex(x=>x.id===terminalId);
    if(idx<0&&project?.path)idx=next.findIndex(x=>x.path===project.path&&!isTerminal(x.status));
    if(idx>=0){
      next=applyProjectPatch(next,next[idx].id,patch);
    }else if(project){
      const added:any={...project,...patch};
      if(added.status==='done'){added.progress=100;added.stage=added.stage||'Готово';added.etaSec=0;}
      if(added.status==='error'){added.progress=100;added.etaSec=0;}
      next.push(added);
    }
  }

  const upsert=(job:any,status:'rendering'|'queued')=>{
    const project=job?.project;
    if(!project?.id)return;
    let idx=next.findIndex(x=>x.id===project.id);
    if(idx<0)idx=next.findIndex(x=>x.path===project.path&&!isTerminal(x.status));
    const old=idx>=0?next[idx]:undefined;
    // Queue snapshots may arrive after render-done/backend finished ack. Terminal state is authoritative.
    if(old&&isTerminal(old.status))return;
    const merged:any={...project,...old,status};
    if(status==='rendering'){
      merged.progress=Math.max(Number(old?.progress)||0,Number(project?.progress)||0);
      merged.stage=old?.stage||'Запускаю рендер';
      merged.elapsedSec=Math.max(Number(old?.elapsedSec)||0,Number(project?.elapsedSec)||0);
    }else{
      merged.progress=Number(old?.progress)||0;
      merged.stage=old?.stage||'Ожидает в очереди';
      merged.elapsedSec=Number(old?.elapsedSec)||0;
    }
    if(idx>=0)next[idx]=merged;else next.push(merged);
  };
  if(active)upsert(active,'rendering');
  pending.forEach((job:any)=>upsert(job,'queued'));
  return next;
}
