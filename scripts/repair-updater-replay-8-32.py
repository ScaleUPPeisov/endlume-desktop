from pathlib import Path

p=Path('src/tauri.ts')
s=p.read_text(encoding='utf-8')
start=s.find('  checkUpdate:async()=>{')
if start<0:
    raise SystemExit('8.32 replay repair: checkUpdate start missing')
status=s.find('\n  updateStatus:',start)
if status<0:
    print('8.32 replay repair: legacy shape already ready')
else:
    close=s.find('\n};',status)
    if close<0:
        raise SystemExit('8.32 replay repair: api object end missing')
    head=s[:status]
    if not head.endswith('\n  },'):
        raise SystemExit('8.32 replay repair: checkUpdate boundary unexpected')
    head=head[:-4]+'\n  }'
    s=head+s[close:]
    p.write_text(s,encoding='utf-8')
    print('8.32 replay repair: existing updateStatus normalized for deterministic migration replay')
