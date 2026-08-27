from pathlib import Path

p=Path('src/store.ts')
s=p.read_text(encoding='utf-8')
old="migrate:(persisted:any)=>{const p=(persisted||{}) as Partial<State>;if(p.settings){p.settings={...p.settings,fps:p.settings.fps===60?30:p.settings.fps,crossfadeSec:0,normalizeLufs:false,codec:'h265'};}return p;}"
new="migrate:(persisted:any)=>{const p:any=persisted||{};if(p.settings){p.settings={...p.settings,fps:p.settings.fps===60?30:p.settings.fps,crossfadeSec:0,normalizeLufs:false,codec:'h265'};}return p;}"
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise SystemExit('8.35 store repair: persisted migration marker missing')
p.write_text(s,encoding='utf-8')
print('ENDLUME: 8.35 persisted settings migration typing hardened')
