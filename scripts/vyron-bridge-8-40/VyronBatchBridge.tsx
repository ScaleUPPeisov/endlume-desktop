import React,{useEffect} from 'react';
import {listen} from '@tauri-apps/api/event';
import {api} from '../tauri';
import {useApp} from '../store';
import type {RenderProject} from '../types';

const MAP_KEY='endlume:vyron-batch-map:v1';
type BatchMap=Record<string,string>;
function readMap():BatchMap{try{return JSON.parse(localStorage.getItem(MAP_KEY)||'{}')}catch{return {}}}
function saveMap(value:BatchMap){localStorage.setItem(MAP_KEY,JSON.stringify(value))}

export function VyronBatchBridge(){
  useEffect(()=>{
    let live=true,busy=false;
    const importBatch=async()=>{
      if(!live||busy)return;busy=true;
      try{
        const req=await api.consumeVyronBatch();if(!req)return;
        const info=await api.loadVyronBatch(req.manifestPath);
        const valid:RenderProject[]=[];const invalid:Array<{name:string;path:string;error:string}>=[];
        for(const path of info.projectPaths){
          try{
            const rows=await api.scanRoot(path);const item=rows.find(x=>x.path===path)||rows[0];
            if(item?.valid)valid.push({...item,status:'queued',progress:0,stage:'Получено из VYRON',elapsedSec:0});
            else invalid.push({name:item?.name||path.split(/[\\/]/).pop()||path,path,error:item?.error||'Проект VYRON не прошёл проверку ENDLUME'});
          }catch(e){invalid.push({name:path.split(/[\\/]/).pop()||path,path,error:String(e)})}
        }
        if(!live)return;
        const st=useApp.getState();st.setDraftProjects(valid);st.setInvalidProjects(invalid);st.patchSettings({outputDir:info.outputDir});st.setLastRoot(info.rootPath);st.setPage('project');
        const map=readMap();for(const p of valid)map[p.path]=info.manifestPath;saveMap(map);
        if(valid.length!==info.projectCount||invalid.length){await api.showError(`VYRON batch ${info.batchId}: готово ${valid.length}/${info.projectCount}, ошибок ${invalid.length}. Исправьте отмеченные проекты перед рендером.`)}
        else await api.showInfo(`${info.channelName}: ${info.projectCount} проектов автоматически загружены из VYRON. Выберите эффекты один раз и нажмите «Добавить в очередь» — настройки применятся ко всей партии.`);
      }catch(e){if(live)await api.showError(`Не удалось принять VYRON batch: ${String(e)}`)}finally{busy=false}
    };
    void importBatch();const timer=window.setInterval(()=>void importBatch(),1200);return()=>{live=false;window.clearInterval(timer)};
  },[]);

  useEffect(()=>{
    const reported=new Set<string>();const offs:Promise<()=>void>[]=[];
    const locate=(id:string)=>{const s=useApp.getState();return s.projects.find(p=>p.id===id)||s.draftProjects.find(p=>p.id===id)};
    offs.push(listen<any>('render-progress',e=>{
      const id=String(e.payload?.id||'');if(!id||reported.has(id))return;const p=locate(id);if(!p)return;const manifest=readMap()[p.path];if(!manifest)return;reported.add(id);void api.reportVyronRender(manifest,p.path,'Rendering').catch(()=>{reported.delete(id)});
    }));
    offs.push(listen<any>('render-done',e=>{
      const id=String(e.payload?.id||'');const p=locate(id);if(!p)return;const manifest=readMap()[p.path];if(!manifest)return;
      const duration=Number(e.payload?.resultDuration||e.payload?.duration||0)||undefined;
      void api.reportVyronRender(manifest,p.path,'Completed',e.payload?.resultPath||null,duration,e.payload?.resultBytes??null,null).catch(()=>{});
    }));
    offs.push(listen<any>('render-error',e=>{
      const id=String(e.payload?.id||'');const p=locate(id);if(!p)return;const manifest=readMap()[p.path];if(!manifest)return;
      void api.reportVyronRender(manifest,p.path,'Error',null,null,null,String(e.payload?.error||e.payload?.stage||'Ошибка рендера')).catch(()=>{});
    }));
    return()=>{offs.forEach(p=>p.then(fn=>fn()).catch(()=>{}))}
  },[]);
  return null;
}
