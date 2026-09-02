from pathlib import Path

# 8.32 updater replay normalization.
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

# 8.39 was originally written against an older compositor where any `pad=` in
# render.rs implied black bars. The proven 8.25 compositor legitimately uses a
# transparent pad for fullscreen Effects while 8.38's BASE image filter uses
# cover+crop. Narrow both migration guards to base_filter only; the real 8.38
# FFmpeg square/portrait/ultrawide smoke still remains mandatory.
perf=Path('scripts/apply-performance-fidelity-8-39.py')
if perf.exists():
    t=perf.read_text(encoding='utf-8')
    old="must('pad={}:{}' not in r,'black-bar pad returned')"
    new="base_filter_line=next((line for line in r.splitlines() if line.startswith('fn base_filter(')),None)\nmust(base_filter_line is not None and 'pad=' not in base_filter_line,'black-bar pad returned')"
    if old in t:
        t=t.replace(old,new,1)
        perf.write_text(t,encoding='utf-8')
        print('8.39 replay repair: no-bars migration guard scoped to base_filter')
    elif 'base_filter_line=next((line for line in r.splitlines()' not in t:
        raise SystemExit('8.39 replay repair: performance no-bars guard missing')

validator=Path('scripts/validate-release-8-39.sh')
if validator.exists():
    t=validator.read_text(encoding='utf-8')
    old="! grep -Fq 'pad={}:{}' \"$RUST\" || fail 'black-bar pad returned'"
    new="BASE_FILTER_LINE=\"$(grep -F 'fn base_filter(' \"$RUST\" | head -1)\"\n[[ -n \"$BASE_FILTER_LINE\" && \"$BASE_FILTER_LINE\" != *'pad='* ]] || fail 'black-bar pad returned in base_filter'"
    if old in t:
        t=t.replace(old,new,1)
        validator.write_text(t,encoding='utf-8')
        print('8.39 replay repair: no-bars validation scoped to base_filter')
    elif "black-bar pad returned in base_filter" not in t:
        raise SystemExit('8.39 replay repair: validation no-bars guard missing')
