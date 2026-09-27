from pathlib import Path
import py_compile

p=Path('scripts/apply-hybrid-fidelity-8-28.py')
if not p.exists():
    raise SystemExit('Hybrid Fidelity patcher file missing')
text=p.read_text(encoding='utf-8')

# Quality/size budget used by 8.29+.
text=text.replace('"-crf","14"','"-crf","22"')
text=text.replace('CRF14','CRF22')
text=text.replace('crf 14','crf 22')

# Replace only the brittle failure branches. If a branch was already repaired,
# this script is a no-op. This makes repeated local installs deterministic.
replacements={
"elif new not in text:raise SystemExit('8.28: Subscribe encoder marker missing')": """elif new not in text:
    fn_pat=r'async fn render_sub_segment\\(.*?\\n}\\n\\nasync fn assemble_visual'
    m=re.search(fn_pat,text,flags=re.S)
    if not m: raise SystemExit('Hybrid Fidelity: render_sub_segment function missing')
    fn=m.group(0)
    desired='if smart_repeat_project(job){args.extend(hybrid_fidelity_args(&job.settings));}else{args.extend(encoder_args(encoder,&job.settings,false));}'
    if desired not in fn:
        candidates=[
            r'args\\.extend\\(encoder_args\\(encoder,&job\\.settings,false\\)\\);',
            r'args\\.extend\\(if smart_repeat_project\\(job\\)\\{fidelity_video_args\\(encoder,&job\\.settings\\)\\}else\\{encoder_args\\(encoder,&job\\.settings,false\\)\\}\\);'
        ]
        fn2=fn
        for pat in candidates:
            fn2,n=re.subn(pat,desired,fn2,count=1)
            if n: break
        else: raise SystemExit('Hybrid Fidelity: Subscribe encoder insertion point missing')
        text=text[:m.start()]+fn2+text[m.end():]""",
"elif new_out not in text:raise SystemExit('8.28: render output marker missing')": """elif new_out not in text:
    simple='let out=unique_output(&out_dir,&job.project.name);'
    repl='let out=if smart_repeat_project(job){unique_output_ext(&out_dir,&job.project.name,\\\"mov\\\")}else{unique_output(&out_dir,&job.project.name)};'
    if simple not in text: raise SystemExit('Hybrid Fidelity: render output assignment missing')
    text=text.replace(simple,repl,1)""",
"elif new_sel not in text:raise SystemExit('8.28: fidelity encoder selector marker missing')": """elif new_sel not in text:
    if 'choose_fidelity_encoder(app,attempt).await' not in text: raise SystemExit('Hybrid Fidelity: fidelity selector missing')
    text=text.replace('choose_fidelity_encoder(app,attempt).await','\\\"libx265\\\".to_string()',1)""",
"elif new_mux not in text:raise SystemExit('8.28: final mux marker missing')": """elif new_mux not in text:
    needle='\\\"-c:v\\\",\\\"copy\\\",\\\"-c:a\\\",\\\"copy\\\"'
    if needle not in text: raise SystemExit('Hybrid Fidelity: final copy/copy mux pair missing')
    text=text.replace(needle,needle+',\\\"-movflags\\\",\\\"+faststart\\\"',1)""",
}
for old,new in replacements.items():
    if old in text:
        text=text.replace(old,new,1)

p.write_text(text,encoding='utf-8')
py_compile.compile(str(p),doraise=True)

# The release branch can already contain the modern private-local updater bridge
# while the historical 8.32 migration is replayed by the local builder. The old
# migration expects checkUpdate to be the final object property and otherwise
# fails with "8.32: checkUpdate end missing". Normalize only that bridge to a
# tiny legacy-compatible placeholder; apply-queue-updater-8-32.py then restores
# the exact modern checkUpdate + updateStatus implementation in the same build.
bridge=Path('src/tauri.ts')
if bridge.is_file():
    b=bridge.read_text(encoding='utf-8')
    modern=("local_update_check" in b and "updateStatus:()=>invoke<" in b and "  checkUpdate:async()=>{" in b)
    if modern:
        start=b.find('  checkUpdate:async()=>{')
        obj_end=b.rfind('\n};')
        if start<0 or obj_end<start:
            raise SystemExit('ENDLUME: modern updater bridge normalization failed')
        placeholder="""  checkUpdate:async()=>{
    return {none:true,current:'1.0.0-alpha.8.31',channel:'migration-placeholder'};
  }"""
        b=b[:start]+placeholder+b[obj_end:]
        if '\n  }\n};' not in b[start:]:
            raise SystemExit('ENDLUME: legacy updater end marker was not normalized')
        bridge.write_text(b,encoding='utf-8')
        print('ENDLUME: modern updater bridge normalized for deterministic 8.32 migration')

q=Path('scripts/apply-queue-updater-8-32.py')
if q.is_file():
    py_compile.compile(str(q),doraise=True)

print('ENDLUME: Hybrid Fidelity patcher normalized, CRF22 budget active, Python syntax OK')
