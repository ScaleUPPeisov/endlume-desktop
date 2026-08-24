from pathlib import Path
import re

EDITORS = Path("src/pages/Editors.tsx")
text = EDITORS.read_text(encoding="utf-8")

# New Subscribe overlays start centered just like normal Effects.
text = text.replace(
    "const emptySubscribe=(source=''):SubscribePreset=>({...emptyEffect(source),name:source.split(/[\\\\/]/).pop()||'Subscribe',scale:.32,x:.16,y:.16,firstAtSec:10,secondAtSec:20,repeatEverySec:300});",
    "const emptySubscribe=(source=''):SubscribePreset=>({...emptyEffect(source),name:source.split(/[\\\\/]/).pop()||'Subscribe',scale:.32,x:.5,y:.5,firstAtSec:10,secondAtSec:20,repeatEverySec:300});",
)

preview_stage = r'''function PreviewStage({title,assets,busy,current,onMove,onScale,onPickColor}:{title:string;assets?:LivePreviewAssets;busy:boolean;current:EffectPreset;onMove:(x:number,y:number)=>void;onScale:(v:number)=>void;onPickColor:(hex:string)=>void}){
  const stageRef=useRef<HTMLDivElement>(null),overlayRef=useRef<HTMLDivElement>(null),modeRef=useRef<'none'|'drag'|'resize'>('none'),rafRef=useRef<number|undefined>(undefined),pointerRef=useRef<globalThis.PointerEvent|undefined>(undefined),draftRef=useRef({x:current.x,y:current.y,scale:current.scale}),currentRef=useRef(current),moveRef=useRef(onMove),scaleRef=useRef(onScale),grabRef=useRef({x:0,y:0}),guideVRef=useRef<HTMLDivElement>(null),guideHRef=useRef<HTMLDivElement>(null),snapBadgeRef=useRef<HTMLDivElement>(null);
  const [snapEnabled,setSnapEnabled]=useState(true),[guidesEnabled,setGuidesEnabled]=useState(true),[safeEnabled,setSafeEnabled]=useState(true);
  currentRef.current=current;moveRef.current=onMove;scaleRef.current=onScale;
  const clamp01=(v:number)=>Math.max(0,Math.min(1,v));
  const setDynamicGuide=(axis:'x'|'y',percent:number|undefined,label='')=>{const el=axis==='x'?guideVRef.current:guideHRef.current;if(!el)return;if(percent==null){el.style.opacity='0';return}el.style.opacity='1';if(axis==='x')el.style.left=`${percent}%`;else el.style.top=`${percent}%`;const badge=snapBadgeRef.current;if(badge&&label){badge.textContent=label;badge.style.opacity='1'}};
  const clearDynamicGuides=()=>{if(guideVRef.current)guideVRef.current.style.opacity='0';if(guideHRef.current)guideHRef.current.style.opacity='0';if(snapBadgeRef.current)snapBadgeRef.current.style.opacity='0'};
  useEffect(()=>{if(modeRef.current==='none')draftRef.current={x:current.x,y:current.y,scale:current.scale}},[current.x,current.y,current.scale,current.fullscreen]);
  useEffect(()=>{
    const paint=()=>{rafRef.current=undefined;const e=pointerRef.current,stage=stageRef.current,overlay=overlayRef.current,mode=modeRef.current;if(!e||!stage||!overlay||mode==='none')return;const r=stage.getBoundingClientRect(),d=draftRef.current;if(mode==='drag'){
      const or=overlay.getBoundingClientRect(),aw=Math.max(1,r.width-or.width),ah=Math.max(1,r.height-or.height);let x=clamp01((e.clientX-r.left-grabRef.current.x)/aw),y=clamp01((e.clientY-r.top-grabRef.current.y)/ah);let xLabel='',yLabel='',xGuide:number|undefined,yGuide:number|undefined;
      if(snapEnabled&&!e.shiftKey){const threshold=10;const rawLeft=x*aw,rawTop=y*ah;const mx=r.width*.06,my=r.height*.06;const xs=[{v:0,p:0,l:'ЛЕВЫЙ КРАЙ'},{v:.5,p:aw*.5,l:'ЦЕНТР X'},{v:1,p:aw,l:'ПРАВЫЙ КРАЙ'},{v:clamp01(mx/aw),p:mx,l:'SAFE LEFT'},{v:clamp01((aw-mx)/aw),p:Math.max(0,aw-mx),l:'SAFE RIGHT'}];const ys=[{v:0,p:0,l:'ВЕРХ'},{v:.5,p:ah*.5,l:'ЦЕНТР Y'},{v:1,p:ah,l:'НИЗ'},{v:clamp01(my/ah),p:my,l:'SAFE TOP'},{v:clamp01((ah-my)/ah),p:Math.max(0,ah-my),l:'SAFE BOTTOM'}];let bx:{v:number;p:number;l:string}|undefined,by:{v:number;p:number;l:string}|undefined,bdx=threshold+1,bdy=threshold+1;for(const c of xs){const dd=Math.abs(rawLeft-c.p);if(dd<bdx){bdx=dd;bx=c}}for(const c of ys){const dd=Math.abs(rawTop-c.p);if(dd<bdy){bdy=dd;by=c}}if(bx&&bdx<=threshold){x=bx.v;xLabel=bx.l;xGuide=bx.l.includes('SAFE')?(bx.l.includes('RIGHT')?94:6):(bx.v*100)}if(by&&bdy<=threshold){y=by.v;yLabel=by.l;yGuide=by.l.includes('SAFE')?(by.l.includes('BOTTOM')?94:6):(by.v*100)}}
      d.x=x;d.y=y;overlay.style.left=`${x*100}%`;overlay.style.top=`${y*100}%`;overlay.style.transform=`translate(${-x*100}%,${-y*100}%)`;if(guidesEnabled){setDynamicGuide('x',xGuide,xLabel);setDynamicGuide('y',yGuide,yLabel)}else clearDynamicGuides();
    }else{const or=overlay.getBoundingClientRect(),left=or.left-r.left;const target=Math.max(12,e.clientX-r.left-left);d.scale=Math.max(.05,Math.min(1.5,target/Math.max(1,r.width)));overlay.style.width=`${d.scale*100}%`;}
    };
    const move=(e:globalThis.PointerEvent)=>{if(modeRef.current==='none')return;pointerRef.current=e;if(rafRef.current==null)rafRef.current=requestAnimationFrame(paint)};
    const up=(e:globalThis.PointerEvent)=>{const mode=modeRef.current;if(mode==='none')return;pointerRef.current=e;if(rafRef.current!=null){cancelAnimationFrame(rafRef.current);rafRef.current=undefined}paint();modeRef.current='none';clearDynamicGuides();const d=draftRef.current;if(mode==='drag')moveRef.current(d.x,d.y);else scaleRef.current(d.scale);};
    window.addEventListener('pointermove',move,{passive:true});window.addEventListener('pointerup',up,{passive:true});window.addEventListener('pointercancel',up,{passive:true});return()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up);window.removeEventListener('pointercancel',up);if(rafRef.current!=null)cancelAnimationFrame(rafRef.current)};
  },[snapEnabled,guidesEnabled]);
  const overlayStyle:React.CSSProperties=current.fullscreen?{left:'0%',top:'0%',width:'100%',height:'100%',transform:'none',touchAction:'none'}:{left:`${current.x*100}%`,top:`${current.y*100}%`,width:`${Math.max(5,current.scale*100)}%`,aspectRatio:'1 / 1',transform:`translate(${-current.x*100}%,${-current.y*100}%)`,touchAction:'none',willChange:'left, top, width, transform',contain:'layout style paint'};
  const begin=(mode:'drag'|'resize',e:React.PointerEvent)=>{if(current.fullscreen)return;e.preventDefault();e.stopPropagation();draftRef.current={x:currentRef.current.x,y:currentRef.current.y,scale:currentRef.current.scale};pointerRef.current=e.nativeEvent;modeRef.current=mode;if(mode==='drag'){const or=overlayRef.current?.getBoundingClientRect();grabRef.current=or?{x:e.clientX-or.left,y:e.clientY-or.top}:{x:0,y:0}}};
  const align=(x:number,y:number)=>{onMove(clamp01(x),clamp01(y))};
  const keyMove=(e:React.KeyboardEvent<HTMLDivElement>)=>{if(current.fullscreen)return;const step=e.shiftKey?.02:.003;if((e.metaKey||e.ctrlKey)&&e.key==='0'){e.preventDefault();align(.5,.5);return}if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();let x=current.x,y=current.y;if(e.key==='ArrowLeft')x-=step;if(e.key==='ArrowRight')x+=step;if(e.key==='ArrowUp')y-=step;if(e.key==='ArrowDown')y+=step;align(x,y)};
  const metric=(label:string,value:number,onValue:(v:number)=>void)=><label className="smartMetricInput"><span>{label}</span><input type="number" min="0" max="100" step="0.1" value={(value*100).toFixed(1)} onChange={e=>onValue(clamp01(Number(e.target.value)/100))}/><em>%</em></label>;
  return <div className="previewStage livePreviewStage smartAlignStage" ref={stageRef} tabIndex={0} onKeyDown={keyMove}>
    <div className="previewLabel">{title}</div>
    <LiveCompositePreview assets={assets} effect={current} busy={busy} overlayRef={overlayRef} overlayStyle={overlayStyle} onDragStart={e=>begin('drag',e)} onResizeStart={e=>begin('resize',e)} onPickColor={onPickColor}/>
    <div className={`smartGuideLayer ${guidesEnabled?'visible':''}`} aria-hidden="true"><i className="smartGuideStatic vertical"/><i className="smartGuideStatic horizontal"/>{safeEnabled&&<i className="smartSafeArea"/>}<span className="smartEdgeLabel left">0</span><span className="smartEdgeLabel centerX">СЕРЕДИНА</span><span className="smartEdgeLabel right">100</span><span className="smartEdgeLabel top">0</span><span className="smartEdgeLabel centerY">СЕРЕДИНА</span><span className="smartEdgeLabel bottom">100</span><div ref={guideVRef} className="smartDynamicGuide vertical"/><div ref={guideHRef} className="smartDynamicGuide horizontal"/><div ref={snapBadgeRef} className="smartSnapBadge"/></div>
    {!current.fullscreen&&<><div className="smartAlignToolbar"><button onClick={()=>align(.5,.5)} title="Автоматически поставить по центру">◎ АВТОЦЕНТР</button><button onClick={()=>align(.5,current.y)}>↔ X</button><button onClick={()=>align(current.x,.5)}>↕ Y</button><button onClick={()=>align(0,current.y)}>←</button><button onClick={()=>align(1,current.y)}>→</button><button onClick={()=>align(current.x,0)}>↑</button><button onClick={()=>align(current.x,1)}>↓</button><button className={snapEnabled?'active':''} onClick={()=>setSnapEnabled(v=>!v)}>МАГНИТ</button><button className={guidesEnabled?'active':''} onClick={()=>setGuidesEnabled(v=>!v)}>ЛИНИИ</button><button className={safeEnabled?'active':''} onClick={()=>setSafeEnabled(v=>!v)}>SAFE</button></div><div className="smartMetrics">{metric('X',current.x,v=>onMove(v,current.y))}{metric('Y',current.y,v=>onMove(current.x,v))}<label className="smartMetricInput"><span>SIZE</span><input type="number" min="5" max="150" step="1" value={(current.scale*100).toFixed(0)} onChange={e=>onScale(Math.max(.05,Math.min(1.5,Number(e.target.value)/100)))}/><em>%</em></label></div></>}
    <div className="smartAlignHint">Shift + drag — без магнита • стрелки — точная подгонка • ⌘0 — центр</div>
  </div>
}
'''

