#!/usr/bin/env python3
from pathlib import Path
import json,re
VERSION='1.0.0-alpha.8.52'
root=Path('.')

p=root/'package.json'
d=json.loads(p.read_text(encoding='utf-8'));d['version']=VERSION;p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

p=root/'src-tauri'/'tauri.conf.json'
d=json.loads(p.read_text(encoding='utf-8'));d['version']=VERSION;d['productName']='ENDLUME STUDIO PEISOV';
if d.get('app',{}).get('windows'): d['app']['windows'][0]['title']='ENDLUME STUDIO PEISOV'
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

p=root/'src-tauri'/'Cargo.toml';s=p.read_text(encoding='utf-8')
m=re.search(r'(?ms)^\[package\]\s*.*?^version\s*=\s*"[^"]+"',s)
if not m: raise SystemExit('Cargo [package] version not found')
block=m.group(0);block=re.sub(r'(?m)^version\s*=\s*"[^"]+"',f'version = "{VERSION}"',block,1);s=s[:m.start()]+block+s[m.end():];p.write_text(s,encoding='utf-8')

lock=root/'package-lock.json'
if lock.is_file():
    d=json.loads(lock.read_text(encoding='utf-8'));d['version']=VERSION
    if isinstance(d.get('packages'),dict) and isinstance(d['packages'].get(''),dict): d['packages']['']['version']=VERSION
    lock.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

print('ENDLUME_VERSION='+VERSION)
