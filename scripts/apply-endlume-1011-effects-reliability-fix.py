#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"PATCH_ANCHOR_NOT_FOUND:{path}:{old[:120]!r}")
    if text.count(old) != 1:
        raise SystemExit(f"PATCH_ANCHOR_NOT_UNIQUE:{path}:{text.count(old)}:{old[:120]!r}")
    p.write_text(text.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    p = Path(path)
    text = p.read_text()
    a = text.find(start)
    if a < 0:
        raise SystemExit(f"PATCH_START_NOT_FOUND:{path}:{start!r}")
    b = text.find(end, a)
    if b < 0:
        raise SystemExit(f"PATCH_END_NOT_FOUND:{path}:{end!r}")
    p.write_text(text[:a] + replacement + text[b:])

# Stable per-project production-effect identity travels with the project/queue job.
replace_once(
    'src/types.ts',
    "  anchors?: SceneAnchors;\n}",
    "  anchors?: SceneAnchors;\n  selectedEffectId?: string | null;\n}"
)
replace_once(
    'src-tauri/src/model.rs',
    "  #[serde(default)] pub anchors:Option<HashMap<String,AnchorPoint>>\n}",
    "  #[serde(default)] pub anchors:Option<HashMap<String,AnchorPoint>>,\n  #[serde(default)] pub selected_effect_id:Option<String>\n}"
)

# Persist the selection by physical project path, independently for every project.
replace_once(
    'src/store.ts',
    "  sceneAnchorsByPath: Record<string, SceneAnchors>;\n",
    "  sceneAnchorsByPath: Record<string, SceneAnchors>;\n  selectedEffectByPath: Record<string, string>;\n"
)
replace_once(
    'src/store.ts',
    "  setSceneAnchor:(projectPath:string,target:string,anchor:AnchorPoint)=>void;\n",
    "  setSceneAnchor:(projectPath:string,target:string,anchor:AnchorPoint)=>void;\n  setSelectedEffectForProject:(projectPath:string,effectId:string)=>void;\n"
)
replace_once(
    'src/store.ts',
    "page:'project',editor:null,projects:[],draftProjects:[],invalidProjects:[],effects:[],subscribes:[],settings:initialSettings,libraryLoaded:false,sceneAnchorsByPath:{},",
    "page:'project',editor:null,projects:[],draftProjects:[],invalidProjects:[],effects:[],subscribes:[],settings:initialSettings,libraryLoaded:false,sceneAnchorsByPath:{},selectedEffectByPath:{},"
)
replace_once(
    'src/store.ts',
    "  patchSettings:(patch)=>set(s=>({settings:{...s.settings,...patch}})),",
    "  setSelectedEffectForProject:(projectPath,effectId)=>set(s=>({selectedEffectByPath:{...s.selectedEffectByPath,[projectPath]:effectId}})),\n  patchSettings:(patch)=>set(s=>({settings:{...s.settings,...patch}})),"
)
replace_once(
    'src/store.ts',
    "}),{name:'endlume-1-ui',version:7,migrate:(persisted:any)=>{const p:any=persisted||{};if(p.settings){p.settings={...p.settings,width:1920,height:1080,fps:60,crossfadeSec:3,normalizeLufs:false,codec:'h265'};}p.projects=[];p.sceneAnchorsByPath=p.sceneAnchorsByPath||{};return p;},partialize:(s)=>({settings:s.settings,lastRoot:s.lastRoot,sceneAnchorsByPath:s.sceneAnchorsByPath})}));",
    "}),{name:'endlume-1-ui',version:8,migrate:(persisted:any)=>{const p:any=persisted||{};if(p.settings){p.settings={...p.settings,width:1920,height:1080,fps:60,crossfadeSec:3,normalizeLufs:false,codec:'h265'};}p.projects=[];p.sceneAnchorsByPath=p.sceneAnchorsByPath||{};p.selectedEffectByPath=p.selectedEffectByPath||{};return p;},partialize:(s)=>({settings:s.settings,lastRoot:s.lastRoot,sceneAnchorsByPath:s.sceneAnchorsByPath,selectedEffectByPath:s.selectedEffectByPath})}));"
)

# Project page: all registry entries remain visible, but render selection is explicit and per project.
replace_once(
    'src/pages/ProjectPage.tsx',
    "const imageExt=new Set(['jpg','jpeg','png','webp','bmp','tif','tiff','heic','avif']);",
    "const NO_EFFECT_SELECTION='__none__';\nconst imageExt=new Set(['jpg','jpeg','png','webp','bmp','tif','tiff','heic','avif']);"
)
replace_once(
    'src/pages/ProjectPage.tsx',
    "    settings,patchSettings,effects,subscribes,ambient,setAmbient,openEditor,setPage,setLastRoot\n",
    "    settings,patchSettings,effects,subscribes,ambient,setAmbient,openEditor,setPage,setLastRoot,\n    selectedEffectByPath,setSelectedEffectForProject\n"
)
replace_once(
    'src/pages/ProjectPage.tsx',
    "  const setFeature=(key:keyof FeatureFlags,value:boolean)=>setFeatures(prev=>{const next={...prev,[key]:value};localStorage.setItem(featureKey,JSON.stringify(next));return next});\n",
    "  const setFeature=(key:keyof FeatureFlags,value:boolean)=>setFeatures(prev=>{const next={...prev,[key]:value};localStorage.setItem(featureKey,JSON.stringify(next));return next});\n  const enabledEffects=effects.filter(e=>e.enabled);\n  const effectIdCounts=effects.reduce<Record<string,number>>((acc,e)=>{const id=e.id.trim();if(id)acc[id]=(acc[id]||0)+1;return acc},{});\n  const duplicateEffectIds=Object.entries(effectIdCounts).filter(([,count])=>count>1).map(([id])=>id);\n  const selectedEffectIdForPath=(path:string)=>selectedEffectByPath[path]||(enabledEffects.length===1?enabledEffects[0].id:'');\n"
)

new_enqueue = r'''  const enqueue=async()=>{
    if(!draftProjects.length)return;
    if(!settings.outputDir){await api.showError('Сначала выберите папку результата.');return}
    try{
      try{
        const power=await api.powerStatus();
        if(power.supported&&power.onBattery){
          await api.showInfo(`MacBook работает от аккумулятора${power.percent!=null?` (${power.percent}%)`:''}. ENDLUME продолжит рендер на полной мощности — подключите питание, если очередь большая.`);
        }
      }catch{}

      const effectRegistry=features.effects?effects:[];
      if(features.effects&&duplicateEffectIds.length){
        throw new Error(`Effects registry повреждён: повторяются ID ${duplicateEffectIds.join(', ')}. ENDLUME не будет угадывать или рендерить не тот эффект.`);
      }
      const activeSubscribes=features.subscribe?subscribes.filter(e=>e.enabled):[];
      const activeAmbient=features.ambient?ambient:undefined;
      const resolved=draftProjects.map(project=>{
        if(!features.effects)return {project,selectedEffect:undefined};
        const selectedId=selectedEffectIdForPath(project.path);
        if(!selectedId){
          throw new Error(`Выберите эффект для проекта «${project.name}» или явно укажите «Без эффекта».`);
        }
        if(selectedId===NO_EFFECT_SELECTION)return {project,selectedEffect:undefined};
        const selectedEffect=effectRegistry.find(effect=>effect.id===selectedId);
        if(!selectedEffect){
          throw new Error(`Эффект ${selectedId} для проекта «${project.name}» больше не существует. Выберите эффект заново.`);
        }
        return {project,selectedEffect};
      });
      const fastStaticProjects=resolved.filter(({project,selectedEffect})=>project.media.length>0&&project.media.every(isImagePath)&&(project.media.length===1||(!selectedEffect&&activeSubscribes.length===0)));
      if(fastStaticProjects.length&&(settings.crossfadeSec>0||settings.normalizeLufs||!!activeAmbient)){
        await api.showInfo(`Processed Audio включён для ${fastStaticProjects.length} статичных проектов. Быстрый visual/manifest pipeline сохраняется, но музыка будет реально декодирована и обработана (crossfade / LUFS / ambient), поэтому MP3 packet-copy отключается и рендер может быть медленнее или больше. Чтобы получить Original MP3 bitstream-copy, выключите audio processing.`);
      }
      const stamp=Date.now().toString(36);
      const queuedProjects=resolved.map(({project,selectedEffect},i)=>({...project,selectedEffectId:selectedEffect?.id||NO_EFFECT_SELECTION,id:`${project.id}-${stamp}-${i}-${Math.random().toString(36).slice(2,8)}`,status:'queued' as const,progress:0,stage:'Ожидает в очереди',elapsedSec:0}));
      await api.enqueue(queuedProjects,settings,effectRegistry,activeSubscribes,activeAmbient);
      appendProjects(queuedProjects);
      setDraftProjects([]);setInvalidProjects([]);setScanNote('');setPage('render');
    }catch(e){await api.showError(String(e))}
  };
'''
replace_between('src/pages/ProjectPage.tsx', '  const enqueue=async()=>{', '\n\n  return <div className="projectColumn">', new_enqueue)

start = '    <section className="sectionBlock">\n      <div className="sectionTitle">ЭФФЕКТЫ</div>'
end = '    <section className="sectionBlock">\n      <div className="sectionTitle">BACKGROUND MUSIC</div>'
new_effect_ui = r'''    <section className="sectionBlock">
      <div className="sectionTitle">ЭФФЕКТЫ</div>
      <div className="featureRow"><span className="featureIcon blue"><Icon name="effects"/></span><div><b>Эффект для каждого проекта</b><small>{!features.effects?'Отключено для текущих рендеров':effects.length?`Доступно: ${effects.length} • выбор сохраняется отдельно для каждого проекта`:'Эффекты не найдены'}</small></div><div className="rowButtons"><button onClick={()=>setFeature('effects',!features.effects)}>{features.effects?'ВЫКЛЮЧИТЬ':'ВКЛЮЧИТЬ'}</button><button onClick={()=>openEditor({kind:'effects'})}>НАСТРОИТЬ →</button></div></div>
      {features.effects&&duplicateEffectIds.length>0&&<div className="validationBox"><b>Effects registry заблокирован:</b><div>Одинаковый ID назначен нескольким эффектам: {duplicateEffectIds.join(', ')}. Рендер с эффектами запрещён, чтобы ENDLUME не подставил другой эффект.</div></div>}
      {features.effects&&draftProjects.length>0&&effects.length>0&&<div className="renderCard">
        <div className="optionGroup"><span>Применить ко всем найденным проектам</span><div className="chipRow"><button onClick={()=>draftProjects.forEach(p=>setSelectedEffectForProject(p.path,NO_EFFECT_SELECTION))}>БЕЗ ЭФФЕКТА</button>{effects.map((effect,index)=><button key={`all-${effect.id}-${index}`} disabled={duplicateEffectIds.includes(effect.id)} onClick={()=>draftProjects.forEach(p=>setSelectedEffectForProject(p.path,effect.id))}>{effect.name}</button>)}</div></div>
        {draftProjects.map(project=><div className="optionGroup" key={`effect-${project.path}`}><span>{project.name}</span><div className="chipRow"><button className={selectedEffectIdForPath(project.path)===NO_EFFECT_SELECTION?'selected':''} onClick={()=>setSelectedEffectForProject(project.path,NO_EFFECT_SELECTION)}>БЕЗ ЭФФЕКТА</button>{effects.map((effect,index)=><button key={`${project.path}-${effect.id}-${index}`} disabled={duplicateEffectIds.includes(effect.id)} className={selectedEffectIdForPath(project.path)===effect.id&&!duplicateEffectIds.includes(effect.id)?'selected':''} onClick={()=>setSelectedEffectForProject(project.path,effect.id)}>{effect.name}</button>)}</div></div>)}
      </div>}
    </section>
'''
replace_between('src/pages/ProjectPage.tsx', start, end, new_effect_ui)

# Backend: treat effects argument as a registry, validate it once, resolve one selected effect per project,
# and reject missing assets before mutating the queue. This makes enqueue atomic and fail-closed.
queue = Path('src-tauri/src/queue.rs')
text = queue.read_text()
old_fn_start = '#[tauri::command]\npub async fn enqueue_projects'
start_i = text.find(old_fn_start)
if start_i < 0:
    raise SystemExit('QUEUE_ENQUEUE_START_NOT_FOUND')
end_marker = '\n\nfn useful_detail'
end_i = text.find(end_marker, start_i)
if end_i < 0:
    raise SystemExit('QUEUE_ENQUEUE_END_NOT_FOUND')
new_fn = r'''#[tauri::command]
pub async fn enqueue_projects(app:AppHandle,runtime:State<'_,Arc<QueueRuntime>>,projects:Vec<ProjectScanItem>,settings:RenderSettings,effects:Vec<EffectPreset>,subscribes:Vec<SubscribePreset>,ambient:Option<String>)->Result<(),String>{
  license::assert_production_allowed(&app).await?;
  if settings.output_dir.trim().is_empty(){return Err("Не выбрана папка результата".into())}

  let mut effect_ids=HashSet::new();
  for effect in &effects{
    let id=effect.id.trim();
    if id.is_empty(){return Err(format!("Effects registry invalid: effect '{}' has empty ID",effect.name))}
    if !effect_ids.insert(id.to_string()){
      return Err(format!("Effects registry invalid: duplicate effect ID '{}'. Render blocked to prevent wrong-effect substitution.",id))
    }
  }

  let mut prepared=Vec::<(ProjectScanItem,Vec<EffectPreset>)>::new();
  for project in projects.into_iter().filter(|p|p.valid){
    let selected_id=project.selected_effect_id.as_deref().map(str::trim).filter(|x|!x.is_empty()).unwrap_or("__none__");
    let selected=if selected_id=="__none__"{
      Vec::new()
    }else{
      let effect=effects.iter().find(|e|e.id==selected_id).ok_or_else(||format!("Selected effect '{}' for project '{}' is not present in the effect registry",selected_id,project.name))?;
      let source=PathBuf::from(&effect.source);
      if !source.is_file(){
        return Err(format!("Selected effect '{}' ({}) for project '{}' is missing: {}",effect.name,effect.id,project.name,source.display()))
      }
      vec![effect.clone()]
    };
    prepared.push((project,selected));
  }

  {
    let active=runtime.active.lock();
    let mut q=runtime.pending.lock();
    let mut occupied=q.iter().map(|j|j.project.id.clone()).collect::<HashSet<_>>();
    if let Some(job)=active.as_ref(){occupied.insert(job.project.id.clone());}
    for (project,selected_effects) in prepared{
      if !occupied.insert(project.id.clone()){continue}
      runtime.clear_terminal(&project.id);
      q.push_back(QueueJob{project,settings:settings.clone(),effects:selected_effects,subscribes:subscribes.clone(),ambient:ambient.clone()});
    }
  }
  runtime.persist(&app);let _=app.emit("queue-changed",queue_snapshot_value(runtime.inner().as_ref()));start_worker_if_needed(app,runtime.inner().clone());Ok(())
}'''
text = text[:start_i] + new_fn + text[end_i:]
text = text.replace(
    'if low.contains("colorkey")||low.contains("chromakey")||low.contains("overlay"){return "Ошибка обработки Effects/Subscribe. Проблемный overlay должен быть пропущен без остановки основного видео.".into()}',
    'if low.contains("colorkey")||low.contains("chromakey")||low.contains("overlay"){return "Ошибка обработки Effects/Subscribe. ENDLUME не подменяет и не скрывает выбранный production-effect: проект остановлен с ошибкой.".into()}',
    1,
)
queue.write_text(text)

# Strengthen the physical diagnostic: raw row count is not enough. Require 3 unique stable IDs
# and reject ephemeral macOS temp assets as production effects.
diag = Path('scripts/diag-endlume-1011-performance-effects-reliability.py')
text = diag.read_text()
text = text.replace(
    "report={'sourceSha':'2e4e958d08927eaf098dc348fdfaed34ecb92b56','project':str(project),'libraryPath':str(lib_path),'effectInventory':inventory,'realEffectCount':len(real_effects),'subscribePresent':bool(subs),'results':results,'threeEffectGate':len(real_effects)==3}",
    "unique_effect_ids=sorted({str(e.get('id','')).strip() for e in real_effects if str(e.get('id','')).strip()})\nephemeral_effects=[row for row in inventory if row.get('exists') and ('/var/folders/' in str(row.get('source','')) or '/tmp/' in str(row.get('source','')))]\neffect_identity_gate=len(real_effects)==3 and len(unique_effect_ids)==3\nproduction_asset_gate=len(ephemeral_effects)==0\nthree_effect_gate=effect_identity_gate and production_asset_gate\nreport={'sourceSha':'2e4e958d08927eaf098dc348fdfaed34ecb92b56','project':str(project),'libraryPath':str(lib_path),'effectInventory':inventory,'realEffectCount':len(real_effects),'uniqueEffectIds':unique_effect_ids,'effectIdentityGate':effect_identity_gate,'ephemeralEffects':ephemeral_effects,'productionAssetGate':production_asset_gate,'subscribePresent':bool(subs),'results':results,'threeEffectGate':three_effect_gate}",
    1,
)
text = text.replace(
    "print('THREE_EFFECT_GATE='+('PASS' if len(real_effects)==3 else 'BLOCKED'))",
    "print('UNIQUE_EFFECT_IDS='+json.dumps(unique_effect_ids,ensure_ascii=False))\nprint('EFFECT_IDENTITY_GATE='+('PASS' if effect_identity_gate else 'BLOCKED'))\nprint('PRODUCTION_ASSET_GATE='+('PASS' if production_asset_gate else 'BLOCKED'))\nprint('THREE_EFFECT_GATE='+('PASS' if three_effect_gate else 'BLOCKED'))",
    1,
)
if 'effectIdentityGate' not in text:
    raise SystemExit('DIAGNOSTIC_PATCH_FAILED')
diag.write_text(text)

print('ENDLUME_10_0_11_EFFECT_RELIABILITY_PATCH_APPLIED=YES')
