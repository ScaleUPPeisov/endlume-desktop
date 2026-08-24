from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{label}: expected source pattern not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


editors = Path("src/pages/Editors.tsx")
replace_once(
    editors,
    "d.scale=Math.max(.05,Math.min(2,distance/(Math.min(r.width,r.height)*.65)));}overlay.style.left=`${d.x*100}%`;overlay.style.top=`${d.y*100}%`;overlay.style.width=`${Math.max(8,d.scale*65)}%`;};",
    "d.scale=Math.max(.05,Math.min(1.5,distance/(r.width*.70710678)));}overlay.style.left=`${d.x*100}%`;overlay.style.top=`${d.y*100}%`;overlay.style.width=`${Math.max(5,d.scale*100)}%`;overlay.style.transform=`translate(${-d.x*100}%,${-d.y*100}%)`;};",
    "Preview resize geometry",
)
replace_once(
    editors,
    "const overlayStyle:React.CSSProperties=current.fullscreen?{left:'0%',top:'0%',width:'100%',height:'100%',transform:'none',touchAction:'none'}:{left:`${current.x*100}%`,top:`${current.y*100}%`,width:`${Math.max(8,current.scale*65)}%`,aspectRatio:'16 / 9',transform:'translate(-50%,-50%)',touchAction:'none',willChange:'left, top, width, transform',contain:'layout style paint'};",
    "const overlayStyle:React.CSSProperties=current.fullscreen?{left:'0%',top:'0%',width:'100%',height:'100%',transform:'none',touchAction:'none'}:{left:`${current.x*100}%`,top:`${current.y*100}%`,width:`${Math.max(5,current.scale*100)}%`,aspectRatio:'1 / 1',transform:`translate(${-current.x*100}%,${-current.y*100}%)`,touchAction:'none',willChange:'left, top, width, transform',contain:'layout style paint'};",
    "Preview source aspect geometry",
)

