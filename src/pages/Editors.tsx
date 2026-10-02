import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useApp } from '../store';
import { api } from '../tauri';
import type { AnchorPoint, EffectPreset, EffectUsageMode, SubscribeFirstAppearance, SubscribePreset } from '../types';
import { Icon, Range } from '../components/ui';
import { LiveCompositePreview, type LivePreviewAssets } from '../components/LiveCompositePreview';

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
const effectiveUsageMode = (item: EffectPreset): EffectUsageMode => item.usageMode ?? (item.enabled ? 'always' : 'off');
const usageLabel = (item: EffectPreset) => { const mode=effectiveUsageMode(item); return mode==='off'?'ВЫКЛ':mode==='always'?'ВСЕГДА':'ПО ИНТЕРВАЛУ'; };
const subscribeFirst = (item: SubscribePreset): SubscribeFirstAppearance => item.firstAppearance ?? 'after-interval';
const subscribeInterval = (item: SubscribePreset) => Math.max(60, item.intervalSec ?? item.repeatEverySec ?? 240);
const subscribeDuration = (item: SubscribePreset) => Math.max(2, Math.min(20, item.showDurationSec ?? 8));
const toggleEffectEnabled = (item: EffectPreset): EffectPreset => {
  const enabled = !item.enabled;
  return { ...item, enabled, usageMode: enabled && item.usageMode === 'off' ? 'always' : item.usageMode };
};
const toggleSubscribeEnabled = (item: SubscribePreset): SubscribePreset => {
  const enabled = !item.enabled;
  return { ...item, enabled, usageMode: enabled && item.usageMode === 'off' ? 'interval' : item.usageMode };
};
const previewEnabled = (item: EffectPreset) => item.enabled && effectiveUsageMode(item) !== 'off';
const previewDiag = (scope:'effects'|'subscribe',phase:'START'|'FINISH'|'APPLY'|'DISCARD',request:number,extra:Record<string,unknown>={}) => console.info('[ENDLUME_PREVIEW]',{scope,phase,request,...extra});

const emptyEffect = (source = ''): EffectPreset => ({
  id: crypto.randomUUID(),
  name: source.split(/[\\/]/).pop() || 'Новый эффект',
  source,
  enabled: true,
  mode: 'chromakey',
  keyColor: '#00ff00',
  similarity: 0.10,
  blend: 0.06,
  despill: 0.35,
  lumaThreshold: 0.03,
  lumaTolerance: 0.08,
  saturation: 1,
  x: 0.5,
  y: 0.5,
  scale: 0.34,
  fullscreen: false,
  previewFrameTime: 0,
  startSec: 0,
  endSec: null,
  usageMode: 'always',
  intervalSec: 240,
  usageDurationSec: 30,
  target: 'CUSTOM',
  offsetX: 0,
  offsetY: 0,
  opacity: 1,
});

const emptySubscribe = (source = ''): SubscribePreset => ({
  ...emptyEffect(source),
  name: source.split(/[\\/]/).pop() || 'Subscribe',
  x: 0.5,
  y: 0.5,
  scale: 0.32,
  firstAtSec: 240,
  secondAtSec: 480,
  repeatEverySec: 240,
  usageMode: 'interval',
  intervalSec: 240,
  firstAppearance: 'after-interval',
  customFirstAtSec: 240,
  showDurationSec: 8,
});

export function EditorRouter() {
  const editor = useApp((s) => s.editor);
  if (!editor) return null;
  return editor.kind === 'effects' ? <EffectsEditor /> : <SubscribeEditor />;
}

function useProjectPath() {
  const draft = useApp((s) => s.draftProjects);
  const projects = useApp((s) => s.projects);
  return draft[0]?.path || projects.find((p) => p.status === 'rendering')?.path || projects.at(-1)?.path;
}

