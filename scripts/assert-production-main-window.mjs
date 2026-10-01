import fs from 'node:fs';
import path from 'node:path';

const configPath=path.resolve(process.argv[2]||'src-tauri/tauri.conf.json');
const config=JSON.parse(fs.readFileSync(configPath,'utf8'));
const windows=config?.app?.windows;

if(!Array.isArray(windows)||windows.length===0){
  throw new Error('PRODUCTION BUILD HAS NO MAIN WINDOW: app.windows is missing or empty');
}
const main=windows.filter((w)=>w&&w.label==='main');
if(main.length!==1){
  throw new Error(`PRODUCTION BUILD MUST CONTAIN EXACTLY ONE label="main" WINDOW; found ${main.length}`);
}
if(!main[0].title){
  throw new Error('PRODUCTION MAIN WINDOW HAS NO TITLE');
}
console.log(JSON.stringify({
  kind:'ENDLUME_PRODUCTION_MAIN_WINDOW_PASS',
  config:configPath,
  windows:windows.length,
  mainLabel:main[0].label,
  mainTitle:main[0].title
}));
