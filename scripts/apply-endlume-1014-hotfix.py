#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one literal match, got {count}")
    write(path, text.replace(old, new, 1))


def regex_once(path: str, pattern: str, replacement: str) -> None:
    text = read(path)
    next_text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one regex match, got {count}: {pattern[:80]}")
    write(path, next_text)


# Idempotence for accidental workflow re-run.
if "outputSource?: 'vyron'|'manual'" in read("src/types.ts"):
    print("ENDLUME 10.0.14 hotfix already applied")
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# BUG 1: carry the VYRON destination with each imported project / queue job.
# ---------------------------------------------------------------------------
replace_once(
    "src/types.ts",
    "  selectedEffectId?: string;\n}",
    "  selectedEffectId?: string;\n  outputDir?: string;\n  outputSource?: 'vyron'|'manual';\n  vyronManifestPath?: string;\n  vyronChannelName?: string;\n}",
)

replace_once(
    "src-tauri/src/model.rs",
    "  #[serde(default)] pub selected_effect_id:Option<String>\n}",
    "  #[serde(default)] pub selected_effect_id:Option<String>,\n  #[serde(default)] pub output_dir:Option<String>,\n  #[serde(default)] pub output_source:Option<String>,\n  #[serde(default)] pub vyron_manifest_path:Option<String>,\n  #[serde(default)] pub vyron_channel_name:Option<String>\n}",
)

replace_once(
    "src/components/VyronBatchBridge.tsx",
    "            if(item?.valid)valid.push({...item,status:'queued',progress:0,stage:'Получено из VYRON',elapsedSec:0});",
    "            if(item?.valid)valid.push({...item,outputDir:info.outputDir,outputSource:'vyron',vyronManifestPath:info.manifestPath,vyronChannelName:info.channelName,status:'queued',progress:0,stage:'Получено из VYRON',elapsedSec:0});",
)
replace_once(
    "src/components/VyronBatchBridge.tsx",
    "        const st=useApp.getState();st.setDraftProjects(valid);st.setInvalidProjects(invalid);st.patchSettings({outputDir:info.outputDir});st.setLastRoot(info.rootPath);st.setPage('project');",
    "        const st=useApp.getState();st.setDraftProjects(valid);st.setInvalidProjects(invalid);st.setPreviewProjectPath(valid[0]?.path);st.setLastRoot(info.rootPath);st.setPage('project');",
)

# The original VYRON contract uses batch.json.outputDir. 10.0.13 reconstructed
# Render/<channel> before considering that canonical manifest value. Prefer the
# declared destination and keep the reconstruction only as compatibility fallback.
regex_once(
    "src-tauri/src/vyron_bridge.rs",
    r"fn resolve_render_output\(v:&Value,batch_root:&Path,channel_name:&str\)->Result<PathBuf,String>\{.*?\n\}\n\n#\[derive\(Clone,Debug,Serialize,Deserialize\)\]",
    r'''fn validate_output_writable(output:&Path)->Result<(),String>{
  let stamp=SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).unwrap_or_default().as_nanos();
  let probe=output.join(format!(".endlume-write-test-{}-{stamp}",std::process::id()));
  match fs::OpenOptions::new().write(true).create_new(true).open(&probe){
    Ok(_)=>{let _=fs::remove_file(&probe);Ok(())}
    Err(e)=>Err(format!("Папка результата VYRON недоступна для записи: {} ({e})",output.display()))
  }
}
fn validate_output_scope(output:&Path,batch_root:&Path)->Result<(),String>{
  if let Some(workspace)=vyron_workspace_root(batch_root){
    let workspace=workspace.canonicalize().map_err(|e|format!("VYRON workspace: {e}"))?;
    if !output.starts_with(&workspace){return Err(format!("Output VYRON находится вне workspace: {}",output.display()))}
  }else if !output.starts_with(batch_root){
    return Err(format!("Output VYRON находится вне batch root: {}",output.display()))
  }
  Ok(())
}
fn resolve_render_output(v:&Value,batch_root:&Path,channel_name:&str)->Result<PathBuf,String>{
  // Canonical contract: VYRON owns outputDir in batch.json. Never reconstruct a
  // different folder when the manifest already supplied the destination.
  if let Some(raw)=v.get("outputDir").and_then(Value::as_str).map(str::trim).filter(|x|!x.is_empty()){
    let output=PathBuf::from(raw);
    fs::create_dir_all(&output).map_err(|e|format!("Output dir '{}': {e}",output.display()))?;
    let output=output.canonicalize().map_err(|e|format!("Output dir '{}': {e}",output.display()))?;
    validate_output_scope(&output,batch_root)?;
    validate_output_writable(&output)?;
    return Ok(output)
  }

  // Compatibility fallback for a newer workspace handoff that genuinely omits
  // outputDir. This is not allowed to override an explicit manifest destination.
  if let Some(workspace)=vyron_workspace_root(batch_root){
    let output=workspace.join("Render").join(safe_channel_folder(channel_name));
    fs::create_dir_all(&output).map_err(|e|format!("Render/<channel>: {e}"))?;
    let workspace=workspace.canonicalize().map_err(|e|format!("VYRON workspace: {e}"))?;
    let output=output.canonicalize().map_err(|e|format!("Render/<channel>: {e}"))?;
    if !output.starts_with(&workspace){return Err("Render VYRON находится вне workspace".into())}
    validate_output_writable(&output)?;
    return Ok(output)
  }
  Err("VYRON batch.json не содержит outputDir и не находится в ProductionManager workspace".into())
}

#[derive(Clone,Debug,Serialize,Deserialize)]''',
)