function EffectsEditor() {
  const effects = useApp((s) => s.effects);
  const setEffects = useApp((s) => s.setEffects);
  const openEditor = useApp((s) => s.openEditor);
  const editor = useApp((s) => s.editor);
  const draftProjects = useApp((s) => s.draftProjects);
  const projects = useApp((s) => s.projects);
  const sceneAnchorsByPath = useApp((s) => s.sceneAnchorsByPath);
  const setSceneAnchor = useApp((s) => s.setSceneAnchor);
  const sceneCandidates = useMemo(() => draftProjects.length ? draftProjects : projects, [draftProjects, projects]);
  const [scenePath, setScenePath] = useState('');
  const [selected, setSelected] = useState(editor?.id || effects[0]?.id);
  const [saved, setSaved] = useState(false);
  const [assets, setAssets] = useState<LivePreviewAssets>();
  const [previewBusy, setPreviewBusy] = useState(false);
  const [anchorMode, setAnchorMode] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const persistTimer = useRef<number | undefined>(undefined);
  const previewRequest = useRef(0);
  const current = effects.find((e) => e.id === selected);
  const projectPath = scenePath || sceneCandidates[0]?.path;
  const target = (current?.target || 'CUSTOM').trim().toUpperCase() || 'CUSTOM';
  const sceneAnchor = projectPath ? sceneAnchorsByPath[projectPath]?.[target] : undefined;
  const resolvedCurrent = current ? {
    ...current,
    target,
    opacity: current.opacity ?? 1,
    x: sceneAnchor ? clamp01(sceneAnchor.x + (current.offsetX ?? 0)) : current.x,
    y: sceneAnchor ? clamp01(sceneAnchor.y + (current.offsetY ?? 0)) : current.y,
  } : undefined;

  useEffect(() => {
    if (!sceneCandidates.length) { if (scenePath) setScenePath(''); return; }
    if (!scenePath || !sceneCandidates.some((item) => item.path === scenePath)) setScenePath(sceneCandidates[0].path);
  }, [sceneCandidates, scenePath]);

  useEffect(() => { setAnchorMode(false); }, [scenePath, target]);

  const saveLibrary = (next: EffectPreset[], immediate = false) => {
    setEffects(next);
    if (persistTimer.current) window.clearTimeout(persistTimer.current);
    const persist = () => api.saveLibrary({
      effects: next,
      subscribes: useApp.getState().subscribes,
      ambient: useApp.getState().ambient,
    }).catch(() => undefined);
    if (immediate) return persist();
    persistTimer.current = window.setTimeout(persist, 180);
    return Promise.resolve();
  };

  useEffect(() => () => {
    previewRequest.current += 1;
    if (persistTimer.current) window.clearTimeout(persistTimer.current);
  }, []);

  const add = async () => {
    const source = await api.chooseVideo('effects');
    if (!source) return;
    const effect = emptyEffect(source);
    await saveLibrary([...effects, effect], true);
    setSelected(effect.id);
  };

  const patch = (value: Partial<EffectPreset>) => {
    if (!current) return;
    void saveLibrary(effects.map((e) => e.id === current.id ? { ...e, ...value } : e));
  };

  const moveEffect = (x: number, y: number) => {
    if (!current) return;
    if (sceneAnchor) {
      patch({ offsetX: x - sceneAnchor.x, offsetY: y - sceneAnchor.y });
    } else {
      patch({ x, y });
    }
  };

  const pickAnchor = (x: number, y: number) => {
    if (!current || !projectPath) return;
    const key = (current.target || 'CUSTOM').trim().toUpperCase() || 'CUSTOM';
    setSceneAnchor(projectPath, key, { x, y, source: 'manual' });
    patch({ target: key, offsetX: 0, offsetY: 0 });
    setAnchorMode(false);
  };

  const remove = async () => {
    if (!current) return;
    const next = effects.filter((e) => e.id !== current.id);
    await saveLibrary(next, true);
    setSelected(next[0]?.id);
    setAssets(undefined);
    setDeleteConfirm(false);
  };

  const loadLive = async (request = ++previewRequest.current) => {
    const latest = useApp.getState().effects.find((e) => e.id === selected);
    if (!projectPath || !latest) return;
    const requestId=`effects-${request}`;
    const renderEffect = sceneAnchor ? {
      ...latest,
      x: clamp01(sceneAnchor.x + (latest.offsetX ?? 0)),
      y: clamp01(sceneAnchor.y + (latest.offsetY ?? 0)),
    } : latest;
    previewDiag('effects','START',request,{requestId});
    setPreviewBusy(true);
    try {
      // Exact FFmpeg composite is the source of truth. The legacy base/overlay proxy
      // is auxiliary only; a base-frame helper failure must never blank a valid Preview.
      const exactPath = await api.generatePreview(projectPath, latest.previewFrameTime, [renderEffect], [], requestId);
      let result:Awaited<ReturnType<typeof api.prepareLivePreview>>|undefined;
      try { result = await api.prepareLivePreview(projectPath, latest.source, latest.previewFrameTime, requestId, 'Effects'); }
      catch (helperError) { previewDiag('effects','DISCARD',request,{requestId,helper:'prepareLivePreview',error:String(helperError)}); }
      previewDiag('effects','FINISH',request,{requestId,exactPath});
      if (request !== previewRequest.current) { previewDiag('effects','DISCARD',request,{requestId,latest:previewRequest.current}); return; }
      setAssets({
        basePath: result ? api.previewUrl(result.basePath) : api.previewUrl(exactPath),
        baseKind: result?.baseKind ?? 'video',
        overlayPath: result ? api.previewUrl(result.overlayPath) : api.previewUrl(latest.source),
        compositePath: api.previewUrl(exactPath),
        requestId,
        previewType:'Effects',
      });
      previewDiag('effects','APPLY',request,{requestId});
    } catch (error) {
      if (request !== previewRequest.current) { previewDiag('effects','DISCARD',request,{requestId,error:String(error)}); return; }
      await api.showError(`Не удалось подготовить Live Preview эффекта.\n${String(error)}`);
    } finally {
      if (request === previewRequest.current) setPreviewBusy(false);
    }
  };

  useEffect(() => {
    if (!current || !projectPath) return;
    const request=++previewRequest.current;
    const timer = window.setTimeout(() => void loadLive(request), 180);
    return () => window.clearTimeout(timer);
  }, [
    selected, projectPath, sceneAnchor?.x, sceneAnchor?.y,
    current?.source, current?.previewFrameTime, current?.enabled, current?.mode,
    current?.keyColor, current?.similarity, current?.blend, current?.despill,
    current?.lumaThreshold, current?.lumaTolerance, current?.x, current?.y,
    current?.scale, current?.fullscreen, current?.opacity, current?.offsetX,
    current?.offsetY, current?.target,
  ]);

  return <div className="editorPage">
    <EditorHeader title="Эффекты" subtitle="FFmpeg Exact Preview • chromakey / luma / screen • Preview = Final" onBack={() => openEditor(null)} />
    <div className="editorLayout">
      <aside className="assetList">
        <button className="addAsset" onClick={add}>+ ДОБАВИТЬ</button>
        {effects.map((effect) => <button key={effect.id} className={`assetItem ${selected === effect.id ? 'active' : ''}`} onClick={() => setSelected(effect.id)}>
          <span className="assetThumb"><Icon name="effects" /></span>
          <span><b>{effect.name}</b><small>{effect.enabled ? 'Включён' : 'Выключен'} • {effect.mode} • {effect.cacheReady ? 'render-cache готов' : 'render-cache при первом рендере'}</small></span>
          <i className={effect.enabled ? 'enabled' : 'disabled'} title={effect.enabled ? 'Выключить' : 'Включить'} onClick={(event) => {
            event.stopPropagation();
            void saveLibrary(effects.map((item) => item.id === effect.id ? toggleEffectEnabled(item) : item), true);
          }} />
        </button>)}
      </aside>

      <main className="visualEditor">
        {current && resolvedCurrent ? <>
          {sceneCandidates.length > 0 && <div className="previewTime"><span>СЦЕНА / ИЗОБРАЖЕНИЕ</span><select value={projectPath || ''} onChange={(event) => setScenePath(event.target.value)}>{sceneCandidates.map((scene) => <option key={scene.path} value={scene.path}>{scene.name}</option>)}</select><b>{sceneAnchor ? `${target} ✓` : `${target}: anchor не задан`}</b></div>}
          <PreviewStage
            title={anchorMode ? `ПОКАЖИ НА ИЗОБРАЖЕНИИ: ${target}` : "LIVE PREVIEW"}
            assets={assets}
            busy={previewBusy}
            current={resolvedCurrent}
            active={previewEnabled(current)}
            anchor={sceneAnchor}
            anchorMode={anchorMode}
            onAnchorPick={pickAnchor}
            onMove={moveEffect}
            onScale={(scale) => patch({ scale })}
            onPickColor={(hex) => patch({ keyColor: hex, similarity: 0.10, blend: 0.06 })}
          />
          <div className="previewTime"><span>Стартовый кадр proxy</span><Range value={current.previewFrameTime} min={0} max={60} step={0.1} onChange={(value) => patch({ previewFrameTime: value })} minLabel="0:00" maxLabel="1:00" /><b>{current.previewFrameTime.toFixed(1)} сек</b></div>
          <button className="refreshPreview" disabled={previewBusy} onClick={() => void loadLive()}><Icon name="refresh" /> {previewBusy ? 'ГОТОВЛЮ PROXY…' : 'ОБНОВИТЬ LIVE PREVIEW'}</button>
          {current.usageMode === undefined && <Timeline start={current.startSec} end={current.endSec} total={useApp.getState().settings.durationHours * 3600} onChange={(start, end) => patch({ startSec: start, endSec: end })} />}
        </> : <div className="emptyEditor"><Icon name="effects" /><h3>Добавьте эффект</h3><p>Видео сохраняется во внутренней библиотеке ENDLUME.</p></div>}
      </main>

      <aside className="editorControls">
        {current && <>
          <label>Название<input value={current.name} onChange={(event) => patch({ name: event.target.value })} /></label>
          <label>Target / anchor<input list="endlume-effect-targets" value={current.target || 'CUSTOM'} onChange={(event) => patch({ target: event.target.value.toUpperCase() })} /></label>
          <datalist id="endlume-effect-targets"><option value="FIREPLACE"/><option value="CUP"/><option value="CANDLE"/><option value="WINDOW"/><option value="LAMP"/><option value="SCREEN"/><option value="TV"/><option value="FIRE"/><option value="SKY"/><option value="GROUND"/><option value="BACKGROUND"/><option value="FOREGROUND"/><option value="FULL_FRAME"/><option value="CUSTOM"/></datalist>
          {!current.fullscreen && projectPath && <button className="savePreset" onClick={() => setAnchorMode((value) => !value)}>{anchorMode ? `ОТМЕНИТЬ УСТАНОВКУ ${target}` : sceneAnchor ? `ИЗМЕНИТЬ ANCHOR: ${target}` : `ПОКАЗАТЬ ГДЕ ${target}`}</button>}
          {sceneAnchor && !current.fullscreen && <button className="savePreset" onClick={() => patch({ offsetX: 0, offsetY: 0 })}>ПРИВЯЗАТЬ ЭФФЕКТ К ЦЕНТРУ ANCHOR</button>}
          <SmallRange label="Opacity" value={current.opacity ?? 1} min={0} max={1} step={0.01} onChange={(value) => patch({ opacity: value })} />
          <UsageModeControl value={effectiveUsageMode(current)} onChange={(usageMode) => patch({ usageMode, enabled: usageMode !== 'off', startSec: usageMode === 'always' ? 0 : current.startSec, endSec: usageMode === 'always' ? null : current.endSec })} />
          {effectiveUsageMode(current) === 'interval' && <div className="usageSliders">
            <SmallRange label="Показывать каждые, мин" value={(current.intervalSec ?? 240) / 60} min={1} max={30} step={1} onChange={(value) => patch({ intervalSec: value * 60 })} />
            <SmallRange label="Длительность эффекта, сек" value={current.usageDurationSec ?? 30} min={5} max={60} step={1} onChange={(value) => patch({ usageDurationSec: value })} />
          </div>}
          <label>Режим<select value={current.mode} onChange={(event) => patch({ mode: event.target.value as EffectPreset['mode'] })}><option value="chromakey">Chromakey</option><option value="luma">Luma Alpha</option><option value="screen">Screen Blend</option></select></label>
          {current.mode === 'chromakey' && <>
            <label>Цвет chromakey<input type="color" value={current.keyColor} onChange={(event) => patch({ keyColor: event.target.value })} /></label>
            <button className="chromaReset" onClick={() => patch({ keyColor: '#00ff00', similarity: 0.10, blend: 0.06, saturation: 1, despill: 0.35 })}>СБРОСИТЬ CHROMAKEY</button>
            <p className="editorHint chromaHint">Нажми «ПИПЕТКА / КИСТЬ» на Preview и выбери фон. ENDLUME возьмёт цвет из исходного кадра.</p>
            <SmallRange label="Similarity" value={current.similarity} min={0.001} max={0.6} step={0.001} onChange={(value) => patch({ similarity: value })} />
            <SmallRange label="Blend / мягкость края" value={current.blend} min={0.001} max={0.35} step={0.001} onChange={(value) => patch({ blend: value })} />
            <SmallRange label="Despill / убрать зелёный ореол" value={current.despill} min={0} max={1} step={0.01} onChange={(value) => patch({ despill: value })} />
          </>}
          {current.mode === 'luma' && <>
            <SmallRange label="Threshold" value={current.lumaThreshold} min={0} max={1} step={0.01} onChange={(value) => patch({ lumaThreshold: value })} />
            <SmallRange label="Tolerance" value={current.lumaTolerance} min={0} max={1} step={0.01} onChange={(value) => patch({ lumaTolerance: value })} />
          </>}
          <label className="checkLine"><input type="checkbox" checked={current.fullscreen} onChange={(event) => patch({ fullscreen: event.target.checked })} /> На весь экран</label>
          <p className="editorHint">Preview и Render используют одинаковые X / Y / SIZE. Пропорции исходного эффекта сохраняются.</p>
          <button className="savePreset" onClick={async () => { await saveLibrary([...effects], true); setSaved(true); window.setTimeout(() => setSaved(false), 1200); }}><Icon name="save" /> {saved ? 'СОХРАНЕНО ✓' : 'СОХРАНИТЬ PRESET'}</button>
          <button className="savePreset" onClick={() => void saveLibrary(effects.map((e) => e.id === current.id ? toggleEffectEnabled(e) : e), true)}>{current.enabled ? 'ВЫКЛЮЧИТЬ ЭФФЕКТ' : 'ВКЛЮЧИТЬ ЭФФЕКТ'}</button>
          {deleteConfirm ? <div className="deleteConfirm" role="dialog" aria-label="Удалить эффект?"><b>Удалить эффект?</b><small>Удалится только эффект из проекта. Исходный видеофайл останется на диске.</small><div><button className="savePreset" onClick={() => setDeleteConfirm(false)}>ОТМЕНА</button><button className="deletePreset" onClick={() => void remove()}><Icon name="trash" /> УДАЛИТЬ</button></div></div> : <button className="deletePreset" onClick={() => setDeleteConfirm(true)}><Icon name="trash" /> УДАЛИТЬ ЭФФЕКТ</button>}
        </>}
      </aside>
    </div>
  </div>;
}

