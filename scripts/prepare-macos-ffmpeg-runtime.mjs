import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const scriptDir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(scriptDir,'..');
const tauriDir=path.join(root,'src-tauri');
if(process.platform!=='darwin'){console.log('[ENDLUME ffmpeg-runtime] non-macOS: skip');process.exit(0)}

const target=process.env.ENDLUME_TAURI_TARGET||(process.arch==='arm64'?'aarch64-apple-darwin':'x86_64-apple-darwin');
if(!/^(aarch64|x86_64)-apple-darwin$/.test(target))throw new Error(`Unsupported macOS target: ${target}`);
const expectedArch=target.startsWith('aarch64')?'arm64':'x86_64';
const binariesDir=path.join(tauriDir,'binaries');
const generatedDir=path.join(tauriDir,'.generated');
const frameworksDir=path.join(generatedDir,'macos-ffmpeg-frameworks');
const macConfig=path.join(tauriDir,'tauri.macos.conf.json');
const manifestPath=path.join(generatedDir,'ffmpeg-runtime-manifest.json');
const ffmpeg=path.join(binariesDir,`ffmpeg-${target}`);
const ffprobe=path.join(binariesDir,`ffprobe-${target}`);
const executableOriginDir=binariesDir;

function run(cmd,args,opts={}){return execFileSync(cmd,args,{encoding:'utf8',stdio:['ignore','pipe','pipe'],...opts})}
function which(name){try{return run('/usr/bin/which',[name]).trim()}catch{return''}}
function ensureSidecar(dst,name){if(fs.existsSync(dst))return;const src=which(name);if(!src)throw new Error(`${name} sidecar missing and ${name} is not available on build machine`);fs.mkdirSync(path.dirname(dst),{recursive:true});fs.copyFileSync(fs.realpathSync(src),dst);fs.chmodSync(dst,0o755);console.log(`[ENDLUME ffmpeg-runtime] staged ${name} from ${src}`)}
function deps(file){return run('/usr/bin/otool',['-L',file]).split('\n').slice(1).map(x=>x.trim().split(/\s+/)[0]).filter(Boolean)}
function rpaths(file){const lines=run('/usr/bin/otool',['-l',file]).split('\n'),out=[];for(let i=0;i<lines.length;i++){if(lines[i].trim()==='cmd LC_RPATH'){for(let j=i+1;j<Math.min(lines.length,i+6);j++){const m=lines[j].trim().match(/^path\s+(.+?)\s+\(offset\s+\d+\)$/);if(m){out.push(m[1]);break}}}}return out}
function isSystem(dep){return dep.startsWith('/System/Library/')||dep.startsWith('/usr/lib/')}
function expandToken(p,loaderDir){return p.replace(/^@loader_path/,loaderDir).replace(/^@executable_path/,executableOriginDir)}
function resolveDep(origin,dep){if(isSystem(dep))return null;if(dep.startsWith('/'))return fs.existsSync(dep)?fs.realpathSync(dep):null;const loaderDir=path.dirname(origin);if(dep.startsWith('@loader_path/')||dep.startsWith('@executable_path/')){const c=expandToken(dep,loaderDir);return fs.existsSync(c)?fs.realpathSync(c):null}if(dep.startsWith('@rpath/')){const suffix=dep.slice(7);for(const rp of rpaths(origin)){const c=path.join(expandToken(rp,loaderDir),suffix);if(fs.existsSync(c))return fs.realpathSync(c)}const local=path.join(loaderDir,suffix);if(fs.existsSync(local))return fs.realpathSync(local)}return null}
function sha256(file){return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')}
function assertArch(file){const out=run('/usr/bin/file',[file]);if(!out.includes(expectedArch))throw new Error(`Architecture mismatch (${expectedArch} required): ${out.trim()}`)}
function forbidden(v){return v.startsWith('/opt/homebrew/')||v.startsWith('/usr/local/')||v.includes('/Cellar/')||v.startsWith('/opt/local/')||v.startsWith('/Users/')||v.startsWith('/private/tmp/')}
function changeDep(file,from,to){if(from!==to)execFileSync('/usr/bin/install_name_tool',['-change',from,to,file],{stdio:'inherit'})}
function deleteRpath(file,rp){try{execFileSync('/usr/bin/install_name_tool',['-delete_rpath',rp,file],{stdio:'ignore'})}catch{}}

ensureSidecar(ffmpeg,'ffmpeg');ensureSidecar(ffprobe,'ffprobe');assertArch(ffmpeg);assertArch(ffprobe);
fs.rmSync(frameworksDir,{recursive:true,force:true});fs.mkdirSync(frameworksDir,{recursive:true});

const originByStaged=new Map([[ffmpeg,fs.realpathSync(ffmpeg)],[ffprobe,fs.realpathSync(ffprobe)]]);
const queued=[fs.realpathSync(ffmpeg),fs.realpathSync(ffprobe)],seen=new Set(),destByOrigin=new Map(),destByBase=new Map();
while(queued.length){
  const origin=queued.shift();if(seen.has(origin))continue;seen.add(origin);assertArch(origin);
  for(const dep of deps(origin)){
    if(isSystem(dep))continue;
    const resolved=resolveDep(origin,dep);if(!resolved)throw new Error(`Unresolved non-system dependency: ${dep} referenced by ${origin}`);
    assertArch(resolved);const base=path.basename(resolved),dest=path.join(frameworksDir,base);
    if(destByBase.has(base)){const prev=destByBase.get(base);if(sha256(prev)!==sha256(resolved))throw new Error(`Dylib basename collision with different contents: ${base}`);destByOrigin.set(resolved,prev)}
    else{fs.copyFileSync(resolved,dest);fs.chmodSync(dest,0o755);destByBase.set(base,dest);destByOrigin.set(resolved,dest);originByStaged.set(dest,resolved);queued.push(resolved)}
  }
}
const staged=[ffmpeg,ffprobe,...[...destByBase.values()].sort()];
for(const file of staged){
  const origin=originByStaged.get(file)||file;
  for(const dep of deps(file)){
    if(isSystem(dep))continue;
    const resolved=resolveDep(origin,dep);if(!resolved)throw new Error(`Cannot map dependency during patch: ${dep} in ${file}`);
    const framework=destByOrigin.get(resolved)||destByBase.get(path.basename(resolved));if(!framework)throw new Error(`Dependency not in closure: ${resolved}`);
    changeDep(file,dep,`@executable_path/../Frameworks/${path.basename(framework)}`);
  }
  for(const rp of rpaths(file))if(forbidden(expandToken(rp,path.dirname(file)))||forbidden(rp))deleteRpath(file,rp);
  if(file.startsWith(frameworksDir+path.sep))execFileSync('/usr/bin/install_name_tool',['-id',`@executable_path/../Frameworks/${path.basename(file)}`,file],{stdio:'inherit'});
}
for(const file of staged){
  assertArch(file);
  for(const dep of deps(file)){
    if(isSystem(dep))continue;
    if(forbidden(dep))throw new Error(`Forbidden dependency remains in ${file}: ${dep}`);
    if(!dep.startsWith('@executable_path/../Frameworks/'))throw new Error(`Unexpected non-system dependency in ${file}: ${dep}`);
    if(!fs.existsSync(path.join(frameworksDir,path.basename(dep))))throw new Error(`Patched dependency missing from framework closure: ${dep}`);
  }
  for(const rp of rpaths(file))if(forbidden(rp))throw new Error(`Forbidden LC_RPATH remains in ${file}: ${rp}`);
}
const frameworks=[...destByBase.values()].sort().map(p=>'./'+path.relative(tauriDir,p).split(path.sep).join('/'));
fs.mkdirSync(generatedDir,{recursive:true});
fs.writeFileSync(macConfig,JSON.stringify({'$schema':'https://schema.tauri.app/config/2',bundle:{macOS:{frameworks}}},null,2)+'\n');
fs.writeFileSync(manifestPath,JSON.stringify({target,arch:expectedArch,ffmpeg:path.relative(root,ffmpeg),ffprobe:path.relative(root,ffprobe),frameworks,frameworkCount:frameworks.length},null,2)+'\n');
console.log(`[ENDLUME ffmpeg-runtime] portable closure ready: ${frameworks.length} dylibs, target=${target}`);