# Queue each resolved destination with its own immutable RenderSettings snapshot.
regex_once(
    "src/pages/ProjectPage.tsx",
    r"  const enqueue=async\(\)=>\{.*?\n  \};\n\n  return <div className=\"projectColumn\">",
    r'''  const enqueue=async()=>{
    if(!draftProjects.length)return;
    try{
      const resolvedDestination=(project:RenderProject)=>project.outputDir?.trim()||settings.outputDir.trim();
      const missingDestination=draftProjects.find(project=>!resolvedDestination(project));
      if(missingDestination){throw new Error(`Для проекта «${missingDestination.name}» не выбрана папка результата. VYRON destination отсутствует — выберите папку вручную.`);}
      try{const power=await api.powerStatus();if(power.supported&&power.onBattery){await api.showInfo(`MacBook работает от аккумулятора${power.percent!=null?` (${power.percent}%)`:''}. ENDLUME продолжит рендер на полной мощности — подключите питание, если очередь большая.`);}}catch{}
      const effectRegistry=features.effects?selectableEffects:[];
      if(features.effects&&duplicateEffectIds.length){throw new Error(`Effects registry повреждён: повторяются ID ${duplicateEffectIds.join(', ')}. ENDLUME не будет угадывать или рендерить не тот эффект.`);}
      const brokenActiveSubscribes=features.subscribe?subscribes.filter(item=>item.enabled&&item.usageMode!=='off'&&effectNeedsRepair(item)):[];
      if(brokenActiveSubscribes.length){throw new Error(`Subscribe требует восстановления файла: ${brokenActiveSubscribes.map(item=>item.name).join(', ')}. ENDLUME не будет запускать рендер с отсутствующим Subscribe asset.`);}
      const activeSubscribes=features.subscribe?activeSubscribesReady:[];
      const activeAmbient=features.ambient?ambient:undefined;
      const resolved=draftProjects.map(project=>{
        if(!features.effects)return {project,selectedEffect:undefined};
        const selectedId=selectedEffectIdForPath(project.path);
        if(!selectedId){throw new Error(`Выберите эффект для проекта «${project.name}» или явно укажите «Без эффекта».`);}
        if(selectedId===NO_EFFECT_SELECTION)return {project,selectedEffect:undefined};
        const persistedEffect=effects.find(effect=>effect.id===selectedId);
        if(!persistedEffect){throw new Error(`Сохранённый effect ID ${selectedId} для проекта «${project.name}» больше не существует. Возможна migration старого duplicate ID. ENDLUME не будет угадывать замену — выберите эффект заново.`);}
        if(effectNeedsRepair(persistedEffect)){throw new Error(`Эффект «${persistedEffect.name}» (${persistedEffect.id}) требует восстановления файла. ${persistedEffect.assetError||'Выберите исходный файл заново в настройках Effects.'}`);}
        if(!persistedEffect.enabled||persistedEffect.usageMode==='off'){throw new Error(`Эффект «${persistedEffect.name}» (${persistedEffect.id}) выключен. Включите его или выберите другой эффект.`);}
        const selectedEffect=effectRegistry.find(effect=>effect.id===selectedId);
        if(!selectedEffect){throw new Error(`Эффект ${selectedId} для проекта «${project.name}» недоступен. ENDLUME не будет подставлять другой эффект.`);}
        return {project,selectedEffect};
      });
      const fastStaticProjects=resolved.filter(({project,selectedEffect})=>project.media.length>0&&project.media.every(isImagePath)&&(project.media.length===1||(!selectedEffect&&activeSubscribes.length===0)));
      if(fastStaticProjects.length&&(settings.crossfadeSec>0||settings.normalizeLufs||!!activeAmbient)){
        await api.showInfo(`Processed Audio включён для ${fastStaticProjects.length} статичных проектов. Быстрый visual/manifest pipeline сохраняется, но музыка будет реально декодирована и обработана (crossfade / LUFS / ambient), поэтому MP3 packet-copy отключается и рендер может быть медленнее или больше. Чтобы получить Original MP3 bitstream-copy, выключите audio processing.`);
      }
      const stamp=Date.now().toString(36);
      const queuedProjects=resolved.map(({project,selectedEffect},i)=>({...project,selectedEffectId:selectedEffect?.id||NO_EFFECT_SELECTION,id:`${project.id}-${stamp}-${i}-${Math.random().toString(36).slice(2,8)}`,status:'queued' as const,progress:0,stage:'Ожидает в очереди',elapsedSec:0}));
      const groups=new Map<string,typeof queuedProjects>();
      for(const project of queuedProjects){
        const outputDir=resolvedDestination(project);
        const group=groups.get(outputDir)||[];group.push(project);groups.set(outputDir,group);
      }
      for(const [outputDir,projects] of groups){
        await api.enqueue(projects,{...settings,outputDir},effectRegistry,activeSubscribes,activeAmbient,ambientSettings);
      }
      appendProjects(queuedProjects);setDraftProjects([]);setPreviewProjectPath(undefined);setInvalidProjects([]);setScanNote('');setPage('render');
    }catch(e){await api.showError(String(e))}
  };

  return <div className="projectColumn">''',
)

