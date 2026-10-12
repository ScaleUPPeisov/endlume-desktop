#!/usr/bin/env python3
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'src-tauri'/'src'/'vyron_bridge.rs'
text=path.read_text(encoding='utf-8')

# Explicit VYRON outputDir is canonical and may intentionally live on /Volumes
# (or another Windows drive). Do not constrain it to batch/workspace ancestry.
# This finalizer is intentionally idempotent because the hotfix workflow may run
# again after the tested source was already committed to the candidate branch.
helper_pattern=r'''fn validate_output_scope\(output:&Path,batch_root:&Path\)->Result<\(\),String>\{.*?\n\}\n'''
if re.search(helper_pattern,text,flags=re.S):
    text,n=re.subn(helper_pattern,'',text,count=1,flags=re.S)
    if n!=1:
        raise SystemExit(f'vyron_bridge.rs: expected one validate_output_scope helper, got {n}')
needle='    validate_output_scope(&output,batch_root)?;\n'
if needle in text:
    if text.count(needle)!=1:
        raise SystemExit(f'vyron_bridge.rs: expected one explicit scope call, got {text.count(needle)}')
    text=text.replace(needle,'',1)
if 'fn validate_output_scope' in text or 'validate_output_scope(&output,batch_root)?' in text:
    raise SystemExit('vyron_bridge.rs: explicit outputDir scope restriction still present')
path.write_text(text,encoding='utf-8')

# 10.0.13 tests encoded the reconstruction regression itself: they expected
# Render/<channel> even when the fixture explicitly declared outputDir. Restore
# the contract in tests too. The channel-sanitization test deliberately removes
# outputDir so it still verifies the compatibility fallback.
tests=ROOT/'src-tauri'/'src'/'vyron_bridge_tests.rs'
t=tests.read_text(encoding='utf-8')
old='''  let expected=base.join("ВАЙРОН").join("Render").join("NEON").canonicalize().unwrap();\n  assert_eq!(PathBuf::from(&info.output_dir),expected);assert!(expected.is_dir());'''
new='''  let expected=manifest.parent().unwrap().join("output").canonicalize().unwrap();\n  assert_eq!(PathBuf::from(&info.output_dir),expected);assert!(expected.is_dir());'''
if old in t:
    if t.count(old)!=1: raise SystemExit('vyron_bridge_tests.rs: roundtrip expectation shape changed')
    t=t.replace(old,new,1)
elif new not in t:
    raise SystemExit('vyron_bridge_tests.rs: roundtrip expectation missing')

old='''  let mut v:serde_json::Value=serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();v["channelName"]=json!("Aegean/Afterglow: Live");fs::write(&manifest,serde_json::to_vec_pretty(&v).unwrap()).unwrap();'''
new='''  let mut v:serde_json::Value=serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();v["channelName"]=json!("Aegean/Afterglow: Live");v.as_object_mut().unwrap().remove("outputDir");fs::write(&manifest,serde_json::to_vec_pretty(&v).unwrap()).unwrap();'''
if old in t:
    if t.count(old)!=1: raise SystemExit('vyron_bridge_tests.rs: sanitization fixture shape changed')
    t=t.replace(old,new,1)
elif new not in t:
    raise SystemExit('vyron_bridge_tests.rs: sanitization fixture missing')

old='''  assert!(PathBuf::from(info.output_dir).ends_with(PathBuf::from("Render").join("NEON")));'''
new='''  assert_eq!(PathBuf::from(info.output_dir),manifest.parent().unwrap().join("output").canonicalize().unwrap());'''
if old in t:
    if t.count(old)!=1: raise SystemExit('vyron_bridge_tests.rs: selected-project expectation shape changed')
    t=t.replace(old,new,1)
elif new not in t:
    raise SystemExit('vyron_bridge_tests.rs: selected-project expectation missing')

insert='''\n#[test]\nfn vyron_explicit_output_dir_may_live_outside_workspace(){\n  let(base,manifest,_)=fixture();\n  let external=base.join("EXTERNAL_OUTPUT");\n  let mut v:serde_json::Value=serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();\n  v["outputDir"]=json!(external.to_string_lossy());\n  fs::write(&manifest,serde_json::to_vec_pretty(&v).unwrap()).unwrap();\n  let info=load_vyron_batch_manifest(manifest.to_string_lossy().into_owned(),None).unwrap();\n  assert_eq!(PathBuf::from(info.output_dir),external.canonicalize().unwrap());\n  assert!(external.is_dir());\n  fs::remove_dir_all(base).unwrap();\n}\n'''
if 'fn vyron_explicit_output_dir_may_live_outside_workspace' not in t:
    t += insert
tests.write_text(t,encoding='utf-8')

qa=ROOT/'scripts'/'qa-endlume-1014-hotfix.py'
qa_text=qa.read_text(encoding='utf-8')
anchor='assert "v.get(\\"outputDir\\")" in vyron and "validate_output_writable" in vyron\n'
extra='assert "validate_output_scope(&output,batch_root)?" not in vyron\nassert "vyron_explicit_output_dir_may_live_outside_workspace" in text("src-tauri/src/vyron_bridge_tests.rs")\n'
if extra not in qa_text:
    if anchor not in qa_text:
        raise SystemExit('qa-endlume-1014-hotfix.py: VYRON QA anchor missing')
    qa_text=qa_text.replace(anchor,anchor+extra,1)
qa.write_text(qa_text,encoding='utf-8')

print('PASS: explicit VYRON outputDir remains canonical, including destinations outside workspace')