render = Path("src-tauri/src/render.rs")
replace_once(
    render,
    "use tauri::{AppHandle,Emitter};",
    "use tauri::{AppHandle,Emitter,Manager};",
    "Tauri path manager",
)
replace_once(
    render,
    "fn unique_output(dir:&Path,name:&str)->PathBuf{let safe=safe_name(name);let mut p=dir.join(format!(\"{} — Ready Videos.mp4\",safe));let mut n=2;while p.exists(){p=dir.join(format!(\"{} — Ready Videos_{}.mp4\",safe,n));n+=1}p}",
    "fn unique_output(dir:&Path,name:&str)->PathBuf{let safe=safe_name(name);let mut p=dir.join(format!(\"{} — Ready Videos.mp4\",safe));let mut n=2;while p.exists(){p=dir.join(format!(\"{} — Ready Videos_{}.mp4\",safe,n));n+=1}p}\nfn ensure_writable_dir(dir:&Path)->Result<(),String>{std::fs::create_dir_all(dir).map_err(|e|format!(\"Не удалось открыть папку результата '{}': {e}\",dir.display()))?;let probe=dir.join(format!(\".endlume-write-test-{}\",std::process::id()));std::fs::OpenOptions::new().create(true).write(true).truncate(true).open(&probe).and_then(|mut f|std::io::Write::write_all(&mut f,b\"ENDLUME\")).map_err(|e|format!(\"Нет прав на запись в '{}': {e}\",dir.display()))?;let _=std::fs::remove_file(probe);Ok(())}\nfn resolve_output_dir(app:&AppHandle,requested:&Path)->Result<(PathBuf,bool),String>{if ensure_writable_dir(requested).is_ok(){return Ok((requested.to_path_buf(),false))}let fallback=app.path().app_data_dir().map_err(|e|e.to_string())?.join(\"exports\");ensure_writable_dir(&fallback)?;Ok((fallback,true))}",
    "Writable output fallback",
)
replace_once(
    render,
    "let scale=if e.fullscreen{format!(\"scale={}:{}\",s.width,s.height)}else{format!(\"scale=iw*{}:ih*{}\",e.scale.max(0.01),e.scale.max(0.01))};let x=if e.fullscreen{\"0\".into()}else{format!(\"(W-w)*{}\",e.x.clamp(0.0,1.0))};let y=if e.fullscreen{\"0\".into()}else{format!(\"(H-h)*{}\",e.y.clamp(0.0,1.0))};",
    "let scale=if e.fullscreen{format!(\"scale={}:{}\",s.width,s.height)}else{let mut target_w=((s.width as f64)*e.scale.clamp(0.02,1.50)).round().max(2.0) as u32;if target_w%2!=0{target_w+=1;}format!(\"scale={}:-2\",target_w)};let x=if e.fullscreen{\"0\".into()}else{format!(\"(W-w)*{}\",e.x.clamp(0.0,1.0))};let y=if e.fullscreen{\"0\".into()}else{format!(\"(H-h)*{}\",e.y.clamp(0.0,1.0))};",
    "Aspect-safe render scale",
)
replace_once(
    render,
    "let (mut rx,child)=app.shell().sidecar(\"ffmpeg\").map_err(|e|e.to_string())?.args(args).spawn().map_err(|e|e.to_string())?;",
    "let cmd_preview=args.join(\" \" );let (mut rx,child)=app.shell().sidecar(\"ffmpeg\").map_err(|e|format!(\"{stage}: встроенный FFmpeg недоступен: {e}\"))?.args(args).spawn().map_err(|e|format!(\"{stage}: FFmpeg не запустился: {e}. Команда: {cmd_preview}\"))?;",
    "FFmpeg spawn diagnostics",
)
replace_once(
    render,
    "let started=chrono::Utc::now().timestamp_millis();let timer=Instant::now();let mut last_error=String::new();let out_dir=PathBuf::from(&job.settings.output_dir);std::fs::create_dir_all(&out_dir).map_err(|e|e.to_string())?;let out=unique_output(&out_dir,&job.project.name);",
    "let started=chrono::Utc::now().timestamp_millis();let timer=Instant::now();let mut last_error=String::new();let requested_out_dir=PathBuf::from(&job.settings.output_dir);let (out_dir,output_fallback)=resolve_output_dir(app,&requested_out_dir)?;if output_fallback{let _=app.emit(\"render-output-fallback\",json!({\"id\":job.project.id,\"requested\":requested_out_dir.to_string_lossy().into_owned(),\"actual\":out_dir.to_string_lossy().into_owned()}));}let out=unique_output(&out_dir,&job.project.name);",
    "Output permission recovery",
)
replace_once(
    render,
    "let work=std::env::temp_dir().join(format!(\"endlume-{}-{}\",job.project.id,attempt));let _=std::fs::remove_dir_all(&work);std::fs::create_dir_all(&work).map_err(|e|e.to_string())?;",
    "let work_root=app.path().app_cache_dir().map_err(|e|e.to_string())?.join(\"render-work\");std::fs::create_dir_all(&work_root).map_err(|e|format!(\"Не удалось создать рабочий кэш ENDLUME: {e}\"))?;let work=work_root.join(format!(\"{}-{}-{}\",safe_name(&job.project.id),attempt,started));if work.exists(){std::fs::remove_dir_all(&work).map_err(|e|format!(\"Не удалось очистить старый render-work '{}': {e}\",work.display()))?;}std::fs::create_dir_all(&work).map_err(|e|format!(\"Не удалось создать render-work '{}': {e}\",work.display()))?;",
    "Owned render workspace",
)

for ui_file in [Path("src/pages/SettingsPage.tsx"), Path("src/tauri.ts")]:
    if ui_file.exists():
        text = ui_file.read_text(encoding="utf-8")
        if "1.0.0-alpha.8.19" in text:
            ui_file.write_text(text.replace("1.0.0-alpha.8.19", "1.0.0-alpha.8.20"), encoding="utf-8")

print("ENDLUME alpha.8.20 aspect/permission hotfix applied")