# Real selected state for the batch chips + explicit stale-selection recovery.
replace_once(
    "src/pages/ProjectPage.tsx",
    "<div className=\"optionGroup\"><span>Применить ко всем найденным проектам</span><div className=\"chipRow\"><button onClick={()=>draftProjects.forEach(p=>setSelectedEffectForProject(p.path,NO_EFFECT_SELECTION))}>БЕЗ ЭФФЕКТА</button>{effects.map((effect,index)=>{const selectable=effectIsSelectable(effect)&&!duplicateEffectIds.includes(effect.id);return <button key={`all-${effect.id}-${index}`} disabled={!selectable} title={effect.assetError||effectStatusLabel(effect)} onClick={()=>selectable&&draftProjects.forEach(p=>setSelectedEffectForProject(p.path,effect.id))}>{effect.name} • {effectStatusLabel(effect)}</button>})}</div></div>",
    "<div className=\"optionGroup\"><span>Применить ко всем найденным проектам</span><div className=\"chipRow\"><button className={draftProjects.every(p=>selectedEffectIdForPath(p.path)===NO_EFFECT_SELECTION)?'selected':''} onClick={()=>draftProjects.forEach(p=>setSelectedEffectForProject(p.path,NO_EFFECT_SELECTION))}>БЕЗ ЭФФЕКТА</button>{effects.map((effect,index)=>{const selectable=effectIsSelectable(effect)&&!duplicateEffectIds.includes(effect.id);const selectedForAll=draftProjects.every(p=>selectedEffectIdForPath(p.path)===effect.id);return <button key={`all-${effect.id}-${index}`} className={selectedForAll?'selected':''} disabled={!selectable} title={effect.assetError||effectStatusLabel(effect)} onClick={()=>selectable&&draftProjects.forEach(p=>setSelectedEffectForProject(p.path,effect.id))}>{effect.name} • {effectStatusLabel(effect)}</button>})}</div></div>",
)
replace_once(
    "src/pages/ProjectPage.tsx",
    "{selectionIssue&&<small>⚠ {selectionIssue}</small>}",
    "{selectionIssue&&<small>⚠ {selectionIssue} <button type=\"button\" onClick={()=>setSelectedEffectForProject(project.path,NO_EFFECT_SELECTION)}>СБРОСИТЬ → БЕЗ ЭФФЕКТА</button></small>}",
)

# AUTO/VYRON output is visible and immutable; manual picker remains the fallback.
replace_once(
    "src/pages/ProjectPage.tsx",
    "      <div className=\"sectionTitle outputTitle\">СОХРАНИТЬ В</div>\n      <button className=\"outputPicker\" onClick={async()=>{const p=await api.chooseOutput();if(p)patchSettings({outputDir:p})}}><Icon name=\"folder\"/><b>Нажмите для выбора папки результата</b><small>{settings.outputDir||'Папка не выбрана'}</small></button>",
    "      <div className=\"sectionTitle outputTitle\">СОХРАНИТЬ В</div>\n      {(()=>{const auto=Array.from(new Set(draftProjects.filter(p=>p.outputSource==='vyron'&&p.outputDir).map(p=>p.outputDir as string)));const needsManual=!draftProjects.length||draftProjects.some(p=>!p.outputDir);return <><button className=\"outputPicker\" disabled={!needsManual} onClick={async()=>{if(!needsManual)return;const p=await api.chooseOutput();if(p)patchSettings({outputDir:p})}}><Icon name=\"folder\"/><b>{auto.length&&!needsManual?'AUTO • VYRON':'Нажмите для выбора папки результата'}</b><small>{auto.length===1&&!needsManual?auto[0]:auto.length>1&&!needsManual?`${auto.length} VYRON destinations • каждая очередь сохранит свой путь`:settings.outputDir||'Папка не выбрана'}</small></button>{auto.length>0&&<div className=\"validationBox\"><b>VYRON destination:</b>{auto.map(path=><div key={path}>{path}</div>)}</div>}</>})()}",
)

# ---------------------------------------------------------------------------
# BUG 3/4: preview must not depend on the expensive exact poster, must fail
# boundedly, and VYRON imported projects must provide a scene to Subscribe.
# ---------------------------------------------------------------------------
replace_once(
    "src/pages/Editors.tsx",
    "const previewDiag = (scope:'effects'|'subscribe',phase:'START'|'FINISH'|'APPLY'|'DISCARD',request:number,extra:Record<string,unknown>={}) => console.info('[ENDLUME_PREVIEW]',{scope,phase,request,...extra});",
    "const previewDiag = (scope:'effects'|'subscribe',phase:'START'|'FINISH'|'APPLY'|'DISCARD',request:number,extra:Record<string,unknown>={}) => console.info('[ENDLUME_PREVIEW]',{scope,phase,request,...extra});\nconst PREVIEW_TIMEOUT_MS=12000;\nfunction previewWithTimeout<T>(promise:Promise<T>,label:string):Promise<T>{return new Promise((resolve,reject)=>{const timer=window.setTimeout(()=>reject(new Error(`${label}: timeout ${PREVIEW_TIMEOUT_MS/1000}s`)),PREVIEW_TIMEOUT_MS);promise.then(value=>{window.clearTimeout(timer);resolve(value)},error=>{window.clearTimeout(timer);reject(error)})})}",
)

