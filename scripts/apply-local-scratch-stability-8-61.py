#!/usr/bin/env python3
from pathlib import Path
import json,re

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'src-tauri/src/render.rs'
s=R.read_text(encoding='utf-8')

def once(text,old,new,label):
    n=text.count(old)
    if n!=1:
        raise SystemExit(f'8.61 migration: {label}: expected 1 anchor, found {n}')
    return text.replace(old,new,1)

# 8.61 fixes only sustained one-image render performance when the final output
# is on an external disk. 8.60 put .ENDLUME-work beside the final output, so
# master/audio/manifest temporary writes all hit the external TOSHIBA volume.
# Keep temporary render I/O on the Mac internal cache and write the final MOV
# to the selected output volume exactly once.
for marker in [
    'resolved_job.settings.width=1920;',
    'resolved_job.settings.height=1080;',
    'resolved_job.settings.fps=60;',
    '"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"',
    'const STRICT_857_MAX_GOP_FRAMES:u32=1800;',
]:
    if marker not in s:
        raise SystemExit('8.61 migration: missing invariant '+marker)

old='''fn render_work_dir(output:&Path,id:&str,attempt:u32)->Result<PathBuf,String>{
  let root=output.join(".ENDLUME-work");
  std::fs::create_dir_all(&root).map_err(|e|format!("Не удалось создать рабочую папку рендера на выбранном диске: {e}"))?;
  let dir=root.join(format!("{}-{}",safe_name(id),attempt));
  let _=std::fs::remove_dir_all(&dir);
  std::fs::create_dir_all(&dir).map_err(|e|format!("Не удалось создать рабочую папку проекта на выбранном диске: {e}"))?;
  Ok(dir)
}
'''
new='''fn render_work_dir(app:&AppHandle,id:&str,attempt:u32)->Result<PathBuf,String>{
  let base=app.path().app_cache_dir().unwrap_or_else(|_|std::env::temp_dir().join("studio.endlume.desktop"));
  let root=base.join("render-work");
  std::fs::create_dir_all(&root).map_err(|e|format!("Не удалось создать локальную рабочую папку ENDLUME: {e}"))?;
  let dir=root.join(format!("{}-{}",safe_name(id),attempt));
  let _=std::fs::remove_dir_all(&dir);
  std::fs::create_dir_all(&dir).map_err(|e|format!("Не удалось создать локальную рабочую папку проекта: {e}"))?;
  Ok(dir)
}

fn finalize_local_output(src:&Path,out:&Path)->Result<(),String>{
  let parent=out.parent().ok_or_else(||"8.61: у итогового файла нет родительской папки".to_string())?;
  std::fs::create_dir_all(parent).map_err(|e|format!("8.61: не удалось создать папку результата: {e}"))?;
  let part=parent.join(format!(".{}.endlume-part",out.file_name().and_then(|x|x.to_str()).unwrap_or("render.mov")));
  let _=std::fs::remove_file(&part);
  match std::fs::rename(src,&part){
    Ok(_)=>{},
    Err(_)=>{
      let mut input=std::fs::File::open(src).map_err(|e|format!("8.61: не удалось открыть локальный результат: {e}"))?;
      let mut output=std::fs::File::create(&part).map_err(|e|format!("8.61: не удалось создать временный итоговый файл: {e}"))?;
      std::io::copy(&mut input,&mut output).map_err(|e|format!("8.61: не удалось перенести итоговое видео на выбранный диск: {e}"))?;
      output.sync_all().map_err(|e|format!("8.61: не удалось синхронизировать итоговое видео: {e}"))?;
      drop(output);
      let _=std::fs::remove_file(src);
    }
  }
  let _=std::fs::remove_file(out);
  std::fs::rename(&part,out).map_err(|e|format!("8.61: не удалось атомарно завершить итоговый MOV: {e}"))?;
  Ok(())
}
'''
s=once(s,old,new,'internal render scratch')
s=once(s,'let work=render_work_dir(&out_dir,&job.project.id,attempt)?;','let work=render_work_dir(app,&job.project.id,attempt)?;','render work call')

