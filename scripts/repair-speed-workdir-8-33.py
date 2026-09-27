from pathlib import Path
import py_compile

# Compatibility marker for local installers. The generated Rust helper is
# output.join(".ENDLUME-work") after this repair is applied.
FIX4_PREFLIGHT_OUTPUT_MARKER = 'output.join(".ENDLUME-work")'

speed=Path('scripts/apply-speed-fidelity-8-33.py')
if not speed.is_file():
    raise SystemExit('8.33 workdir repair: apply-speed-fidelity-8-33.py missing')

st=speed.read_text(encoding='utf-8')
marker='8.25 render_work_dir helper could not be replaced'
new_work="""desired_work_helper='''fn render_work_dir(output:&Path,id:&str,attempt:u32)->Result<PathBuf,String>{
  let root=output.join(\".ENDLUME-work\");
  std::fs::create_dir_all(&root).map_err(|e|format!(\"Не удалось создать рабочую папку рендера на выбранном диске: {e}\"))?;
  let dir=root.join(format!(\"{}-{}\",safe_name(id),attempt));
  let _=std::fs::remove_dir_all(&dir);
  std::fs::create_dir_all(&dir).map_err(|e|format!(\"Не удалось создать рабочую папку проекта на выбранном диске: {e}\"))?;
  Ok(dir)
}

'''
if 'fn render_work_dir(app:&AppHandle,job_id:&str,attempt:u32)' in r:
    r,n=re.subn(r'fn render_work_dir\\(app:&AppHandle,job_id:&str,attempt:u32\\)->Result<PathBuf,String>\\{.*?\\n\\}\\n',desired_work_helper,r,count=1,flags=re.S)
    must(n==1,'8.25 render_work_dir helper could not be replaced')
elif 'fn render_work_dir(output:&Path,id:&str,attempt:u32)' not in r:
    marker='fn fmt_ts(sec:f64)->String{'
    must(marker in r,'render work helper marker missing')
    r=r.replace(marker,desired_work_helper+marker,1)

r=r.replace('let work=render_work_dir(app,&job.project.id,attempt)?;',
            'let work=render_work_dir(&out_dir,&job.project.id,attempt)?;',1)
r,_=re.subn(r'let work=std::env::temp_dir\\(\\)\\.join\\(format!\\(\"endlume-\\{\\}-\\{\\}\",job\\.project\\.id,attempt\\)\\);',
             'let work=render_work_dir(&out_dir,&job.project.id,attempt)?;',r,count=1)
must('let work=render_work_dir(&out_dir,&job.project.id,attempt)?;' in r,'render workspace was not moved to output drive')
must('output.join(\".ENDLUME-work\")' in r,'output-drive render helper missing')
"""

if marker not in st:
    block_start=st.find("if 'fn render_work_dir(' not in r:")
    end_marker="must(n==1 or 'let work=render_work_dir(&out_dir,&job.project.id,attempt)?;' in r,'render workspace was not moved to output drive')"
    block_end=st.find(end_marker,block_start) if block_start>=0 else -1
    if block_start<0 or block_end<0:
        raise SystemExit('8.33 workdir repair: historical workdir block not found')
    block_end+=len(end_marker)
    st=st[:block_start]+new_work+st[block_end:]
    speed.write_text(st,encoding='utf-8')

py_compile.compile(str(speed),doraise=True)

render=Path('src-tauri/src/render.rs')
if render.is_file():
    r=render.read_text(encoding='utf-8')
    if 'fn render_work_dir(app:&AppHandle,job_id:&str,attempt:u32)' not in r and 'fn render_work_dir(output:&Path,id:&str,attempt:u32)' not in r:
        raise SystemExit('8.33 workdir repair: source render_work_dir helper missing before migration')

print('ENDLUME: 8.33 output-drive workspace migration normalized against 8.25 helper')