# Effects preview state + load pipeline.
replace_once(
    "src/pages/Editors.tsx",
    "  const [previewBusy, setPreviewBusy] = useState(false);\n  const [anchorMode, setAnchorMode] = useState(false);",
    "  const [previewBusy, setPreviewBusy] = useState(false);\n  const [previewError, setPreviewError] = useState<string>();\n  const [anchorMode, setAnchorMode] = useState(false);",
)
replace_once(
    "src/pages/Editors.tsx",
    "  const invalidatePreview=()=>{previewRequest.current+=1;setAssets(undefined);setPreviewSnapshot(undefined);};",
    "  const invalidatePreview=()=>{previewRequest.current+=1;setAssets(undefined);setPreviewSnapshot(undefined);setPreviewError(undefined);};",
)
regex_once(
    "src/pages/Editors.tsx",
    r"  const loadLive = async \(request = \+\+previewRequest\.current\) => \{\n    const latest = useApp\.getState\(\)\.effects\.find\(\(e\) => e\.id === selected\);.*?\n  \};\n\n  useEffect\(\(\) => \{\n    if \(!current \|\| !projectPath\) return;\n    const request=\+\+previewRequest\.current;\n    const timer = window\.setTimeout\(\(\) => void loadLive\(request\), 180\);\n    return \(\) => window\.clearTimeout\(timer\);\n  \}, \[.*?\n  \]\);",
    r'''  const loadLive = async (request = ++previewRequest.current) => {
    const latest = useApp.getState().effects.find((e) => e.id === selected);
    if (!projectPath || !latest) { setAssets(undefined);setPreviewSnapshot(undefined);setPreviewError(!projectPath?'Не выбрана сцена проекта для Preview.':undefined);return; }
    setAssets(undefined);setPreviewSnapshot(undefined);setPreviewError(undefined);
    const requestId=`effects-${request}`;
    previewDiag('effects','START',request,{requestId,projectPath,source:latest.source});
    setPreviewBusy(true);
    try {
      const composed={...latest,target:(latest.target||'CUSTOM').trim().toUpperCase()||'CUSTOM',opacity:latest.opacity??1,x:sceneAnchor?clamp01(sceneAnchor.x+(latest.offsetX??0)):latest.x,y:sceneAnchor?clamp01(sceneAnchor.y+(latest.offsetY??0)):latest.y};
      const result = await previewWithTimeout(api.prepareLivePreview(projectPath, latest.source, latest.previewFrameTime, requestId, 'Effects'),'Effects Live Preview');
      previewDiag('effects','FINISH',request,{requestId,basePath:result.basePath,overlayPath:result.overlayPath});
      if (request !== previewRequest.current) { previewDiag('effects','DISCARD',request,{requestId,latest:previewRequest.current}); return; }
      setPreviewSnapshot(composed);
      setAssets({basePath:api.previewUrl(result.basePath),baseFilePath:result.basePath,baseKind:result.baseKind,overlayPath:api.previewUrl(result.overlayPath),overlayFilePath:result.overlayPath,baseBytes:result.baseBytes,overlayBytes:result.overlayBytes,requestId,previewType:'Effects'});
      previewDiag('effects','APPLY',request,{requestId});
      void previewWithTimeout(api.generatePreviewPoster(projectPath, latest.previewFrameTime, [composed], [], requestId),'Effects poster').then(posterPath=>{
        if(request!==previewRequest.current)return;
        setAssets(previous=>previous?.requestId===requestId?{...previous,posterPath:api.previewUrl(posterPath),posterFilePath:posterPath}:previous);
      }).catch(error=>console.warn('[preview/error] optional Effects poster failed',requestId,String(error)));
    } catch (error) {
      if (request !== previewRequest.current) { previewDiag('effects','DISCARD',request,{requestId,error:String(error)}); return; }
      const message=`Effects Preview: ${String(error)}\nИсточник: ${latest.source}`;
      setPreviewError(message);console.error('[preview/error]',requestId,message);
    } finally {
      if (request === previewRequest.current) setPreviewBusy(false);
    }
  };

  useEffect(() => {
    if (!current || !projectPath) return;
    const request=++previewRequest.current;
    const timer = window.setTimeout(() => void loadLive(request), 180);
    return () => window.clearTimeout(timer);
  }, [selected, projectPath, current?.source, current?.previewFrameTime]);''',
)
replace_once(
    "src/pages/Editors.tsx",
    "          <PreviewStage\n            title={anchorMode ? `ПОКАЖИ НА ИЗОБРАЖЕНИИ: ${target}` : \"LIVE PREVIEW\"}",
    "          <PreviewStage\n            title={anchorMode ? `ПОКАЖИ НА ИЗОБРАЖЕНИИ: ${target}` : \"LIVE PREVIEW\"}",
)
replace_once(
    "src/pages/Editors.tsx",
    "          />\n          <div className=\"previewTime\"><span>Стартовый кадр proxy</span>",
    "          />\n          {previewError&&<div className=\"validationBox\"><b>Live Preview не готов:</b><div>{previewError}</div><button type=\"button\" onClick={()=>void loadLive()}>ПОВТОРИТЬ</button></div>}\n          <div className=\"previewTime\"><span>Стартовый кадр proxy</span>",
)

