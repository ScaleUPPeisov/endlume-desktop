from pathlib import Path

path = Path("src-tauri/src/render.rs")
text = path.read_text(encoding="utf-8")
old = '''      "crossfade"=>{let cf=s.crossfade_sec.min((d/3.0).max(0.15)).max(0.1);duration=d;args.extend(vec!["-i",media,"-i",media].into_iter().map(String::from));graph=format!("[0:v]trim=duration={d},setpts=PTS-STARTPTS[a];[1:v]trim=duration={d},setpts=PTS-STARTPTS[b];[a][b]xfade=transition=fade:duration={cf}:offset={},trim=start={cf}:duration={d},setpts=PTS-STARTPTS[x];{}[outv]",(d-cf).max(0.1),base_filter(s,"x"));},'''
new = '''      "crossfade"=>{let cf=s.crossfade_sec.min((d/3.0).max(0.15)).max(0.1);duration=d;args.extend(vec!["-i",media,"-i",media].into_iter().map(String::from));graph=format!("[0:v]trim=duration={d},setpts=PTS-STARTPTS,fps={},settb=AVTB[a];[1:v]trim=duration={d},setpts=PTS-STARTPTS,fps={},settb=AVTB[b];[a][b]xfade=transition=fade:duration={cf}:offset={},trim=start={cf}:duration={d},setpts=PTS-STARTPTS[x];{}[outv]",s.fps,s.fps,(d-cf).max(0.1),base_filter(s,"x"));},'''

if new in text:
    print("ENDLUME crossfade CFR fix already applied")
elif old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("ENDLUME crossfade CFR fix applied")
else:
    raise SystemExit("Expected crossfade render source was not found; refusing to patch an unknown render pipeline")
