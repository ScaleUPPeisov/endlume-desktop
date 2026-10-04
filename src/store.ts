import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AnchorPoint, BackgroundMusicSettings, EffectPreset, LibraryPayload, Page, RenderProject, RenderSettings, SceneAnchors, SubscribePreset } from './types';
import { applyProjectPatch } from './queue-state';

type Editor = null | {kind:'effects'|'subscribe'; id?:string};
interface State {
  page: Page;
  editor: Editor;
  projects: RenderProject[];
  draftProjects: RenderProject[];
  invalidProjects: Array<{name:string;path:string;error:string}>;
  effects: EffectPreset[];
  subscribes: SubscribePreset[];
  ambient?: string;
  ambientSettings: BackgroundMusicSettings;
  settings: RenderSettings;
  lastRoot?: string;
  previewProjectPath?: string;
  libraryLoaded: boolean;
  sceneAnchorsByPath: Record<string, SceneAnchors>;
  setPage:(p:Page)=>void;
  openEditor:(editor:Editor)=>void;
  setProjects:(p:RenderProject[])=>void;
  setDraftProjects:(p:RenderProject[])=>void;
  appendProjects:(p:RenderProject[])=>void;
  syncQueueProjects:(p:RenderProject[])=>void;
  patchProject:(id:string,p:Partial<RenderProject>)=>void;
  removeProject:(id:string)=>void;
  clearFinished:()=>void;
  setInvalidProjects:(v:Array<{name:string;path:string;error:string}>)=>void;
  setEffects:(v:EffectPreset[])=>void;
  setSubscribes:(v:SubscribePreset[])=>void;
  setAmbient:(v?:string)=>void;
  patchAmbientSettings:(v:Partial<BackgroundMusicSettings>)=>void;
  setLibrary:(v:LibraryPayload)=>void;
  setLibraryLoaded:(v:boolean)=>void;
  setSceneAnchor:(projectPath:string,target:string,anchor:AnchorPoint)=>void;
  patchSettings:(p:Partial<RenderSettings>)=>void;
  setLastRoot:(v?:string)=>void;
  setPreviewProjectPath:(v?:string)=>void;
}

export const defaultBackgroundMusicSettings:BackgroundMusicSettings={volumePct:18,bassDb:0,midDb:0,trebleDb:0};

const initialSettings:RenderSettings={
  width:1920,height:1080,fps:60,codec:'h265',bitrateMbps:30,durationHours:2,
  durationMode:'whole-track',loopMode:'image',crossfadeSec:3,normalizeLufs:false,
  outputDir:'',preset:'fast',encoderPreference:'auto'
};

export const useApp=create<State>()(persist((set)=>({
  page:'project',editor:null,projects:[],draftProjects:[],invalidProjects:[],effects:[],subscribes:[],ambientSettings:defaultBackgroundMusicSettings,settings:initialSettings,libraryLoaded:false,sceneAnchorsByPath:{},
  setPage:(page)=>set({page,editor:null}),
  openEditor:(editor)=>set({editor}),
  setProjects:(projects)=>set({projects}),
  setDraftProjects:(draftProjects)=>set({draftProjects}),
  appendProjects:(v)=>set(s=>{const known=new Set(s.projects.map(p=>p.id));return {projects:[...s.projects,...v.filter(n=>!known.has(n.id))]}}),
  syncQueueProjects:(incoming)=>set(s=>{
    const incomingIds=new Set(incoming.map(p=>p.id));
    const oldById=new Map(s.projects.map(p=>[p.id,p]));
    const terminal=s.projects.filter(p=>['done','error'].includes(p.status)&&!incomingIds.has(p.id));
    const live=incoming.map(p=>{const old=oldById.get(p.id);if(!old)return p;if(['done','error'].includes(old.status))return old;return {...old,...p,progress:p.status==='rendering'?Math.max(old.progress||0,p.progress||0):p.progress,stage:p.status==='rendering'&&old.stage?old.stage:p.stage,elapsedSec:p.status==='rendering'?Math.max(old.elapsedSec||0,p.elapsedSec||0):p.elapsedSec}});
    return {projects:[...terminal,...live]};
  }),
  patchProject:(id,patch)=>set(s=>({projects:applyProjectPatch(s.projects,id,patch) as RenderProject[]})),
  removeProject:(id)=>set(s=>({projects:s.projects.filter(p=>p.id!==id)})),
  clearFinished:()=>set(s=>({projects:s.projects.filter(p=>!['done','error'].includes(p.status))})),
  setInvalidProjects:(invalidProjects)=>set({invalidProjects}),
  setEffects:(effects)=>set({effects}),
  setSubscribes:(subscribes)=>set({subscribes}),
  setAmbient:(ambient)=>set({ambient}),
  patchAmbientSettings:(patch)=>set(s=>({ambientSettings:{...s.ambientSettings,...patch}})),
  setLibrary:(v)=>set({effects:(v.effects||[]).map(e=>({...e,despill:e.despill>0?e.despill:0.35})),subscribes:(v.subscribes||[]).map(e=>({...e,despill:e.despill>0?e.despill:0.35})),ambient:v.ambient,ambientSettings:{...defaultBackgroundMusicSettings,...(v.ambientSettings||{})},libraryLoaded:true}),
  setLibraryLoaded:(libraryLoaded)=>set({libraryLoaded}),
  setSceneAnchor:(projectPath,target,anchor)=>set(s=>{
    const key=target.trim().toUpperCase()||'CUSTOM';
    const anchors={...(s.sceneAnchorsByPath[projectPath]||{}),[key]:anchor};
    return {
      sceneAnchorsByPath:{...s.sceneAnchorsByPath,[projectPath]:anchors},
      draftProjects:s.draftProjects.map(p=>p.path===projectPath?{...p,anchors}:p)
    };
  }),
  patchSettings:(patch)=>set(s=>({settings:{...s.settings,...patch}})),
  setLastRoot:(lastRoot)=>set({lastRoot}),
  setPreviewProjectPath:(previewProjectPath)=>set({previewProjectPath})
}),{name:'endlume-1-ui',version:7,migrate:(persisted:any)=>{const p:any=persisted||{};if(p.settings){p.settings={...p.settings,width:1920,height:1080,fps:60,crossfadeSec:3,normalizeLufs:false,codec:'h265'};}p.projects=[];p.sceneAnchorsByPath=p.sceneAnchorsByPath||{};return p;},partialize:(s)=>({settings:s.settings,lastRoot:s.lastRoot,sceneAnchorsByPath:s.sceneAnchorsByPath})}));