# Subscribe: VYRON bridge now sets previewProjectPath; this fallback also protects
# old restored drafts and exposes a precise missing-media recovery action.
replace_once(
    "src/pages/Editors.tsx",
    "  const projectPath = useProjectPath();\n  const [selected, setSelected] = useState(editor?.id || subscribes[0]?.id);",
    "  const previewProjectPath = useProjectPath();\n  const draftProjects = useApp((s) => s.draftProjects);\n  const projectPath = previewProjectPath || draftProjects[0]?.path;\n  const [selected, setSelected] = useState(editor?.id || subscribes[0]?.id);",
)
replace_once(
    "src/pages/Editors.tsx",
    "  const [previewBusy, setPreviewBusy] = useState(false);\n  const [saved, setSaved] = useState(false);",
    "  const [previewBusy, setPreviewBusy] = useState(false);\n  const [previewError, setPreviewError] = useState<string>();\n  const [saved, setSaved] = useState(false);",
)
# Second occurrence only: the first invalidatePreview was already changed, so this
# literal now uniquely identifies Subscribe.
replace_once(
    "src/pages/Editors.tsx",
    "  const invalidatePreview=()=>{previewRequest.current+=1;setAssets(undefined);setPreviewSnapshot(undefined);};",
    "  const invalidatePreview=()=>{previewRequest.current+=1;setAssets(undefined);setPreviewSnapshot(undefined);setPreviewError(undefined);};",
)
replace_once(
    "src/pages/Editors.tsx",
    "  const remove = async () => {\n    if (!current) return;\n    const next = subscribes.filter((item) => item.id !== current.id);\n    await saveLibrary(next, true);\n    invalidatePreview();setSelected(next[0]?.id);\n  };",
    "  const remove = async () => {\n    if (!current) return;\n    const next = subscribes.filter((item) => item.id !== current.id);\n    await saveLibrary(next, true);\n    invalidatePreview();setSelected(next[0]?.id);\n  };\n\n  const reselectSource = async () => {\n    if(!current)return;\n    const source=await api.chooseVideo('subscribe');if(!source)return;\n    const next=subscribes.map(item=>item.id===current.id?{...item,source,assetState:'ready' as const,assetError:undefined,cacheReady:false,cacheKey:undefined}:item);\n    await saveLibrary(next,true);invalidatePreview();\n  };",
)
regex_once(
    "src/pages/Editors.tsx",
    r"  const loadLive = async \(request = \+\+previewRequest\.current\) => \{\n    const latest = useApp\.getState\(\)\.subscribes\.find\(\(item\) => item\.id === selected\);.*?\n  \};\n\n  useEffect\(\(\) => \{\n    if \(!current \|\| !projectPath\) return;\n    const request=\+\+previewRequest\.current;\n    const timer = window\.setTimeout\(\(\) => void loadLive\(request\), 180\);\n    return \(\) => window\.clearTimeout\(timer\);\n  \}, \[.*?\n  \]\);",
    r'''  const loadLive = async (request = ++previewRequest.current) => {
    const latest = useApp.getState().subscribes.find((item) => item.id === selected);
    if (!latest) { setAssets(undefined);setPreviewSnapshot(undefined);return; }
    if (!projectPath) { setAssets(undefined);setPreviewSnapshot(undefined);setPreviewError(`Для Subscribe Preview не выбрана сцена проекта. Media: ${latest.name}\nОжидаемый путь: ${latest.source}`);return; }
    setAssets(undefined);setPreviewSnapshot(undefined);setPreviewError(undefined);
    const requestId=`subscribe-${request}`;
    previewDiag('subscribe','START',request,{requestId,projectPath,source:latest.source});
    setPreviewBusy(true);
    try {
      const result = await previewWithTimeout(api.prepareLivePreview(projectPath, latest.source, latest.previewFrameTime, requestId, 'Subscribe'),'Subscribe Live Preview');
      previewDiag('subscribe','FINISH',request,{requestId,basePath:result.basePath,overlayPath:result.overlayPath});
      if (request !== previewRequest.current) { previewDiag('subscribe','DISCARD',request,{requestId,latest:previewRequest.current}); return; }
      setPreviewSnapshot(latest);
      setAssets({basePath:api.previewUrl(result.basePath),baseFilePath:result.basePath,baseKind:result.baseKind,overlayPath:api.previewUrl(result.overlayPath),overlayFilePath:result.overlayPath,baseBytes:result.baseBytes,overlayBytes:result.overlayBytes,requestId,previewType:'Subscribe'});
      previewDiag('subscribe','APPLY',request,{requestId});
      void previewWithTimeout(api.generatePreviewPoster(projectPath, latest.previewFrameTime, [], [latest], requestId),'Subscribe poster').then(posterPath=>{
        if(request!==previewRequest.current)return;
        setAssets(previous=>previous?.requestId===requestId?{...previous,posterPath:api.previewUrl(posterPath),posterFilePath:posterPath}:previous);
      }).catch(error=>console.warn('[preview/error] optional Subscribe poster failed',requestId,String(error)));
    } catch (error) {
      if (request !== previewRequest.current) { previewDiag('subscribe','DISCARD',request,{requestId,error:String(error)}); return; }
      const message=`Subscribe media: ${latest.name}\nОжидаемый путь: ${latest.source}\nФайл не удалось открыть: ${String(error)}`;
      setPreviewError(message);console.error('[preview/error]',requestId,message);
    } finally {
      if (request === previewRequest.current) setPreviewBusy(false);
    }
  };

  useEffect(() => {
    if (!current || !projectPath) return;
    const request=++previewRequest.current;
    const timer = window.setTimeout(() => void loadLive(request), 180);
    return () => window.clearTimeout(timer);
  }, [selected, projectPath, current?.source, current?.previewFrameTime]);''',
)
replace_once(
    "src/pages/Editors.tsx",
    "          <PreviewStage title=\"LIVE PREVIEW\" assets={assets} busy={previewBusy} current={previewSnapshot || current} active={!!assets&&!!previewSnapshot&&previewEnabled(previewSnapshot)} onMove={(x, y) => patch({ x, y })} onScale={(scale) => patch({ scale })} onPickColor={(hex) => patch({ keyColor: hex, similarity: 0.10, blend: 0.06 })} />\n          <div className=\"previewTime\"><span>Стартовый кадр Subscribe-видео</span>",
    "          <PreviewStage title=\"LIVE PREVIEW\" assets={assets} busy={previewBusy} current={previewSnapshot || current} active={!!assets&&!!previewSnapshot&&previewEnabled(previewSnapshot)} onMove={(x, y) => patch({ x, y })} onScale={(scale) => patch({ scale })} onPickColor={(hex) => patch({ keyColor: hex, similarity: 0.10, blend: 0.06 })} />\n          {previewError&&<div className=\"validationBox\"><b>Subscribe Preview не готов:</b><div>{previewError}</div><div><button type=\"button\" onClick={()=>void loadLive()}>ПОВТОРИТЬ</button><button type=\"button\" onClick={()=>void reselectSource()}>ВЫБРАТЬ ЗАНОВО</button></div></div>}\n          <div className=\"previewTime\"><span>Стартовый кадр Subscribe-видео</span>",
)

