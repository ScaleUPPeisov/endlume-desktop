import { invoke, convertFileSrc } from '@tauri-apps/api/core';
import { open, message } from '@tauri-apps/plugin-dialog';
import { getVersion } from '@tauri-apps/api/app';
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
export type VyronBatchRequest={batchId:string;manifestPath:string;requestedAt?:string|null;handoffId?:string|null;selectedProjectIds?:string[];sourceManifestPath?:string|null;schemaVersion?:number|null};
export type VyronBatchInfo={batchId:string;channelId:string;channelName:string;projectCount:number;tracksAssigned:number;rootPath:string;outputDir:string;statusPath:string;manifestPath:string;projectPaths:string[]};
type NativeUpdateInfo={supported:boolean;available:boolean;current:string;version?:string|null;notes?:string|null;date?:string|null;reason?:string|null};
type NativeUpdateStatus={state:string;stage?:string|null;progress:number;message?:string|null;logPath?:string|null};

const isWindowsRuntime=()=>/Windows/i.test(navigator.userAgent);
const isMacRuntime=()=>/Macintosh|Mac OS X/i.test(navigator.userAgent);
const productTitle=()=>'ENDLUME YT Studio PEISOV';

async function withTimeout<T>(promise:Promise<T>,ms:number,label:string):Promise<T>{
  let timer:number|undefined;
  try{return await Promise.race([promise,new Promise<T>((_,reject)=>{timer=window.setTimeout(()=>reject(new Error(`${label}: превышено время ожидания ${Math.round(ms/1000)} сек`)),ms)})]);}
  finally{if(timer!==undefined)window.clearTimeout(timer)}
}

async function importManagedAsset(source:string,kind:'effects'|'subscribe'|'ambient'){
  return invoke<string>('import_library_asset',{source,kind});
}

async function nativeUpdateInstall(onProgress?:(percent:number,stage?:string)=>void){
  onProgress?.(1,'Подготавливаю подписанное обновление');
  let stopped=false;
  const poll=async()=>{
    while(!stopped){
      try{
        const s=await invoke<NativeUpdateStatus>('local_update_status');
        onProgress?.(Math.max(0,Math.min(100,Number(s.progress)||0)),s.stage||undefined);
        if(s.state==='failed')throw new Error(s.message||'Windows update failed');
        if(s.state==='success')return;
      }catch(e){if(String(e).includes('Windows update failed'))throw e;}
      await new Promise(r=>window.setTimeout(r,250));
    }
  };
  const install=invoke<NativeUpdateStatus>('local_update_start');
  const poller=poll();
  try{
    const done=await install;
    onProgress?.(Math.max(0,Math.min(100,Number(done.progress)||100)),done.stage||'Обновление установлено');
    stopped=true;
    await poller.catch(()=>{});
  }finally{stopped=true;}
}

export const api = {
  isWindows:isWindowsRuntime,
  chooseRoots: async()=>{
    const result=await open({directory:true,multiple:true,title:'Выберите папку или несколько папок с проектами'});
    if(!result)return [] as string[];
    return Array.isArray(result)?result:[result];
  },
  chooseOutput: async()=>{
    const result=await open({directory:true,multiple:false,title:'Папка для готовых видео'});
    return typeof result==='string'?result:null;
  },
  chooseVideo: async(kind:'effects'|'subscribe'='effects')=>{
    const result=await open({directory:false,multiple:false,title:kind==='subscribe'?'Выберите Subscribe-видео':'Выберите видео эффекта',filters:[{name:'Video',extensions:['mp4','mov','m4v','mkv','webm','avi','wmv','flv','ts','mts','m2ts','mpg','mpeg','vob','3gp']} ]});
    if(typeof result!=='string')return null;
    return importManagedAsset(result,kind);
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
  consumeVyronBatch:()=>invoke<VyronBatchRequest|null>('consume_vyron_batch_request'),
  loadVyronBatch:(manifestPath:string,selectedProjectIds:string[]=[])=>invoke<VyronBatchInfo>('load_vyron_batch_manifest',{manifestPath,selectedProjectIds}),
  reportVyronRender:(manifestPath:string,projectPath:string,renderStatus:string,outputFile?:string|null,duration?:number|null,fileSize?:number|null,error?:string|null)=>invoke<void>('report_vyron_render',{manifestPath,projectPath,renderStatus,outputFile:outputFile??null,duration:duration??null,fileSize:fileSize??null,error:error??null}),
  showError:(text:string)=>message(text,{title:productTitle(),kind:'error'}),
  showInfo:(text:string)=>message(text,{title:productTitle(),kind:'info'}),
  checkUpdate:async()=>{
    const current=await getVersion();
    if(isWindowsRuntime()||isMacRuntime()){
      const u=await withTimeout(invoke<NativeUpdateInfo>('local_update_check'),20000,'Проверка обновлений');
      if(!u.available||!u.version)return {none:true,current,channel:'signed-sha256',reason:u.reason||undefined};
      if(u.reason)throw new Error(u.reason);
      return {
        version:u.version,
        date:u.date||'',
        body:u.notes||'',
        current,
        channel:'signed-sha256',
        install:nativeUpdateInstall
      };
    }
    return {none:true,current,channel:'unsupported'};
  },
  updateStatus:async()=>invoke<NativeUpdateStatus>('local_update_status')
};
