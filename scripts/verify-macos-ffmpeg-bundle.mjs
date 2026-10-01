import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const scriptDir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(scriptDir,'..');
if(process.platform!=='darwin')process.exit(0);
const target=process.env.ENDLUME_TAURI_TARGET||(process.arch==='arm64'?'aarch64-apple-darwin':'x86_64-apple-darwin');
const expectedArch=target.startsWith('aarch64')?'arm64':'x86_64';

function run(cmd,args,opts={}){return execFileSync(cmd,args,{encoding:'utf8',stdio:['ignore','pipe','pipe'],...opts})}
function deps(file){return run('/usr/bin/otool',['-L',file]).split('\n').slice(1).map(x=>x.trim().split(/\s+/)[0]).filter(Boolean)}
function rpaths(file){const lines=run('/usr/bin/otool',['-l',file]).split('\n'),out=[];for(let i=0;i<lines.length;i++)if(lines[i].trim()==='cmd LC_RPATH')for(let j=i+1;j<Math.min(lines.length,i+6);j++){const m=lines[j].trim().match(/^path\s+(.+?)\s+\(offset\s+\d+\)$/);if(m){out.push(m[1]);break}}return out}
function isSystem(dep){return dep.startsWith('/System/Library/')||dep.startsWith('/usr/lib/')}
function forbidden(v){return v.startsWith('/opt/homebrew/')||v.startsWith('/usr/local/')||v.includes('/Cellar/')||v.startsWith('/opt/local/')||v.startsWith('/Users/')||v.startsWith('/private/tmp/')}
function walk(dir,depth=0){if(depth>7||!fs.existsSync(dir))return[];const out=[];for(const e of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory()){if(e.name.endsWith('.app'))out.push(p);else out.push(...walk(p,depth+1))}}return out}
function roots(){const out=[];if(process.env.CARGO_TARGET_DIR)out.push(path.resolve(process.env.CARGO_TARGET_DIR));out.push(path.join(root,'src-tauri','target'));return[...new Set(out.filter(fs.existsSync))]}

const apps=roots().flatMap(walk).filter(p=>path.basename(p).includes('ENDLUME'));
if(!apps.length)throw new Error(`No ENDLUME .app found under: ${roots().join(', ')}`);
apps.sort((a,b)=>fs.statSync(b).mtimeMs-fs.statSync(a).mtimeMs);
const app=apps[0],macos=path.join(app,'Contents','MacOS'),frameworksDir=path.join(app,'Contents','Frameworks');
const ffmpeg=path.join(macos,'ffmpeg'),ffprobe=path.join(macos,'ffprobe');
for(const p of[ffmpeg,ffprobe])if(!fs.existsSync(p))throw new Error(`Bundled sidecar missing: ${p}`);
const dylibs=fs.existsSync(frameworksDir)?fs.readdirSync(frameworksDir).filter(n=>n.endsWith('.dylib')).map(n=>path.join(frameworksDir,n)):[];
if(!dylibs.length)throw new Error('No bundled FFmpeg dylibs found in Contents/Frameworks');

for(const file of[ffmpeg,ffprobe,...dylibs]){
  const info=run('/usr/bin/file',[file]);if(!info.includes(expectedArch))throw new Error(`Architecture mismatch: ${info.trim()}`);
  for(const dep of deps(file)){
    if(isSystem(dep))continue;
    if(forbidden(dep))throw new Error(`Forbidden production dependency in ${file}: ${dep}`);
    if(dep.startsWith('@executable_path/../Frameworks/')){if(!fs.existsSync(path.join(frameworksDir,path.basename(dep))))throw new Error(`Dependency missing inside app: ${dep}`)}
    else throw new Error(`Unexpected non-system dependency in ${file}: ${dep}`);
  }
  for(const rp of rpaths(file))if(forbidden(rp))throw new Error(`Forbidden production LC_RPATH in ${file}: ${rp}`);
}

const cleanEnv={...process.env,PATH:'/usr/bin:/bin:/usr/sbin:/sbin'};delete cleanEnv.DYLD_LIBRARY_PATH;delete cleanEnv.DYLD_FALLBACK_LIBRARY_PATH;delete cleanEnv.DYLD_FRAMEWORK_PATH;
for(const[bin,args]of[[ffmpeg,['-version']],[ffprobe,['-version']]]){const p=spawnSync(bin,args,{env:cleanEnv,encoding:'utf8'});if(p.status!==0)throw new Error(`Bundled ${path.basename(bin)} failed without Homebrew env: ${p.stderr||p.stdout}`)}

const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'endlume-ffmpeg-smoke-'));
try{
  const out=path.join(tmp,'preview-smoke.mp4'),base=['-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=black:s=320x180:r=30','-t','0.35','-an'];
  let enc=spawnSync(ffmpeg,[...base,'-c:v','h264_videotoolbox','-pix_fmt','yuv420p','-y',out],{env:cleanEnv,encoding:'utf8'});
  if(enc.status!==0)enc=spawnSync(ffmpeg,[...base,'-c:v','libx264','-pix_fmt','yuv420p','-y',out],{env:cleanEnv,encoding:'utf8'});
  if(enc.status!==0||!fs.existsSync(out))throw new Error(`Bundled FFmpeg preview smoke failed: ${enc.stderr||enc.stdout}`);
  const probe=spawnSync(ffprobe,['-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height:format=duration','-of','json',out],{env:cleanEnv,encoding:'utf8'});
  if(probe.status!==0)throw new Error(`Bundled FFprobe preview smoke failed: ${probe.stderr||probe.stdout}`);
  const data=JSON.parse(probe.stdout);if(!data.streams?.[0]||Number(data.streams[0].width)!==320||Number(data.streams[0].height)!==180||Number(data.format?.duration)<=0)throw new Error(`Invalid preview smoke probe: ${probe.stdout}`);
}finally{fs.rmSync(tmp,{recursive:true,force:true})}

const sign=spawnSync('/usr/bin/codesign',['--verify','--deep','--strict','--verbose=2',app],{encoding:'utf8'});
if(sign.status!==0)throw new Error(`codesign verification failed: ${sign.stderr||sign.stdout}`);
if(process.env.ENDLUME_REQUIRE_GATEKEEPER==='1'){const gate=spawnSync('/usr/sbin/spctl',['-a','-vv',app],{encoding:'utf8'});if(gate.status!==0)throw new Error(`Gatekeeper verification failed: ${gate.stderr||gate.stdout}`)}

console.log(JSON.stringify({kind:'ENDLUME_MACOS_FFMPEG_RUNTIME_PASS',app,target,frameworks:dylibs.length,ffmpeg:true,ffprobe:true,codesign:true}));