pattern = re.compile(r"function PreviewStage\([\s\S]*?\n}\n\nfunction SmallRange", re.M)
if not pattern.search(text):
    raise SystemExit("Smart Align: PreviewStage block not found")
text = pattern.sub(preview_stage + "\nfunction SmallRange", text, count=1)

fmt_and_timeline = r'''function fmtEditorTime(sec:number){const s=Math.max(0,Math.round(sec));const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),ss=s%60;return h>0?`${h}:${String(m).padStart(2,'0')}:${String(ss).padStart(2,'0')}`:`${m}:${String(ss).padStart(2,'0')}`}

function Timeline({start,end,total,onChange}:{start:number;end:number|null;total:number;onChange:(s:number,e:number|null)=>void}){const safeEnd=Math.max(start+1,Math.min(total,end??total)),mid=start+(safeEnd-start)/2,duration=Math.max(0,safeEnd-start),pct=(v:number)=>`${Math.max(0,Math.min(100,(v/Math.max(1,total))*100))}%`;return <div className="timeline smartTiming"><div className="timelineHead"><b>ВРЕМЯ ЭФФЕКТА</b><span>{fmtEditorTime(start)} → {end==null?'до конца':fmtEditorTime(safeEnd)}</span></div><div className="smartTimingSummary"><span><small>НАЧАЛО</small><b>{fmtEditorTime(start)}</b></span><span><small>СЕРЕДИНА</small><b>{fmtEditorTime(mid)}</b></span><span><small>КОНЕЦ</small><b>{end==null?'КОНЕЦ ВИДЕО':fmtEditorTime(safeEnd)}</b></span><span><small>ДЛИТЕЛЬНОСТЬ</small><b>{fmtEditorTime(duration)}</b></span></div><div className="smartTimingMap"><i className="smartTimingActive" style={{left:pct(start),width:`${Math.max(0,((safeEnd-start)/Math.max(1,total))*100))}%`}}/><b className="start" style={{left:pct(start)}}/><b className="mid" style={{left:pct(mid)}}/><b className="end" style={{left:pct(safeEnd)}}/></div><div className="dualRange"><Range value={start} min={0} max={total} step={1} onChange={v=>onChange(Math.min(v,safeEnd-1),end)} minLabel="0:00" maxLabel="конец видео"/><Range value={safeEnd} min={0} max={total} step={1} onChange={v=>onChange(start,v>=total?null:Math.max(v,start+1))} minLabel="начало" maxLabel="до конца"/></div></div>}
'''
pattern_timeline = re.compile(r"function Timeline\([\s\S]*?\n\nfunction SubscribeTimeline", re.M)
if not pattern_timeline.search(text):
    raise SystemExit("Smart Align: Timeline block not found")