# Poster is now optional. Base + overlay are enough for GPU Live Preview; a poster
# arriving later may enhance startup but can no longer block the first usable frame.
regex_once(
    "src/components/LiveCompositePreview.tsx",
    r"  useEffect\(\(\)=>\{\n    if\(!assets\)return;\n    const requestId=.*?\n  \},\[assets\?\.baseFilePath,assets\?\.overlayFilePath,assets\?\.posterFilePath,assets\?\.baseKind,assets\?\.requestId,assets\?\.previewType\]\);",
    r'''  useEffect(()=>{
    if(!assets)return;
    const requestId=assets.requestId||'<unknown>',previewType=assets.previewType||'Effects';
    let disposed=false,baseObjectUrl:string|undefined,posterObjectUrl:string|undefined;
    (async()=>{
      try{
        if(!assets.baseFilePath||!assets.overlayFilePath)throw new Error('Preview base/overlay file path missing');
        const [baseBytes,overlayBytes]=await Promise.all([readFile(assets.baseFilePath),readFile(assets.overlayFilePath)]);
        if(baseBytes.byteLength<1024||overlayBytes.byteLength<1024)throw new Error(`Preview payload too small: base=${baseBytes.byteLength} overlay=${overlayBytes.byteLength}`);
        let posterBytes:Uint8Array|undefined;
        if(assets.posterFilePath){try{const bytes=await readFile(assets.posterFilePath);if(bytes.byteLength>=1024)posterBytes=bytes;else console.warn('[preview/error] optional poster too small',requestId,bytes.byteLength)}catch(error){console.warn('[preview/error] optional poster read failed',requestId,String(error))}}
        transportBytesRef.current=baseBytes.byteLength+overlayBytes.byteLength+(posterBytes?.byteLength||0);
        const baseRaw=baseBytes.buffer.slice(baseBytes.byteOffset,baseBytes.byteOffset+baseBytes.byteLength) as ArrayBuffer;
        baseObjectUrl=URL.createObjectURL(new Blob([baseRaw],{type:assets.baseKind==='image'?'image/png':'video/mp4'}));
        if(posterBytes){const posterRaw=posterBytes.buffer.slice(posterBytes.byteOffset,posterBytes.byteOffset+posterBytes.byteLength) as ArrayBuffer;posterObjectUrl=URL.createObjectURL(new Blob([posterRaw],{type:'image/png'}));}
        const resolvedOverlay=assets.overlayPath;
        console.info(`[ENDLUME_PREVIEW] PREVIEW_REQUEST_ID=${requestId} PREVIEW_TYPE=${previewType} FRONTEND_PAYLOAD_BYTES=${transportBytesRef.current} OBJECT_URL_CREATED=true FRONTEND_TRANSFER_MODE=BASE_BLOB_OVERLAY_ASSET POSTER_OPTIONAL=${!!posterObjectUrl}`);
        if(disposed){if(baseObjectUrl)URL.revokeObjectURL(baseObjectUrl);if(posterObjectUrl)URL.revokeObjectURL(posterObjectUrl);baseObjectUrl=undefined;posterObjectUrl=undefined;return}
        setBaseSrc(baseObjectUrl);setOverlaySrc(resolvedOverlay);setPosterSrc(posterObjectUrl);
      }catch(error){
        console.error(`[ENDLUME_PREVIEW] PREVIEW_REQUEST_ID=${requestId} PREVIEW_TYPE=${previewType} OBJECT_URL_CREATED=false IMAGE_LOAD=RED PREVIEW_APPLIED=false ERROR=${String(error)}`);
        if(frameStateRef.current&&!reportedFrameRef.current){reportedFrameRef.current=true;frameStateRef.current({status:'RED',requestId,previewType,width:0,height:0,payloadBytes:transportBytesRef.current,paintedNonBlack:0,browserVisible:false,pixelReadback:'RED'})}
      }
    })();
    return()=>{disposed=true;if(baseObjectUrl)URL.revokeObjectURL(baseObjectUrl);if(posterObjectUrl)URL.revokeObjectURL(posterObjectUrl)};
  },[assets?.baseFilePath,assets?.overlayFilePath,assets?.posterFilePath,assets?.baseKind,assets?.requestId,assets?.previewType]);''',
)
replace_once(
    "src/components/LiveCompositePreview.tsx",
    "    {(busy||!posterSrc)&&<div className=\"livePreviewPreparing\">Подготавливаю Live Preview…</div>}",
    "    {(busy||(!liveReady&&!posterSrc))&&<div className=\"livePreviewPreparing\">Подготавливаю Live Preview…</div>}",
)

