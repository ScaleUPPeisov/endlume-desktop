import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const scriptDir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(scriptDir,'..');
const args=process.argv.slice(2);
const command=args.find(a=>!a.startsWith('-'))||'';
const targetIndex=args.indexOf('--target');
const target=targetIndex>=0&&args[targetIndex+1]?args[targetIndex+1]:(process.arch==='arm64'?'aarch64-apple-darwin':'x86_64-apple-darwin');
const macTarget=/^(aarch64|x86_64)-apple-darwin$/.test(target);
const macConfig=path.join(root,'src-tauri','tauri.macos.conf.json');
const hadConfig=fs.existsSync(macConfig);
const oldConfig=hadConfig?fs.readFileSync(macConfig):null;
const env={...process.env,ENDLUME_TAURI_TARGET:target};
const tauriBin=path.join(root,'node_modules','.bin',process.platform==='win32'?'tauri.cmd':'tauri');
function exec(cmd,cmdArgs){const r=spawnSync(cmd,cmdArgs,{cwd:root,env,stdio:'inherit'});if(r.error)throw r.error;return r.status??1;}
let status=0;
try{
  if(process.platform==='darwin'&&macTarget&&(command==='build'||command==='dev')){
    status=exec(process.execPath,[path.join(scriptDir,'prepare-macos-ffmpeg-runtime.mjs')]);
  }
  if(status===0) status=exec(tauriBin,args);
  if(status===0&&process.platform==='darwin'&&macTarget&&command==='build') status=exec(process.execPath,[path.join(scriptDir,'verify-macos-ffmpeg-bundle.mjs')]);
} finally {
  if(process.platform==='darwin'&&macTarget&&(command==='build'||command==='dev')){
    if(hadConfig) fs.writeFileSync(macConfig,oldConfig); else fs.rmSync(macConfig,{force:true});
  }
}
process.exit(status);
