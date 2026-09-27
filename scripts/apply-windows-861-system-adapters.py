#!/usr/bin/env python3
from pathlib import Path
p=Path('src-tauri/src/system.rs')
s=p.read_text(encoding='utf-8')
marker='const ENDLUME_CANONICAL_PATH:&str="/Applications/ENDLUME Studio.app";\n'
ffi='''\n#[cfg(target_os="windows")]\n#[repr(C)]\nstruct SystemPowerStatus{\n  ac_line_status:u8,battery_flag:u8,battery_life_percent:u8,reserved1:u8,battery_life_time:u32,battery_full_life_time:u32,\n}\n#[cfg(target_os="windows")]\nextern "system"{fn GetSystemPowerStatus(status:*mut SystemPowerStatus)->i32;}\n#[cfg(target_os="windows")]\nfn windows_power_status()->Value{\n  let mut status=SystemPowerStatus{ac_line_status:255,battery_flag:255,battery_life_percent:255,reserved1:0,battery_life_time:u32::MAX,battery_full_life_time:u32::MAX};\n  let ok=unsafe{GetSystemPowerStatus(&mut status as *mut SystemPowerStatus)}!=0;\n  if !ok{return json!({"supported":false,"onBattery":false,"percent":null});}\n  let percent=if status.battery_life_percent==255{None}else{Some(status.battery_life_percent.min(100) as u32)};\n  json!({"supported":true,"onBattery":status.ac_line_status==0,"percent":percent})\n}\n#[cfg(target_os="windows")]\nfn hidden_windows_command(program:&str)->std::process::Command{\n  use std::os::windows::process::CommandExt;\n  let mut command=std::process::Command::new(program);\n  command.creation_flags(0x0800_0000);\n  command\n}\n'''
if 'fn windows_power_status()' not in s:
    s=s.replace(marker,marker+ffi)
old='''  #[cfg(not(target_os="macos"))]\n  { json!({"supported":false,"onBattery":false,"percent":null}) }'''
new='''  #[cfg(target_os="windows")]\n  { return windows_power_status(); }\n  #[cfg(all(not(target_os="macos"),not(target_os="windows")))]\n  { json!({"supported":false,"onBattery":false,"percent":null}) }'''
if old in s:s=s.replace(old,new)
s=s.replace('std::process::Command::new("explorer.exe").arg(&path).spawn()','hidden_windows_command("explorer.exe").arg(&path).spawn()')
s=s.replace('std::process::Command::new("explorer.exe").arg(format!("/select,{path}")).spawn()','hidden_windows_command("explorer.exe").arg(format!("/select,{path}")).spawn()')
p.write_text(s,encoding='utf-8')
print('ENDLUME_WINDOWS_SYSTEM_ADAPTERS_APPLIED')
