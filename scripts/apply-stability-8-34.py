from pathlib import Path

def must(cond, msg):
    if not cond:
        raise SystemExit(f"8.34: {msg}")

# Live Preview / project scan hardening.
# In addition to ignoring ._* filenames, block AppleDouble by file magic.
p = Path("src-tauri/src/scan.rs")
s = p.read_text(encoding="utf-8")
s = s.replace(
    "use std::path::{Path,PathBuf};",
    "use std::{fs::File,io::Read,path::{Path,PathBuf}};",
    1,
)
if "fn has_appledouble_magic(" not in s:
    marker = 'fn is_macos_sidecar(p:&Path)->bool{let n=p.file_name().and_then(|x|x.to_str()).unwrap_or("");n==".DS_Store"||n.starts_with("._")||n.starts_with(".Spotlight-")||n.starts_with(".Trashes")||n.starts_with(\'.\')}\n'
    must(marker in s, "scan sidecar marker missing")
    helper = '''fn has_appledouble_magic(p:&Path)->bool{let mut b=[0u8;4];File::open(p).and_then(|mut f|f.read_exact(&mut b)).is_ok()&&matches!(u32::from_be_bytes(b),0x00051607|0x00051600)}
fn rejected_macos_input(p:&Path)->bool{is_macos_sidecar(p)||has_appledouble_magic(p)}
'''
    s = s.replace(marker, marker + helper, 1)
s = s.replace(
    "if !p.is_file()||is_macos_sidecar(&p){continue}",
    "if !p.is_file()||rejected_macos_input(&p){continue}",
)
must("rejected_macos_input(&p)" in s and "0x00051607" in s, "scan magic guard missing")
p.write_text(s, encoding="utf-8")

p = Path("src-tauri/src/live_preview.rs")
s = p.read_text(encoding="utf-8")
s = s.replace(
    "use std::{fs,path::{Path,PathBuf},time::UNIX_EPOCH};",
    "use std::{fs,io::Read,path::{Path,PathBuf},time::UNIX_EPOCH};",
    1,
)
if "fn has_appledouble_magic(" not in s:
    marker = 'fn is_macos_sidecar(p:&Path)->bool{let n=p.file_name().and_then(|x|x.to_str()).unwrap_or("");n==".DS_Store"||n.starts_with("._")||n.starts_with(".Spotlight-")||n.starts_with(".Trashes")||n.starts_with(\'.\')}\n'
    must(marker in s, "live preview sidecar marker missing")
    helper = '''fn has_appledouble_magic(p:&Path)->bool{let mut b=[0u8;4];fs::File::open(p).and_then(|mut f|f.read_exact(&mut b)).is_ok()&&matches!(u32::from_be_bytes(b),0x00051607|0x00051600)}
fn rejected_macos_input(p:&Path)->bool{is_macos_sidecar(p)||has_appledouble_magic(p)}
'''
    s = s.replace(marker, marker + helper, 1)

s = s.replace('join("live-preview-v5")', 'join("live-preview-v6")')
s = s.replace(
    ".filter(|p|p.is_file()&&!is_macos_sidecar(p)&&is_media(p)&&ready_file(p))",
    ".filter(|p|p.is_file()&&!rejected_macos_input(p)&&is_media(p)&&ready_file(p))",
)
old = 'if is_macos_sidecar(&overlay){return Err("Выбран служебный файл macOS (._*), а не настоящий Effects/Subscribe файл".into())}'
new = 'if rejected_macos_input(&overlay){return Err("ENDLUME заблокировала служебный AppleDouble/resource-fork файл macOS. Выберите настоящий Effects/Subscribe файл.".into())}'
s = s.replace(old, new)
must("live-preview-v6" in s, "preview cache version not bumped")
must("!rejected_macos_input(p)&&is_media(p)" in s, "first_media magic guard missing")
must("rejected_macos_input(&overlay)" in s, "overlay magic guard missing")
p.write_text(s, encoding="utf-8")

# Reject poisoned/renamed AppleDouble payloads at library import time.
p = Path("src-tauri/src/assets.rs")
s = p.read_text(encoding="utf-8")
s = s.replace(
    "use std::{fs,path::{Path,PathBuf},time::UNIX_EPOCH};",
    "use std::{fs,io::Read,path::{Path,PathBuf},time::UNIX_EPOCH};",
    1,
)
if "fn has_appledouble_magic(" not in s:
    marker = '''fn safe_kind(kind:&str)->&'static str{
  match kind{"subscribe"=>"subscribe","ambient"=>"ambient",_=>"effects"}
}
'''
    must(marker in s, "assets safe_kind marker missing")
    helper = '''
fn has_appledouble_magic(path:&Path)->bool{
  let mut b=[0u8;4];
  fs::File::open(path).and_then(|mut f|f.read_exact(&mut b)).is_ok()&&matches!(u32::from_be_bytes(b),0x00051607|0x00051600)
}
fn is_macos_sidecar(path:&Path)->bool{
  let n=path.file_name().and_then(|x|x.to_str()).unwrap_or("");
  n==".DS_Store"||n.starts_with("._")||n.starts_with(".Spotlight-")||n.starts_with(".Trashes")||n.starts_with('.')
}
'''
    s = s.replace(marker, marker + helper, 1)

needle = 'if !src.is_file(){return Err(format!("Выбранный файл не найден: {}",src.display()))}\n'
if 'ENDLUME не импортирует служебные AppleDouble/resource-fork' not in s:
    must(needle in s, "assets source validation marker missing")
    s = s.replace(
        needle,
        needle + '  if is_macos_sidecar(&src)||has_appledouble_magic(&src){return Err("ENDLUME не импортирует служебные AppleDouble/resource-fork файлы macOS. Выберите настоящий медиафайл.".into())}\n',
        1,
    )
must("has_appledouble_magic(&src)" in s, "managed library magic guard missing")
p.write_text(s, encoding="utf-8")

# Permanent product invariants.
project = Path("src/pages/ProjectPage.tsx").read_text(encoding="utf-8")
must("Шум 1" not in project and "Шум 2" not in project, "Noise 1/2 UI returned")

render = Path("src-tauri/src/render.rs").read_text(encoding="utf-8")
must("hybrid_video_kbps" in render, "smart 2h size budget missing")
must("choose_hybrid_encoder(app,attempt).await" in render, "hardware-first render path missing")
must('"hevc_videotoolbox"' in render, "Apple VideoToolbox path missing")
must('"audio-original-clean.mp3"' in render, "original MP3 bitstream-copy path missing")

print("ENDLUME alpha.8.34 stability hardening applied")
