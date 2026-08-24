from pathlib import Path

p=Path('src/pages/Editors.tsx')
s=p.read_text(encoding='utf-8')
changed=False

old="const add=async()=>{const source=await api.chooseVideo();if(!source)return;const e=emptyEffect(source);await saveLibrary([...effects,e],true);setSelected(e.id)};"
new="const add=async()=>{try{const source=await api.chooseVideo('effects');if(!source)return;const e=emptyEffect(source);await saveLibrary([...effects,e],true);setSelected(e.id)}catch(err){await api.showError(`Не удалось добавить эффект.\\n${String(err)}`)}};"
if old in s:
    s=s.replace(old,new,1);changed=True
elif new not in s:
    raise SystemExit('Effects add handler not found')

old="const loadLive=async()=>{const latest=useApp.getState().effects.find(e=>e.id===selected);if(!projectPath||!latest)return;setPreviewBusy(true);try{const a=await api.prepareLivePreview(projectPath,latest.source,latest.previewFrameTime);setAssets({basePath:api.previewUrl(a.basePath),baseKind:a.baseKind,overlayPath:api.previewUrl(a.overlayPath)})}catch(e){await api.showError(`Не удалось подготовить Live Preview эффекта.\\n${String(e)}`)}finally{setPreviewBusy(false)}};"
new="const loadLive=async()=>{const latest=useApp.getState().effects.find(e=>e.id===selected);if(!projectPath||!latest)return;if(!latest.source.trim()){setAssets(undefined);return}setPreviewBusy(true);try{const a=await api.prepareLivePreview(projectPath,latest.source,latest.previewFrameTime);setAssets({basePath:api.previewUrl(a.basePath),baseKind:a.baseKind,overlayPath:api.previewUrl(a.overlayPath)})}catch(e){setAssets(undefined);await api.showError(`Не удалось подготовить Live Preview эффекта.\\n${String(e)}`)}finally{setPreviewBusy(false)}};"
if old in s:
    s=s.replace(old,new,1);changed=True
elif new not in s:
    raise SystemExit('Effects live preview handler not found')

old="const add=async()=>{const source=await api.chooseVideo();if(!source)return;const e=emptySubscribe(source);await saveLibrary([...subscribes,e],true);setSelected(e.id)};"
new="const add=async()=>{try{const source=await api.chooseVideo('subscribe');if(!source)return;const e=emptySubscribe(source);await saveLibrary([...subscribes,e],true);setSelected(e.id)}catch(err){await api.showError(`Не удалось добавить Subscribe-видео.\\n${String(err)}`)}};"
if old in s:
    s=s.replace(old,new,1);changed=True
elif new not in s:
    raise SystemExit('Subscribe add handler not found')

old="const loadLive=async()=>{const latest=useApp.getState().subscribes.find(e=>e.id===selected);if(!projectPath||!latest)return;setPreviewBusy(true);try{const a=await api.prepareLivePreview(projectPath,latest.source,latest.previewFrameTime);setAssets({basePath:api.previewUrl(a.basePath),baseKind:a.baseKind,overlayPath:api.previewUrl(a.overlayPath)})}catch(e){await api.showError(`Не удалось подготовить Live Preview Subscribe.\\n${String(e)}`)}finally{setPreviewBusy(false)}};"
new="const loadLive=async()=>{const latest=useApp.getState().subscribes.find(e=>e.id===selected);if(!projectPath||!latest)return;if(!latest.source.trim()){setAssets(undefined);return}setPreviewBusy(true);try{const a=await api.prepareLivePreview(projectPath,latest.source,latest.previewFrameTime);setAssets({basePath:api.previewUrl(a.basePath),baseKind:a.baseKind,overlayPath:api.previewUrl(a.overlayPath)})}catch(e){setAssets(undefined);await api.showError(`Не удалось подготовить Live Preview Subscribe.\\n${String(e)}`)}finally{setPreviewBusy(false)}};"
if old in s:
    s=s.replace(old,new,1);changed=True
elif new not in s:
    raise SystemExit('Subscribe live preview handler not found')

if changed:
    p.write_text(s,encoding='utf-8')
    print('ENDLUME editor asset hotfix applied')
else:
    print('ENDLUME editor asset hotfix already applied')