# Bounded FFmpeg execution for Preview only. The final renderer is untouched.
replace_once(
    "src-tauri/src/live_preview.rs",
    "use std::{fs,io::Read,path::{Path,PathBuf},sync::OnceLock,time::UNIX_EPOCH};",
    "use std::{fs,io::Read,path::{Path,PathBuf},process::{Command,Stdio},sync::OnceLock,thread,time::{Duration,Instant,UNIX_EPOCH}};",
)
replace_once(
    "src-tauri/src/live_preview.rs",
    "pub(crate) async fn ffmpeg_output(app:&AppHandle,args:Vec<String>)->Result<(bool,Option<i32>,Vec<u8>,Vec<u8>),String>{",
    "const PREVIEW_PROCESS_TIMEOUT:Duration=Duration::from_secs(5);\nfn staged_process_output(exe:&Path,args:&[String])->Result<(bool,Option<i32>,Vec<u8>,Vec<u8>),String>{\n  let mut child=Command::new(exe).args(args).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().map_err(|e|format!(\"[preview/error] Не удалось запустить FFmpeg preview {}: {e}\",exe.display()))?;\n  let started=Instant::now();\n  loop{\n    match child.try_wait(){\n      Ok(Some(_))=>{let out=child.wait_with_output().map_err(|e|format!(\"[preview/error] FFmpeg preview wait: {e}\"))?;return Ok((out.status.success(),out.status.code(),out.stdout,out.stderr))}\n      Ok(None) if started.elapsed()>=PREVIEW_PROCESS_TIMEOUT=>{let _=child.kill();let out=child.wait_with_output().map_err(|e|format!(\"[preview/error] FFmpeg preview timeout wait: {e}\"))?;let detail=String::from_utf8_lossy(&out.stderr);return Err(format!(\"[preview/error] FFmpeg preview timeout after {}s: {}\",PREVIEW_PROCESS_TIMEOUT.as_secs(),detail.trim().chars().take(500).collect::<String>()))}\n      Ok(None)=>thread::sleep(Duration::from_millis(35)),\n      Err(e)=>{let _=child.kill();let _=child.wait();return Err(format!(\"[preview/error] FFmpeg preview status: {e}\"))}\n    }\n  }\n}\n\npub(crate) async fn ffmpeg_output(app:&AppHandle,args:Vec<String>)->Result<(bool,Option<i32>,Vec<u8>,Vec<u8>),String>{",
)
replace_once(
    "src-tauri/src/live_preview.rs",
    "    let out=std::process::Command::new(&ffmpeg).args(&args).output()\n      .map_err(|e|format!(\"Не удалось запустить staged FFmpeg preview {}: {e}\",ffmpeg.display()))?;\n    return Ok((out.status.success(),out.status.code(),out.stdout,out.stderr))",
    "    return staged_process_output(&ffmpeg,&args)",
)
replace_once(
    "src-tauri/src/live_preview.rs",
    "  let out=app.shell().sidecar(\"ffmpeg\").map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;\n  Ok((out.status.success(),out.status.code(),out.stdout,out.stderr))",
    "  let future=app.shell().sidecar(\"ffmpeg\").map_err(|e|e.to_string())?.args(args).output();\n  let out=tokio::time::timeout(PREVIEW_PROCESS_TIMEOUT,future).await.map_err(|_|format!(\"[preview/error] FFmpeg sidecar preview timeout after {}s\",PREVIEW_PROCESS_TIMEOUT.as_secs()))?.map_err(|e|e.to_string())?;\n  Ok((out.status.success(),out.status.code(),out.stdout,out.stderr))",
)
replace_once(
    "src-tauri/src/live_preview.rs",
    "  let project=PathBuf::from(project_path);if !project.is_dir(){return Err(\"Сначала выберите папку проекта\".into())}\n  let overlay=PathBuf::from(overlay_source);if !overlay.is_file(){return Err(\"Не найден файл Effects/Subscribe\".into())}if rejected_macos_input(&overlay){return Err(\"ENDLUME заблокировала служебный AppleDouble/resource-fork файл macOS. Выберите настоящий Effects/Subscribe файл.\".into())}if rejected_macos_input(&overlay){return Err(\"ENDLUME заблокировала служебный AppleDouble/resource-fork файл macOS. Выберите настоящий Effects/Subscribe файл.\".into())}",
    "  let request=request_id.as_deref().unwrap_or(\"<none>\");let kind=preview_type.as_deref().unwrap_or(\"Unknown\");\n  if live_preview_diag_enabled(){eprintln!(\"[preview/request] id={request} type={kind} project={} source={} seek={time_sec}\",project_path,overlay_source);}\n  let project=PathBuf::from(&project_path);if !project.is_dir(){return Err(format!(\"[preview/source] Папка проекта не найдена: {project_path}\"))}\n  let overlay=PathBuf::from(&overlay_source);if !overlay.is_file(){return Err(format!(\"[preview/source] Media не найден. expectedPath={overlay_source} exists=false\"))}if rejected_macos_input(&overlay){return Err(\"[preview/source] ENDLUME заблокировала служебный AppleDouble/resource-fork файл macOS. Выберите настоящий Effects/Subscribe файл.\".into())}",
)
replace_once(
    "src-tauri/src/live_preview.rs",
    "  let base_kind=make_base(&app,&base,time_sec,&base_out).await?;make_overlay(&app,&overlay,overlay_seek,&overlay_out).await?;",
    "  if live_preview_diag_enabled(){eprintln!(\"[preview/source] id={request} base={} overlay={}\",base.display(),overlay.display());}\n  let started=Instant::now();\n  let base_kind=make_base(&app,&base,time_sec,&base_out).await.map_err(|e|format!(\"[preview/frame] base failed: {e}\"))?;\n  make_overlay(&app,&overlay,overlay_seek,&overlay_out).await.map_err(|e|format!(\"[preview/decode] overlay failed: {e}\"))?;\n  if live_preview_diag_enabled(){eprintln!(\"[preview/frame] id={request} ready_ms={} base={} overlay={}\",started.elapsed().as_millis(),base_out.display(),overlay_out.display());}",
)
# The diagnostics block declares request/kind again in 10.0.13; reuse the values above.
replace_once(
    "src-tauri/src/live_preview.rs",
    "    let request=request_id.as_deref().unwrap_or(\"<none>\");\n    let kind=preview_type.as_deref().unwrap_or(\"Unknown\");\n",
    "",
)

