#!/usr/bin/env python3
from pathlib import Path
import sys

# Reuse the proven 10.0.11 physical acceptance verbatim, but teach its fixture
# resolver the current persisted preset name. Product/render code is untouched.
base=Path(__file__).with_name('qa-endlume-1011-preview-subscribe-final.py')
source=base.read_text(encoding='utf-8')
old='"эквалайзер круглый" in str(x.get("name","")).lower()'
new='("эквалайзер круглый" in str(x.get("name","")).lower() or "qa round equalizer" in str(x.get("name","")).lower())'
count=source.count(old)
if count!=2:
    raise SystemExit(f'Unexpected Round Equalizer resolver shape: {count}')
source=source.replace(old,new)
code=compile(source,str(base),'exec')
globals_dict={'__name__':'__main__','__file__':str(base),'__package__':None}
exec(code,globals_dict,globals_dict)
