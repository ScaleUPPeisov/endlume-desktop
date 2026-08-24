from pathlib import Path
import re

p = Path("src/pages/Editors.tsx")
text = p.read_text(encoding="utf-8")

# Replace the generated timing helper + Timeline as one compile-safe block.
# This avoids the previous nested template-expression that produced TS1005 on local builds.
fixed_timing = r'''function fmtEditorTime(sec:number){
  const s=Math.max(0,Math.round(sec));
  const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),ss=s%60;
  return h>0?`${h}:${String(m).padStart(2,'0')}:${String(ss).padStart(2,'0')}`:`${m}:${String(ss).padStart(2,'0')}`;
}

function Timeline({start,end,total,onChange}:{start:number;end:number|null;total:number;onChange:(s:number,e:number|null)=>void}){
  const safeEnd=Math.max(start+1,Math.min(total,end??total));
  const mid=start+(safeEnd-start)/2;
  const duration=Math.max(0,safeEnd-start);
  const pct=(v:number)=>`${Math.max(0,Math.min(100,(v/Math.max(1,total))*100))}%`;
  const widthPct=Math.max(0,Math.min(100,((safeEnd-start)/Math.max(1,total))*100));
  return <div className="timeline smartTiming">
    <div className="timelineHead"><b>ВРЕМЯ ЭФФЕКТА</b><span>{fmtEditorTime(start)} → {end==null?'до конца':fmtEditorTime(safeEnd)}</span></div>
    <div className="smartTimingSummary">
      <span><small>НАЧАЛО</small><b>{fmtEditorTime(start)}</b></span>
      <span><small>СЕРЕДИНА</small><b>{fmtEditorTime(mid)}</b></span>
      <span><small>КОНЕЦ</small><b>{end==null?'КОНЕЦ ВИДЕО':fmtEditorTime(safeEnd)}</b></span>
      <span><small>ДЛИТЕЛЬНОСТЬ</small><b>{fmtEditorTime(duration)}</b></span>
    </div>
    <div className="smartTimingMap">
      <i className="smartTimingActive" style={{left:pct(start),width:`${widthPct}%`}}/>
      <b className="start" style={{left:pct(start)}}/>
      <b className="mid" style={{left:pct(mid)}}/>
      <b className="end" style={{left:pct(safeEnd)}}/>
    </div>
    <div className="dualRange">
      <Range value={start} min={0} max={total} step={1} onChange={v=>onChange(Math.min(v,safeEnd-1),end)} minLabel="0:00" maxLabel="конец видео"/>
      <Range value={safeEnd} min={0} max={total} step={1} onChange={v=>onChange(start,v>=total?null:Math.max(v,start+1))} minLabel="начало" maxLabel="до конца"/>
    </div>
  </div>;
}
'''

pattern = re.compile(r"function fmtEditorTime\([\s\S]*?\n\nfunction SubscribeTimeline", re.M)
if pattern.search(text):
    text = pattern.sub(fixed_timing + "\nfunction SubscribeTimeline", text, count=1)
else:
    # Fallback for a partially generated editor: replace Timeline only and inject helper once.
    timeline_only = re.compile(r"function Timeline\([\s\S]*?\n\nfunction SubscribeTimeline", re.M)
    if not timeline_only.search(text):
        raise SystemExit("Smart Align post-check failed: Timeline block not found")
    text = timeline_only.sub(fixed_timing + "\nfunction SubscribeTimeline", text, count=1)

# Normalize any malformed Shift ternary left by an older generated patch.
text = text.replace("e.shiftKey?.02:.003", "e.shiftKey ? 0.02 : 0.003")
text = text.replace("e.shiftKey?.02:.005", "e.shiftKey ? 0.02 : 0.005")

# Hard fail before TypeScript if the generated editor is incomplete.
required = [
    "smartAlignToolbar",
    "smartGuideLayer",
    "smartSafeArea",
    "smartTimingSummary",
    "АВТОЦЕНТР",
    "Shift + drag",
    "widthPct",
    "effects-v4-aspect-safe" if Path("src-tauri/src/cache.rs").exists() else "smartAlignStage",
]
for marker in required:
    targets = text
    if marker == "effects-v4-aspect-safe":
        targets = Path("src-tauri/src/cache.rs").read_text(encoding="utf-8")
    if marker not in targets:
        raise SystemExit(f"Smart Align validation failed: missing {marker}")

if text.count("function fmtEditorTime(") != 1:
    raise SystemExit("Smart Align validation failed: timing helper must exist exactly once")
if "shiftKey?." in text or "*100))}%" in text:
    raise SystemExit("Smart Align validation failed: malformed generated TypeScript remains")

p.write_text(text, encoding="utf-8")

# Keep Settings → Updates history complete through the current local release.
history_path = Path("src/components/ReleaseHistory.tsx")
if history_path.exists():
    history = history_path.read_text(encoding="utf-8").replace("current:true,", "")
    if "1.0.0-alpha.8.24" not in history:
        marker = "const releases:Release[]=[\n"
        entries = """  {version:'1.0.0-alpha.8.24',date:'25.08.2026',current:true,title:'Smart Align: автоцентр, магнитные направляющие и точные временные метки',items:[
    'Новые Effects и Subscribe стартуют по центру кадра; кнопка «АВТОЦЕНТР» возвращает выбранный overlay точно в середину.',
    'Добавлены магнитные привязки к центру, краям и Safe Area. Shift + drag временно отключает магнит для полностью ручной подгонки.',
    'В Preview постоянно видны центр, границы 0/100 и безопасная зона; при snap появляется динамическая cyan/pink направляющая.',
    'Добавлены точные X / Y / SIZE в процентах, кнопки выравнивания и управление стрелками; ⌘0 мгновенно центрирует overlay.',
    'Timeline явно показывает Начало / Середину / Конец / Длительность эффекта, а Subscribe — первое, второе, последнее появление и интервал.',
    'Smart Align использует ту же нормализованную x/y/scale геометрию, что и финальный render.'
  ]},
"""
        if marker not in history:
            raise SystemExit("Release history marker not found")
        history = history.replace(marker, marker + entries, 1)
    history_path.write_text(history, encoding="utf-8")

print("ENDLUME alpha.8.24 Smart Align compile-safe post-check passed")