# Static source-contract checks for this hotfix.
qa = ROOT / "scripts" / "qa-endlume-1014-hotfix.py"
qa.write_text('''#!/usr/bin/env python3\nfrom pathlib import Path\nroot=Path(__file__).resolve().parents[1]\ndef text(p): return (root/p).read_text(encoding="utf-8")\nproject=text("src/pages/ProjectPage.tsx")\nbridge=text("src/components/VyronBatchBridge.tsx")\nvyron=text("src-tauri/src/vyron_bridge.rs")\neditors=text("src/pages/Editors.tsx")\nlive=text("src-tauri/src/live_preview.rs")\ncomposite=text("src/components/LiveCompositePreview.tsx")\nmodel=text("src-tauri/src/model.rs")\nassert "outputSource?: 'vyron'|'manual'" in text("src/types.ts")\nassert "outputDir:info.outputDir,outputSource:'vyron'" in bridge\nassert "setPreviewProjectPath(valid[0]?.path)" in bridge\nassert "v.get(\\"outputDir\\")" in vyron and "validate_output_writable" in vyron\nassert "const groups=new Map<string,typeof queuedProjects>()" in project\nassert "AUTO • VYRON" in project\nassert "selectedForAll" in project and "СБРОСИТЬ → БЕЗ ЭФФЕКТА" in project\nassert "previewWithTimeout" in editors and "ПОВТОРИТЬ" in editors and "ВЫБРАТЬ ЗАНОВО" in editors\nassert "poster optional" in composite.lower() or "POSTER_OPTIONAL" in composite\nassert "PREVIEW_PROCESS_TIMEOUT" in live and "[preview/request]" in live and "[preview/decode]" in live\nassert "output_dir:Option<String>" in model\nprint("PASS: ENDLUME 10.0.14 source contracts")\n''', encoding="utf-8")

print("Applied ENDLUME 10.0.14 focused hotfix")
