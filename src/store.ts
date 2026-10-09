import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { EffectPreset, LibraryPayload, Page, RenderProject, RenderSettings, SubscribePreset } from './types';

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
  settings: RenderSettings;
  lastRoot?: string;
  libraryLoaded: boolean;
  setPage:(p:Page)=>void;
  openEditor:(editor:Editor)=>void;
  setProjects:(p:RenderProject[])=>void;
  setDraftProjects:(p:RenderProject[])=>void;
  appendProjects:(p:RenderProject[])=>void;
  patchProject:(id:string,p:Partial<RenderProject>)=>void;
  removeProject:(id:string)=>void;
  clearFinished:()=>void;
  setInvalidProjects:(v:Array<{name:string;path:string;error:string}>)=>void;
  setEffects:(v:EffectPreset[])=>void;
  setSubscribes:(v:SubscribePreset[])=>void;
  setAmbient:(v?:string)=>void;
  setLibrary:(v:LibraryPayload)=>void;
  setLibraryLoaded:(v:boolean)=>void;
  patchSettings:(p:Partial<RenderSettings>)=>void;
  setLastRoot:(v?:string)=>void;
}

const initialSettings:RenderSettings={
  width:3840,height:2160,fps:60,codec:'h264',bitrateMbps:30,durationHours:2,
  durationMode:'whole-track',loopMode:'image',crossfadeSec:3,normalizeLufs:false,
  outputDir:'',preset:'fast',encoderPreference:'auto'
};

export const useApp=create<State>()(persist((set)=>({
  page:'project',editor:null,projects:[],draftProjects:[],invalidProjects:[],effects:[],subscribes:[],settings:initialSettings,libraryLoaded:false,
  setPage:(page)=>set({page,editor:null}),
  openEditor:(editor)=>set({editor}),
  setProjects:(projects)=>set({projects}),
  setDraftProjects:(draftProjects)=>set({draftProjects}),
  appendProjects:(v)=>set(s=>({projects:[...s.projects,...v.filter(n=>!s.projects.some(p=>p.path===n.path&&p.status!=='done'))]})),
  patchProject:(id,patch)=>set(s=>({projects:s.projects.map(p=>p.id===id?{...p,...patch}:p)})),
  removeProject:(id)=>set(s=>({projects:s.projects.filter(p=>p.id!==id)})),
  clearFinished:()=>set(s=>({projects:s.projects.filter(p=>!['done','error'].includes(p.status))})),
  setInvalidProjects:(invalidProjects)=>set({invalidProjects}),
  setEffects:(effects)=>set({effects}),
  setSubscribes:(subscribes)=>set({subscribes}),
  setAmbient:(ambient)=>set({ambient}),
  setLibrary:(v)=>set({effects:v.effects||[],subscribes:v.subscribes||[],ambient:v.ambient,libraryLoaded:true}),
  setLibraryLoaded:(libraryLoaded)=>set({libraryLoaded}),
  patchSettings:(patch)=>set(s=>({settings:{...s.settings,...patch}})),
  setLastRoot:(lastRoot)=>set({lastRoot})
}),{name:'endlume-1-ui',partialize:(s)=>({settings:s.settings,lastRoot:s.lastRoot})}));