# These anchors exist after apply-render-speed-stability-8-60.py and are the two
# strict one-image zero-copy finalization paths (Subscribe OFF / periodic ON).
s=once(s,'crate::mp4_manifest::expand_video_prefix_cycle(&seed,&seed,0,master_frames,total_frames)?;std::fs::rename(&seed,out).map_err(|e|format!("Strict 8.56: не удалось завершить zero-copy MOV: {e}"))?;','crate::mp4_manifest::expand_video_prefix_cycle(&seed,&seed,0,master_frames,total_frames)?;finalize_local_output(&seed,out)?;','strict cross-volume finalize')
s=once(s,'crate::mp4_manifest::expand_video_prefix_cycle(&seed,&seed,plan.anchor_frames,plan.repeat_frames,total_frames)?;std::fs::rename(&seed,out).map_err(|e|format!("8.52: не удалось завершить zero-copy MOV: {e}"))?;','crate::mp4_manifest::expand_video_prefix_cycle(&seed,&seed,plan.anchor_frames,plan.repeat_frames,total_frames)?;finalize_local_output(&seed,out)?;','periodic cross-volume finalize')
R.write_text(s,encoding='utf-8')

# Version identity is bumped only after all previous migrations have been applied.
for rel in ['package.json','src-tauri/tauri.conf.json']:
    p=ROOT/rel; d=json.loads(p.read_text());
    if d.get('version')!='1.0.0-alpha.8.60': raise SystemExit(f'8.61 migration: {rel} expected 8.60')
    d['version']='1.0.0-alpha.8.61'; p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'src-tauri/Cargo.toml'; txt=p.read_text(); txt,n=re.subn(r'(?m)^version\s*=\s*"1\.0\.0-alpha\.8\.60"$', 'version = "1.0.0-alpha.8.61"',txt,count=1)
if n!=1: raise SystemExit('8.61 migration: Cargo 8.60 version anchor missing')
p.write_text(txt)
p=ROOT/'package-lock.json'
if p.exists():
    d=json.loads(p.read_text())
    d['version']='1.0.0-alpha.8.61'
    if isinstance(d.get('packages'),dict) and '' in d['packages']: d['packages']['']['version']='1.0.0-alpha.8.61'
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
P=ROOT/'src/pages/SettingsPage.tsx'; ui=P.read_text()
if '1.0.0-alpha.8.60' not in ui: raise SystemExit('8.61 migration: Settings 8.60 anchor missing')
P.write_text(ui.replace('1.0.0-alpha.8.60','1.0.0-alpha.8.61'))
H=ROOT/'src/components/ReleaseHistory.tsx'; h=H.read_text()
old="version:'1.0.0-alpha.8.60',date:'07.09.2026',current:true"
if old not in h: raise SystemExit('8.61 migration: ReleaseHistory 8.60 current anchor missing')
h=h.replace(old,"version:'1.0.0-alpha.8.60',date:'07.09.2026',current:false",1)
anchor='const releases:Release[]=[\n'
entry="""const releases:Release[]=[
  {version:'1.0.0-alpha.8.61',date:'07.09.2026',current:true,title:'External Disk Render Stability',items:[
    'Рабочие master/audio/manifest файлы one-image рендера перенесены с внешнего output-диска в локальный cache Mac.',
    'На TOSHIBA/другой выбранный диск итоговый MOV записывается один раз после завершения локального zero-copy manifest.',
    'Убрано накопительное замедление проектов из-за многократной тяжёлой записи временных файлов на внешний диск.',
    'Сохранены HEVC VideoToolbox q:v100, GOP1800, 1920×1080 CFR60, original MP3 packet-copy, whole-song, Effects/Subscribe, 500–700 МБ и VYRON contracts.'
  ]},
"""
if anchor not in h: raise SystemExit('8.61 migration: ReleaseHistory list anchor missing')
H.write_text(h.replace(anchor,entry,1))

print('PASS: ENDLUME 8.61 internal scratch + single external final write + version contracts applied')
