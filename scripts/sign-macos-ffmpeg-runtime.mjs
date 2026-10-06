import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const scriptDir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(scriptDir,'..');

if(process.platform!=='darwin'){
  console.log('[ENDLUME ffmpeg-runtime] non-macOS signing: skip');
  process.exit(0);
}

const target=process.env.ENDLUME_TAURI_TARGET||(process.arch==='arm64'?'aarch64-apple-darwin':'x86_64-apple-darwin');
if(!/^(aarch64|x86_64)-apple-darwin$/.test(target))throw new Error(`Unsupported macOS target for FFmpeg signing: ${target}`);

const tauriDir=path.join(root,'src-tauri');
const binariesDir=path.join(tauriDir,'binaries');
const frameworksDir=path.join(tauriDir,'.generated','macos-ffmpeg-frameworks');
const ffmpeg=path.join(binariesDir,`ffmpeg-${target}`);
const ffprobe=path.join(binariesDir,`ffprobe-${target}`);

function runCodesign(args,label){
  const result=spawnSync('/usr/bin/codesign',args,{encoding:'utf8'});
  if(result.status!==0){
    throw new Error(`${label} failed: ${result.stderr||result.stdout||`exit ${result.status}`}`);
  }
}

const dylibs=fs.existsSync(frameworksDir)
  ? fs.readdirSync(frameworksDir).filter(name=>name.endsWith('.dylib')).sort().map(name=>path.join(frameworksDir,name))
  : [];
const sidecars=[ffmpeg,ffprobe];
for(const file of [...dylibs,...sidecars]){
  if(!fs.existsSync(file))throw new Error(`macOS FFmpeg runtime file missing before signing: ${file}`);
}

// install_name_tool invalidates Mach-O code signatures. Apple Silicon refuses to
// execute a binary with a stale signature even when every dylib dependency is
// correctly bundled. Re-sign the fully patched closure only after all dependency
// and LC_ID/LC_RPATH rewrites are complete. A later Developer ID release signing
// pass may safely replace these ad-hoc signatures.
for(const file of dylibs){
  runCodesign(['--force','--sign','-',file],`Ad-hoc signing ${path.basename(file)}`);
}
for(const file of sidecars){
  runCodesign(['--force','--sign','-',file],`Ad-hoc signing ${path.basename(file)}`);
}
for(const file of [...dylibs,...sidecars]){
  runCodesign(['--verify','--strict','--verbose=2',file],`Code-sign verification ${path.basename(file)}`);
}

console.log(JSON.stringify({
  kind:'ENDLUME_MACOS_FFMPEG_RUNTIME_SIGNED',
  target,
  dylibs:dylibs.length,
  sidecars:sidecars.map(path.basename)
}));