function SubscribeEditor() {
  const subscribes = useApp((s) => s.subscribes);
  const setSubscribes = useApp((s) => s.setSubscribes);
  const openEditor = useApp((s) => s.openEditor);
  const editor = useApp((s) => s.editor);
  const projectPath = useProjectPath();
  const [selected, setSelected] = useState(editor?.id || subscribes[0]?.id);
  const [assets, setAssets] = useState<LivePreviewAssets>();
  const [previewBusy, setPreviewBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const persistTimer = useRef<number | undefined>(undefined);
  const previewRequest = useRef(0);
  const current = subscribes.find((e) => e.id === selected);

  const saveLibrary = (next: SubscribePreset[], immediate = false) => {
    setSubscribes(next);
    if (persistTimer.current) window.clearTimeout(persistTimer.current);
    const persist = () => api.saveLibrary({
      effects: useApp.getState().effects,
      subscribes: next,
      ambient: useApp.getState().ambient,
    }).catch(() => undefined);
    if (immediate) return persist();
    persistTimer.current = window.setTimeout(persist, 180);
    return Promise.resolve();
  };

  useEffect(() => () => {
    previewRequest.current += 1;
    if (persistTimer.current) window.clearTimeout(persistTimer.current);
  }, []);

  const add = async () => {
    const source = await api.chooseVideo('subscribe');
    if (!source) return;
    const subscribe = emptySubscribe(source);
    await saveLibrary([...subscribes, subscribe], true);
    setSelected(subscribe.id);
  };

  const patch = (value: Partial<SubscribePreset>) => {
    if (!current) return;
    void saveLibrary(subscribes.map((item) => item.id === current.id ? { ...item, ...value } : item));
  };

  const remove = async () => {
    if (!current) return;
    const next = subscribes.filter((item) => item.id !== current.id);
    await saveLibrary(next, true);
    setSelected(next[0]?.id);
    setAssets(undefined);
  };

  const loadLive = async (request = ++previewRequest.current) => {
    const latest = useApp.getState().subscribes.find((item) => item.id === selected);
    if (!projectPath || !latest) return;
    const requestId=`subscribe-${request}`;
    previewDiag('subscribe','START',request,{requestId});
    setPreviewBusy(true);
    try {
      const exactPath = await api.generatePreview(projectPath, latest.previewFrameTime, [], [latest], requestId);
      let result:Awaited<ReturnType<typeof api.prepareLivePreview>>|undefined;
      try { result = await api.prepareLivePreview(projectPath, latest.source, latest.previewFrameTime); }
      catch (helperError) { previewDiag('subscribe','DISCARD',request,{requestId,helper:'prepareLivePreview',error:String(helperError)}); }
      previewDiag('subscribe','FINISH',request,{requestId,exactPath});
      if (request !== previewRequest.current) { previewDiag('subscribe','DISCARD',request,{requestId,latest:previewRequest.current}); return; }
      setAssets({
        basePath: result ? api.previewUrl(result.basePath) : api.previewUrl(exactPath),
        baseKind: result?.baseKind ?? 'video',
        overlayPath: result ? api.previewUrl(result.overlayPath) : api.previewUrl(latest.source),
        compositePath: api.previewUrl(exactPath),
        requestId,
        previewType:'Subscribe',
      });
      previewDiag('subscribe','APPLY',request,{requestId});
    } catch (error) {
      if (request !== previewRequest.current) { previewDiag('subscribe','DISCARD',request,{requestId,error:String(error)}); return; }
      await api.showError(`Не удалось подготовить Live Preview Subscribe.\n${String(error)}`);
    } finally {
      if (request === previewRequest.current) setPreviewBusy(false);
    }
  };

  useEffect(() => {
    if (!current || !projectPath) return;
    const request=++previewRequest.current;
    const timer = window.setTimeout(() => void loadLive(request), 180);
    return () => window.clearTimeout(timer);
  }, [
    selected, projectPath, current?.source, current?.previewFrameTime, current?.enabled,
    current?.mode, current?.keyColor, current?.similarity, current?.blend, current?.despill,
    current?.lumaThreshold, current?.lumaTolerance, current?.x, current?.y,
    current?.scale, current?.fullscreen, current?.opacity,
  ]);

  return <div className="editorPage">
    <EditorHeader title="Кнопка Subscribe" subtitle="FFmpeg Exact Preview • chromakey • позиция • расписание" onBack={() => openEditor(null)} />
    <div className="editorLayout">
      <aside className="assetList">
        <button className="addAsset" onClick={add}>+ ДОБАВИТЬ</button>
        {subscribes.map((item) => <button key={item.id} className={`assetItem ${selected === item.id ? 'active' : ''}`} onClick={() => setSelected(item.id)}>
          <span className="assetThumb pink"><Icon name="subscribe" /></span>
          <span><b>{item.name}</b><small>{usageLabel(item)}{effectiveUsageMode(item) === 'interval' ? ` • каждые ${Math.round(subscribeInterval(item) / 60)} мин` : ''}</small></span>
          <i className={item.enabled ? 'enabled' : 'disabled'} title={item.enabled ? 'Выключить' : 'Включить'} onClick={(event) => {
            event.stopPropagation();
            void saveLibrary(subscribes.map((entry) => entry.id === item.id ? toggleSubscribeEnabled(entry) : entry), true);
          }} />
        </button>)}
      </aside>

      <main className="visualEditor">
        {current ? <>
          <PreviewStage title="LIVE PREVIEW" assets={assets} busy={previewBusy} current={current} active={previewEnabled(current)} onMove={(x, y) => patch({ x, y })} onScale={(scale) => patch({ scale })} onPickColor={(hex) => patch({ keyColor: hex, similarity: 0.10, blend: 0.06 })} />
          <div className="previewTime"><span>Стартовый кадр Subscribe-видео</span><Range value={current.previewFrameTime} min={0} max={60} step={0.1} onChange={(value) => patch({ previewFrameTime: value })} minLabel="0:00" maxLabel="1:00" /><b>{current.previewFrameTime.toFixed(1)} сек</b></div>
          <button className="refreshPreview" disabled={previewBusy} onClick={() => void loadLive()}><Icon name="refresh" /> {previewBusy ? 'ГОТОВЛЮ PROXY…' : 'ОБНОВИТЬ LIVE PREVIEW'}</button>
          <SubscribeTimeline current={current} />
        </> : <div className="emptyEditor"><Icon name="subscribe" /><h3>Добавьте Subscribe-видео</h3></div>}
      </main>

      <aside className="editorControls">
        {current && <>
          <label>Название<input value={current.name} onChange={(event) => patch({ name: event.target.value })} /></label>
          <label>Цвет chromakey<input type="color" value={current.keyColor} onChange={(event) => patch({ keyColor: event.target.value })} /></label>
          <button className="chromaReset" onClick={() => patch({ keyColor: '#00ff00', similarity: 0.10, blend: 0.06, saturation: 1, despill: 0.35 })}>СБРОСИТЬ CHROMAKEY</button>
          <p className="editorHint chromaHint">Пипеткой/кистью в Preview выбери фон Subscribe-видео.</p>
          <SmallRange label="Similarity" value={current.similarity} min={0.001} max={0.6} step={0.001} onChange={(value) => patch({ similarity: value })} />
          <SmallRange label="Blend / мягкость края" value={current.blend} min={0.001} max={0.35} step={0.001} onChange={(value) => patch({ blend: value })} />
            <SmallRange label="Despill / убрать зелёный ореол" value={current.despill} min={0} max={1} step={0.01} onChange={(value) => patch({ despill: value })} />
          <UsageModeControl value={effectiveUsageMode(current)} onChange={(usageMode) => patch({ usageMode, enabled: usageMode !== 'off' })} />
          {effectiveUsageMode(current) === 'interval' && <>
            <div className="usageSliders">
              <SmallRange label="Показывать каждые, мин" value={subscribeInterval(current) / 60} min={1} max={30} step={1} onChange={(value) => patch({ intervalSec: value * 60, repeatEverySec: value * 60 })} />
              <SmallRange label="Длительность показа, сек" value={subscribeDuration(current)} min={2} max={20} step={1} onChange={(value) => patch({ showDurationSec: value })} />
            </div>
            <FirstAppearanceControl value={subscribeFirst(current)} onChange={(firstAppearance) => patch({ firstAppearance })} />
            {subscribeFirst(current) === 'custom' && <label>Своё время<input type="time" step={1} value={secondsToTimeInput(current.customFirstAtSec ?? subscribeInterval(current))} onChange={(event) => patch({ customFirstAtSec: timeInputToSeconds(event.target.value) })} /><small>чч:мм:сс</small></label>}
          </>}
          <p className="editorHint">Subscribe использует тот же aspect-safe compositor, что и Effects.</p>
          <button className="savePreset" onClick={async () => { await saveLibrary([...subscribes], true); setSaved(true); window.setTimeout(() => setSaved(false), 1200); }}><Icon name="save" /> {saved ? 'СОХРАНЕНО ✓' : 'СОХРАНИТЬ PRESET'}</button>
          <button className="savePreset" onClick={() => void saveLibrary(subscribes.map((item) => item.id === current.id ? toggleSubscribeEnabled(item) : item), true)}>{current.enabled ? 'ВЫКЛЮЧИТЬ SUBSCRIBE' : 'ВКЛЮЧИТЬ SUBSCRIBE'}</button>
          <button className="deletePreset" onClick={remove}><Icon name="trash" /> УДАЛИТЬ</button>
        </>}
      </aside>
    </div>
  </div>;
}

function EditorHeader({ title, subtitle, onBack }: { title: string; subtitle: string; onBack: () => void }) {
  return <div className="editorHeader"><div><small>ENDLUME</small><h1>{title}</h1><p>{subtitle}</p></div><button onClick={onBack}>← ВЕРНУТЬСЯ К ПРОЕКТУ</button></div>;
}

function PreviewStage({ title, assets, busy, current, active, anchor, anchorMode, onAnchorPick, onMove, onScale, onPickColor }: {
  title: string;
  assets?: LivePreviewAssets;
  busy: boolean;
  current: EffectPreset;
  active: boolean;
  anchor?: AnchorPoint;
  anchorMode?: boolean;
  onAnchorPick?: (x: number, y: number) => void;
  onMove: (x: number, y: number) => void;
  onScale: (value: number) => void;
  onPickColor: (hex: string) => void;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const modeRef = useRef<'none' | 'drag' | 'resize'>('none');
  const pointerRef = useRef<globalThis.PointerEvent | undefined>(undefined);
  const rafRef = useRef<number | undefined>(undefined);
  const draftRef = useRef({ x: current.x, y: current.y, scale: current.scale });
  const currentRef = useRef(current);
  const moveRef = useRef(onMove);
  const scaleRef = useRef(onScale);
  const grabRef = useRef({ x: 0, y: 0 });
  const guideVRef = useRef<HTMLDivElement>(null);
  const guideHRef = useRef<HTMLDivElement>(null);
  const snapBadgeRef = useRef<HTMLDivElement>(null);
  const [snapEnabled, setSnapEnabled] = useState(true);
  const [guidesEnabled, setGuidesEnabled] = useState(true);
  const [safeEnabled, setSafeEnabled] = useState(true);

  currentRef.current = current;
  moveRef.current = onMove;
  scaleRef.current = onScale;

  useEffect(() => {
    if (modeRef.current === 'none') draftRef.current = { x: current.x, y: current.y, scale: current.scale };
  }, [current.x, current.y, current.scale, current.fullscreen]);

  const clearGuides = () => {
    if (guideVRef.current) guideVRef.current.style.opacity = '0';
    if (guideHRef.current) guideHRef.current.style.opacity = '0';
    if (snapBadgeRef.current) snapBadgeRef.current.style.opacity = '0';
  };

  const showGuide = (axis: 'x' | 'y', percent: number, label: string) => {
    if (!guidesEnabled) return;
    const element = axis === 'x' ? guideVRef.current : guideHRef.current;
    if (!element) return;
    element.style.opacity = '1';
    if (axis === 'x') element.style.left = `${percent}%`;
    else element.style.top = `${percent}%`;
    if (snapBadgeRef.current) {
      snapBadgeRef.current.textContent = label;
      snapBadgeRef.current.style.opacity = '1';
    }
  };

  useEffect(() => {
    const paint = () => {
      rafRef.current = undefined;
      const event = pointerRef.current;
      const stage = stageRef.current;
      const overlay = overlayRef.current;
      const mode = modeRef.current;
      if (!event || !stage || !overlay || mode === 'none') return;

      const stageRect = stage.getBoundingClientRect();
      const overlayRect = overlay.getBoundingClientRect();
      const draft = draftRef.current;

      if (mode === 'drag') {
        const halfW = Math.min(0.49, overlayRect.width / Math.max(1, stageRect.width) / 2);
        const halfH = Math.min(0.49, overlayRect.height / Math.max(1, stageRect.height) / 2);
        let x = (event.clientX - stageRect.left - grabRef.current.x) / Math.max(1, stageRect.width);
        let y = (event.clientY - stageRect.top - grabRef.current.y) / Math.max(1, stageRect.height);
        x = Math.max(halfW, Math.min(1 - halfW, x));
        y = Math.max(halfH, Math.min(1 - halfH, y));
        clearGuides();

        if (snapEnabled && !event.shiftKey) {
          const tx = 10 / Math.max(1, stageRect.width);
          const ty = 10 / Math.max(1, stageRect.height);
          const safe = 0.06;
          const xTargets = [
            { value: halfW, guide: 0, label: 'ЛЕВЫЙ КРАЙ' },
            { value: 0.5, guide: 50, label: 'ЦЕНТР X' },
            { value: 1 - halfW, guide: 100, label: 'ПРАВЫЙ КРАЙ' },
            { value: safe + halfW, guide: 6, label: 'SAFE LEFT' },
            { value: 1 - safe - halfW, guide: 94, label: 'SAFE RIGHT' },
          ];
          const yTargets = [
            { value: halfH, guide: 0, label: 'ВЕРХ' },
            { value: 0.5, guide: 50, label: 'ЦЕНТР Y' },
            { value: 1 - halfH, guide: 100, label: 'НИЗ' },
            { value: safe + halfH, guide: 6, label: 'SAFE TOP' },
            { value: 1 - safe - halfH, guide: 94, label: 'SAFE BOTTOM' },
          ];
          const xHit = xTargets.reduce<typeof xTargets[number] | undefined>((best, item) => Math.abs(x - item.value) <= tx && (!best || Math.abs(x - item.value) < Math.abs(x - best.value)) ? item : best, undefined);
          const yHit = yTargets.reduce<typeof yTargets[number] | undefined>((best, item) => Math.abs(y - item.value) <= ty && (!best || Math.abs(y - item.value) < Math.abs(y - best.value)) ? item : best, undefined);
          if (xHit) { x = xHit.value; showGuide('x', xHit.guide, xHit.label); }
          if (yHit) { y = yHit.value; showGuide('y', yHit.guide, yHit.label); }
        }

        draft.x = x;
        draft.y = y;
        overlay.style.left = `${x * 100}%`;
        overlay.style.top = `${y * 100}%`;
      } else {
        const width = Math.max(16, event.clientX - overlayRect.left);
        const scale = Math.max(0.05, Math.min(1.5, width / Math.max(1, stageRect.width)));
        draft.scale = scale;
        overlay.style.width = `${scale * 100}%`;
      }
    };

    const move = (event: globalThis.PointerEvent) => {
      if (modeRef.current === 'none') return;
      pointerRef.current = event;
      if (rafRef.current == null) rafRef.current = requestAnimationFrame(paint);
    };

    const up = (event: globalThis.PointerEvent) => {
      const mode = modeRef.current;
      if (mode === 'none') return;
      pointerRef.current = event;
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = undefined;
      paint();
      modeRef.current = 'none';
      clearGuides();
      const draft = draftRef.current;
      if (mode === 'drag') moveRef.current(draft.x, draft.y);
      else scaleRef.current(draft.scale);
    };

    window.addEventListener('pointermove', move, { passive: true });
    window.addEventListener('pointerup', up, { passive: true });
    window.addEventListener('pointercancel', up, { passive: true });
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, [snapEnabled, guidesEnabled]);

  const overlayStyle: React.CSSProperties = current.fullscreen ? {
    left: '0%', top: '0%', width: '100%', height: '100%', transform: 'none', touchAction: 'none',
  } : {
    left: `${current.x * 100}%`,
    top: `${current.y * 100}%`,
    width: `${Math.max(5, current.scale * 100)}%`,
    transform: 'translate(-50%, -50%)',
    touchAction: 'none',
    willChange: 'left, top, width, transform',
    contain: 'layout style paint',
  };

  const begin = (mode: 'drag' | 'resize', event: React.PointerEvent) => {
    if (current.fullscreen) return;
    event.preventDefault();
    event.stopPropagation();
    draftRef.current = { x: currentRef.current.x, y: currentRef.current.y, scale: currentRef.current.scale };
    pointerRef.current = event.nativeEvent;
    modeRef.current = mode;
    if (mode === 'drag') {
      const overlayRect = overlayRef.current?.getBoundingClientRect();
      if (overlayRect) {
        grabRef.current = {
          x: event.clientX - (overlayRect.left + overlayRect.width / 2),
          y: event.clientY - (overlayRect.top + overlayRect.height / 2),
        };
      } else grabRef.current = { x: 0, y: 0 };
    }
  };

  const align = (position: 'center' | 'centerX' | 'centerY' | 'left' | 'right' | 'top' | 'bottom') => {
    const stageRect = stageRef.current?.getBoundingClientRect();
    const overlayRect = overlayRef.current?.getBoundingClientRect();
    const halfW = stageRect && overlayRect ? Math.min(0.49, overlayRect.width / Math.max(1, stageRect.width) / 2) : Math.min(0.49, current.scale / 2);
    const halfH = stageRect && overlayRect ? Math.min(0.49, overlayRect.height / Math.max(1, stageRect.height) / 2) : Math.min(0.49, current.scale / 2);
    let x = current.x;
    let y = current.y;
    if (position === 'center') { x = 0.5; y = 0.5; }
    if (position === 'centerX') x = 0.5;
    if (position === 'centerY') y = 0.5;
    if (position === 'left') x = halfW;
    if (position === 'right') x = 1 - halfW;
    if (position === 'top') y = halfH;
    if (position === 'bottom') y = 1 - halfH;
    onMove(clamp01(x), clamp01(y));
  };

  const keyMove = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (current.fullscreen) return;
    if ((event.metaKey || event.ctrlKey) && event.key === '0') {
      event.preventDefault();
      align('center');
      return;
    }
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const step = event.shiftKey ? 0.02 : 0.003;
    let x = current.x;
    let y = current.y;
    if (event.key === 'ArrowLeft') x -= step;
    if (event.key === 'ArrowRight') x += step;
    if (event.key === 'ArrowUp') y -= step;
    if (event.key === 'ArrowDown') y += step;
    onMove(clamp01(x), clamp01(y));
  };

  const metric = (label: string, value: number, onValue: (value: number) => void) => <label className="smartMetricInput"><span>{label}</span><input type="number" min="0" max="100" step="0.1" value={(value * 100).toFixed(1)} onChange={(event) => onValue(clamp01(Number(event.target.value) / 100))} /><em>%</em></label>;

  return <div className="previewStage livePreviewStage smartAlignStage" ref={stageRef} tabIndex={0} onKeyDown={keyMove}>
    <div className="previewLabel">{title}</div>
    <LiveCompositePreview assets={assets} effect={current} active={active} busy={busy} overlayRef={overlayRef} overlayStyle={overlayStyle} anchor={anchor} anchorMode={anchorMode} onAnchorPick={onAnchorPick} onDragStart={(event) => begin('drag', event)} onResizeStart={(event) => begin('resize', event)} onPickColor={onPickColor} />
    <div className={`smartGuideLayer ${guidesEnabled ? 'visible' : ''}`} aria-hidden="true">
      <i className="smartGuideStatic vertical" /><i className="smartGuideStatic horizontal" />
      {safeEnabled && <i className="smartSafeArea" />}
      <span className="smartEdgeLabel left">0</span><span className="smartEdgeLabel centerX">СЕРЕДИНА</span><span className="smartEdgeLabel right">100</span>
      <span className="smartEdgeLabel top">0</span><span className="smartEdgeLabel centerY">СЕРЕДИНА</span><span className="smartEdgeLabel bottom">100</span>
      <div ref={guideVRef} className="smartDynamicGuide vertical" /><div ref={guideHRef} className="smartDynamicGuide horizontal" /><div ref={snapBadgeRef} className="smartSnapBadge" />
    </div>
    {!current.fullscreen && <>
      <div className="smartAlignToolbar">
        <button onClick={() => align('center')}>◎ АВТОЦЕНТР</button><button onClick={() => align('centerX')}>↔ X</button><button onClick={() => align('centerY')}>↕ Y</button>
        <button onClick={() => align('left')}>←</button><button onClick={() => align('right')}>→</button><button onClick={() => align('top')}>↑</button><button onClick={() => align('bottom')}>↓</button>
        <button className={snapEnabled ? 'active' : ''} onClick={() => setSnapEnabled((value) => !value)}>МАГНИТ</button>
        <button className={guidesEnabled ? 'active' : ''} onClick={() => setGuidesEnabled((value) => !value)}>ЛИНИИ</button>
        <button className={safeEnabled ? 'active' : ''} onClick={() => setSafeEnabled((value) => !value)}>SAFE</button>
      </div>
      <div className="smartMetrics">
        {metric('X', current.x, (value) => onMove(value, current.y))}
        {metric('Y', current.y, (value) => onMove(current.x, value))}
        <label className="smartMetricInput"><span>SIZE</span><input type="number" min="5" max="150" step="1" value={(current.scale * 100).toFixed(0)} onChange={(event) => onScale(Math.max(0.05, Math.min(1.5, Number(event.target.value) / 100)))} /><em>%</em></label>
      </div>
    </>}
    <div className="smartAlignHint">{anchorMode ? 'Кликни по объекту на изображении — anchor сохранится для этой сцены' : 'Shift + drag — без магнита • стрелки — точная подгонка • ⌘0 — центр'}</div>
  </div>;
}

function UsageModeControl({ value, onChange }: { value: EffectUsageMode; onChange: (value: EffectUsageMode) => void }) {
  return <div className="usageModeBlock"><span>ИСПОЛЬЗОВАНИЕ</span><div className="usageSegments">{(['off','always','interval'] as EffectUsageMode[]).map((mode) => <button type="button" key={mode} className={value === mode ? 'selected' : ''} onClick={() => onChange(mode)}>{mode === 'off' ? 'ВЫКЛ' : mode === 'always' ? 'ВСЕГДА' : 'ПО ИНТЕРВАЛУ'}</button>)}</div></div>;
}
function FirstAppearanceControl({ value, onChange }: { value: SubscribeFirstAppearance; onChange: (value: SubscribeFirstAppearance) => void }) {
  return <div className="usageModeBlock"><span>ПЕРВОЕ ПОЯВЛЕНИЕ</span><div className="usageSegments firstAppearance">{(['after-interval','immediate','custom'] as SubscribeFirstAppearance[]).map((mode) => <button type="button" key={mode} className={value === mode ? 'selected' : ''} onClick={() => onChange(mode)}>{mode === 'after-interval' ? 'ЧЕРЕЗ ИНТЕРВАЛ' : mode === 'immediate' ? 'СРАЗУ' : 'СВОЁ ВРЕМЯ'}</button>)}</div></div>;
}
function secondsToTimeInput(sec:number){const value=Math.max(0,Math.round(sec));const h=Math.floor(value/3600);const m=Math.floor((value%3600)/60);const ss=value%60;return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(ss).padStart(2,'0')}`;}
function timeInputToSeconds(value:string){const parts=value.split(':').map(Number);if(parts.some(Number.isNaN))return 0;return Math.max(0,(parts.length===3?parts[0]*3600+parts[1]*60+parts[2]:parts[0]*3600+parts[1]*60));}

function SmallRange({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (value: number) => void }) {
  return <div className="smallRange"><div><span>{label}</span><b>{value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')}</b></div><Range value={value} min={min} max={max} step={step} onChange={onChange} /></div>;
}

function fmtEditorTime(sec: number) {
  const value = Math.max(0, Math.round(sec));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const seconds = value % 60;
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}` : `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function Timeline({ start, end, total, onChange }: { start: number; end: number | null; total: number; onChange: (start: number, end: number | null) => void }) {
  const safeTotal = Math.max(1, total);
  const safeEnd = Math.max(start + 1, Math.min(safeTotal, end ?? safeTotal));
  const mid = start + (safeEnd - start) / 2;
  const duration = Math.max(0, safeEnd - start);
  const pct = (value: number) => `${Math.max(0, Math.min(100, value / safeTotal * 100))}%`;
  const widthPct = Math.max(0, Math.min(100, (safeEnd - start) / safeTotal * 100));
  return <div className="timeline smartTiming">
    <div className="timelineHead"><b>ВРЕМЯ ЭФФЕКТА</b><span>{fmtEditorTime(start)} → {end == null ? 'до конца' : fmtEditorTime(safeEnd)}</span></div>
    <div className="smartTimingSummary">
      <span><small>НАЧАЛО</small><b>{fmtEditorTime(start)}</b></span><span><small>СЕРЕДИНА</small><b>{fmtEditorTime(mid)}</b></span><span><small>КОНЕЦ</small><b>{end == null ? 'КОНЕЦ ВИДЕО' : fmtEditorTime(safeEnd)}</b></span><span><small>ДЛИТЕЛЬНОСТЬ</small><b>{fmtEditorTime(duration)}</b></span>
    </div>
    <div className="smartTimingMap"><i className="smartTimingActive" style={{ left: pct(start), width: `${widthPct}%` }} /><b className="start" style={{ left: pct(start) }} /><b className="mid" style={{ left: pct(mid) }} /><b className="end" style={{ left: pct(safeEnd) }} /></div>
    <div className="dualRange"><Range value={start} min={0} max={safeTotal} step={1} onChange={(value) => onChange(Math.min(value, safeEnd - 1), end)} minLabel="0:00" maxLabel="конец видео" /><Range value={safeEnd} min={0} max={safeTotal} step={1} onChange={(value) => onChange(start, value >= safeTotal ? null : Math.max(value, start + 1))} minLabel="начало" maxLabel="до конца" /></div>
  </div>;
}

function SubscribeTimeline({ current }: { current: SubscribePreset }) {
  const total = useApp((s) => s.settings.durationHours * 3600);
  const mode = effectiveUsageMode(current);
  const interval = subscribeInterval(current);
  const duration = subscribeDuration(current);
  const marks = useMemo(() => {
    if (mode === 'off') return [] as number[];
    if (mode === 'always') return [0];
    if (current.usageMode === undefined) {
      const values = [current.firstAtSec, current.secondAtSec].filter((value, index, all) => value >= 0 && value < total && all.indexOf(value) === index);
      if (current.repeatEverySec > 0) for (let time = Math.max(current.firstAtSec, current.secondAtSec) + current.repeatEverySec; time < total && values.length < 10000; time += current.repeatEverySec) values.push(time);
      return values.sort((a, b) => a - b);
    }
    const first = subscribeFirst(current) === 'immediate' ? 0 : subscribeFirst(current) === 'custom' ? Math.max(0, current.customFirstAtSec ?? interval) : interval;
    const values:number[] = [];
    for (let time = first; time < total && values.length < 10000; time += interval) values.push(time);
    return values;
  }, [mode, interval, duration, current.usageMode, current.firstAtSec, current.secondAtSec, current.repeatEverySec, current.firstAppearance, current.customFirstAtSec, total]);
  const totalVisible = mode === 'always' ? total : marks.reduce((sum, mark) => sum + Math.min(duration, Math.max(0, total - mark)), 0);
  const last = marks.at(-1) ?? 0;
  return <div className="timeline subscribeTimeline smartTiming">
    <div className="timelineHead"><b>РАСПИСАНИЕ SUBSCRIBE</b><span>{mode === 'always' ? 'весь ролик' : `${marks.length} появлений • ${Math.round(totalVisible)} сек суммарно`}</span></div>
    <div className="smartTimingSummary compact"><span><small>РЕЖИМ</small><b>{usageLabel(current)}</b></span><span><small>ПЕРВОЕ</small><b>{marks.length ? fmtEditorTime(marks[0]) : '—'}</b></span><span><small>ПОСЛЕДНЕЕ</small><b>{marks.length ? fmtEditorTime(last) : '—'}</b></span><span><small>ИНТЕРВАЛ</small><b>{mode === 'interval' ? fmtEditorTime(interval) : '—'}</b></span></div>
    {marks.length > 0 && mode === 'interval' && <div className="timeTrack">{marks.map((mark, index) => <i key={`${mark}-${index}`} style={{ left: `${mark / Math.max(1, total) * 100}%` }} title={fmtEditorTime(mark)} />)}</div>}
  </div>;
}
