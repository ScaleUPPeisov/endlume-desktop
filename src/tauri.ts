import { invoke, convertFileSrc } from '@tauri-apps/api/core';
import { open, message } from '@tauri-apps/plugin-dialog';
import { check } from '@tauri-apps/plugin-updater';
import { relaunch } from '@tauri-apps/plugin-process';
import type { BenchmarkResult, EffectPreset, LibraryPayload, LicenseStatus, ProjectScanItem, RecoveryPayload, RenderSettings, SubscribePreset } from './types';

export type SingleAppStatus={
  supported:boolean;
  singleApp:boolean;
  canonicalName?:boolean;
  canonicalInstall?:boolean;
  canonicalPath?:string;
  currentName?:string;
  currentPath?:string;
  currentVersion?:string;
  currentInApplications?:boolean;
  found?:string[];
  removed?:string[];
  remaining?:string[];
  failed?:Array<{path:string;error:string}>;
  skipped?:Array<{path:string;reason:string;version?:string}>;
  error?:string;
};

export type LivePreviewAssetPaths={basePath:string;baseKind:'image'|'video';overlayPath:string};

async function withTimeout<T>(promise:Promise<T>,ms:number,label:string):Promise<T>{
  let timer:number|undefined;
  try{return await Promise.race([promise,new Promise<T>((_,reject)=>{timer=window.setTimeout(()=>reject(new Error(`${label}: превышено время ожидания ${Math.round(ms/1000)} сек`)),ms)})]);}
  finally{if(timer!==undefined)window.clearTimeout(timer)}
}

async function importManagedAsset(source:string,kind:string){
  return invoke<string>('import_library_asset',{source,kind});
}

export const api = {
  chooseRoots: async()=>{
    const result=await open({directory:true,multiple:true,title:'Выберите папку или несколько папок с проектами'});
    if(!result)return [] as string[];
    return Array.isArray(result)?result:[result];
  },
  chooseOutput: async()=>{
    const result=await open({directory:true,multiple:false,title:'Папка для готовых видео'});
    return typeof result==='string'?result:null;
  },
  chooseVideo: async()=>{
    const result=await open({directory:false,multiple:false,title:'Выберите видео',filters:[{name:'Video',extensions:['mp4','mov','m4v','mkv','webm','avi','wmv','flv','ts','mts','m2ts','mpg','mpeg','vob','3gp']} ]});
    if(typeof result!=='string')return null;
    return importManagedAsset(result,'effects');
  },
  chooseAmbient: async()=>{
    const result=await open({directory:false,multiple:false,title:'Выберите ambient-аудио',filters:[{name:'Audio',extensions:['mp3','wav','m4a','aac','flac','ogg','opus']} ]});
    if(typeof result!=='string')return null;
    return importManagedAsset(result,'ambient');
  },
  scanRoot:(path:string)=>invoke<ProjectScanItem[]>('scan_root',{path}),
  enqueue:(projects:ProjectScanItem[],settings:RenderSettings,effects:EffectPreset[],subscribes:SubscribePreset[],ambient?:string)=>invoke<void>('enqueue_projects',{projects,settings,effects,subscribes,ambient}),
  queueSnapshot:()=>invoke<any>('queue_snapshot'),
  reorderQueue:(ids:string[])=>invoke<void>('reorder_queue',{ids}),
  cancelProject:(id:string)=>invoke<void>('cancel_project',{id}),
  generatePreview:(projectPath:string,timeSec:number,effects:EffectPreset[],subscribes:SubscribePreset[])=>invoke<string>('generate_preview',{projectPath,timeSec,effects,subscribes}),
  prepareLivePreview:(projectPath:string,overlaySource:string,timeSec:number)=>invoke<LivePreviewAssetPaths>('prepare_live_preview',{projectPath,overlaySource,timeSec}),
  previewUrl:(path?:string)=>path?convertFileSrc(path):'',
  loadLibrary:()=>invoke<LibraryPayload>('load_library'),
  saveLibrary:(payload:LibraryPayload)=>invoke<void>('save_library',{payload}),
  loadRecovery:()=>invoke<RecoveryPayload>('load_recovery'),
  resumeRecovery:()=>invoke<void>('resume_recovery'),
  dismissRecovery:()=>invoke<void>('dismiss_recovery'),
  benchmark:()=>invoke<BenchmarkResult>('benchmark_engine'),
  activate:(key:string)=>invoke<LicenseStatus>('activate_license',{key}),
  license:()=>invoke<LicenseStatus>('license_status'),
  cacheStats:()=>invoke<{count:number;bytes:number}>('cache_stats'),
  powerStatus:()=>invoke<{supported:boolean;onBattery:boolean;percent?:number|null}>('power_status'),
  diskStatus:(path?:string)=>invoke<{totalBytes:number;freeBytes:number;usedBytes:number;mount:string}>('disk_status',{path:path||null}),
  cleanupDuplicateApps:(aggressive=false)=>invoke<SingleAppStatus>('cleanup_duplicate_apps',{aggressive}),
  normalizeAppName:()=>invoke<{supported:boolean;renamed:boolean;canonicalName:boolean;canonicalInstall?:boolean;currentPath?:string;previousPath?:string;reason?:string}>('normalize_current_app_name'),
  clearCache:()=>invoke<void>('clear_effect_cache'),
  openPath:(p:string)=>invoke<void>('open_result_path',{path:p}),
  reveal:(p:string)=>invoke<void>('reveal_result_path',{path:p}),
  showError:(text:string)=>message(text,{title:'ENDLUME Studio',kind:'error'}),
  showInfo:(text:string)=>message(text,{title:'ENDLUME Studio',kind:'info'}),
  checkUpdate:async()=>{
    const update=await withTimeout(check(),12000,'Проверка обновлений');
    if(!update)return {none:true,current:'1.0.0-alpha.8.18',channel:'alpha',signedUpdater:true};
    let downloaded=0,total=0;
    return {
      version:update.version,
      date:update.date,
      body:update.body||'',
      current:update.currentVersion,
      install:async(onProgress?:(percent:number)=>void)=>{
        const guard=await invoke<SingleAppStatus>('cleanup_duplicate_apps',{aggressive:true}).catch(()=>null);
        if(guard?.supported&&guard.canonicalInstall===false){await invoke('normalize_current_app_name');return;}
        if(guard?.failed?.length){throw new Error(`Не удалось удалить старые копии ENDLUME: ${guard.failed.map(x=>x.path).join(', ')}`);}
        await update.downloadAndInstall((event:any)=>{
          if(event.event==='Started'){total=Number(event.data?.contentLength||0);downloaded=0;onProgress?.(0)}
          else if(event.event==='Progress'){downloaded+=Number(event.data?.chunkLength||0);if(total>0)onProgress?.(Math.min(100,downloaded/total*100))}
          else if(event.event==='Finished'){onProgress?.(100)}
        });
        const after=await invoke<SingleAppStatus>('cleanup_duplicate_apps',{aggressive:true}).catch(()=>null);
        if(after?.failed?.length)console.warn('ENDLUME duplicate cleanup after update',after.failed);
        await relaunch();
      }
    };
  }
};