text = pattern_timeline.sub(fmt_and_timeline + "\nfunction SubscribeTimeline", text, count=1)

# Better time summary for Subscribe schedule without changing render semantics.
subscribe_old = re.search(r"function SubscribeTimeline\([\s\S]*$", text)
if subscribe_old:
    replacement = r'''function SubscribeTimeline({current,onChange}:{current:SubscribePreset;onChange:(p:Partial<SubscribePreset>)=>void}){const total=useApp(s=>s.settings.durationHours*3600);const marks=useMemo(()=>{const a=[current.firstAtSec,current.secondAtSec];for(let t=current.secondAtSec+current.repeatEverySec;t<total;t+=current.repeatEverySec)a.push(t);return a},[current.firstAtSec,current.secondAtSec,current.repeatEverySec,total]);const last=marks.at(-1)??current.secondAtSec;return <div className="timeline subscribeTimeline smartTiming"><div className="timelineHead"><b>РАСПИСАНИЕ SUBSCRIBE</b><span>{marks.length} показов</span></div><div className="smartTimingSummary compact"><span><small>ПЕРВОЕ</small><b>{fmtEditorTime(current.firstAtSec)}</b></span><span><small>ВТОРОЕ</small><b>{fmtEditorTime(current.secondAtSec)}</b></span><span><small>ПОСЛЕДНЕЕ</small><b>{fmtEditorTime(last)}</b></span><span><small>ИНТЕРВАЛ</small><b>{fmtEditorTime(current.repeatEverySec)}</b></span></div><div className="timeTrack">{marks.map((m,i)=><i key={i} style={{left:`${(m/total)*100}%`}} title={fmtEditorTime(m)}/>)}</div></div>}'''
    text = text[:subscribe_old.start()] + replacement + "\n"

EDITORS.write_text(text, encoding="utf-8")

# Keep all visible local-build labels in sync.
for ui_file in [Path("src/pages/SettingsPage.tsx"), Path("src/tauri.ts")]:
    if ui_file.exists():
        t = ui_file.read_text(encoding="utf-8")
        for old in ["1.0.0-alpha.8.19","1.0.0-alpha.8.20","1.0.0-alpha.8.21","1.0.0-alpha.8.22","1.0.0-alpha.8.23"]:
            t = t.replace(old, "1.0.0-alpha.8.24")
        ui_file.write_text(t, encoding="utf-8")

print("ENDLUME alpha.8.24 Smart Align / Guides / Timing hotfix applied")
