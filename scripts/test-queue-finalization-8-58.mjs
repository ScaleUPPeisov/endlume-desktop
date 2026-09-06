import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';

const compiled=process.argv[2];
if(!compiled)throw new Error('usage: node test-queue-finalization-8-58.mjs <compiled queue-state.js>');
const {applyProjectPatch,applyQueueSnapshot}=await import(pathToFileURL(compiled).href);

const mk=(i)=>({id:`job-${String(i).padStart(3,'0')}`,name:String(i).padStart(3,'0'),path:`/fixture/${String(i).padStart(3,'0')}`,media:['image.png'],audio:Array.from({length:10},(_,x)=>`track-${x}.mp3`),status:'queued',progress:0,stage:'Ожидает в очереди',elapsedSec:0});

// Exact regression seen in 8.57: RAF-held 97% progress arrives after render-done.
let projects=[mk(1),mk(2)];
projects=applyQueueSnapshot(projects,{active:{project:projects[0]},pending:[{project:projects[1]}]});
projects=applyProjectPatch(projects,'job-001',{status:'rendering',progress:97,stage:'Финальная проверка FFprobe',elapsedSec:40});
projects=applyProjectPatch(projects,'job-001',{status:'done',progress:100,stage:'Готово',resultPath:'/out/001 — Ready Videos.mp4',resultBytes:500_000_000,etaSec:0,elapsedSec:41});
projects=applyProjectPatch(projects,'job-001',{status:'rendering',progress:97,stage:'Финальная проверка FFprobe',elapsedSec:40.5});
let first=projects.find(p=>p.id==='job-001');
assert.equal(first.status,'done');
assert.equal(first.progress,100);
assert.equal(first.stage,'Готово');
assert.equal(first.resultPath,'/out/001 — Ready Videos.mp4');
assert.equal(first.resultBytes,500_000_000);

// A later queue snapshot for the next job must not downgrade the completed card.
projects=applyQueueSnapshot(projects,{active:{project:projects[1]},pending:[]});
first=projects.find(p=>p.id==='job-001');
assert.equal(first.status,'done');
assert.equal(first.progress,100);
assert.equal(first.resultPath,'/out/001 — Ready Videos.mp4');

// Full 40-project queue with deliberately hostile event ordering.
projects=Array.from({length:40},(_,i)=>mk(i+1));
for(let i=0;i<40;i++){
  const current=projects[i];
  const pending=projects.slice(i+1).map(project=>({project}));
  projects=applyQueueSnapshot(projects,{active:{project:current},pending});
  projects=applyProjectPatch(projects,current.id,{status:'rendering',progress:73,stage:'Strict 8.57: fidelity master полного Effects-цикла',elapsedSec:20});
  projects=applyProjectPatch(projects,current.id,{status:'rendering',progress:97,stage:'Финальная проверка FFprobe',elapsedSec:36});
  projects=applyProjectPatch(projects,current.id,{status:'done',progress:100,stage:'Готово',resultPath:`/out/${current.name} — Ready Videos.mp4`,resultBytes:500_000_000,etaSec:0,elapsedSec:37});
  // Simulate the exact stale RAF event that broke 8.57.
  projects=applyProjectPatch(projects,current.id,{status:'rendering',progress:97,stage:'Финальная проверка FFprobe',elapsedSec:36.8});
  if(i+1<40)projects=applyQueueSnapshot(projects,{active:{project:projects.find(p=>p.id===`job-${String(i+2).padStart(3,'0')}`)},pending:projects.filter(p=>Number(p.name)>i+2&&!['done','error'].includes(p.status)).map(project=>({project}))});
  const done=projects.find(p=>p.id===current.id);
  assert.equal(done.status,'done',`${current.id} status regressed`);
  assert.equal(done.progress,100,`${current.id} progress regressed`);
  assert.equal(done.resultBytes,500_000_000,`${current.id} result bytes lost`);
  assert.ok(done.resultPath?.endsWith('Ready Videos.mp4'),`${current.id} result path lost`);
}
assert.equal(projects.filter(p=>p.status==='done').length,40);
assert.equal(projects.filter(p=>p.progress===100).length,40);

// Error is also terminal and cannot be turned back into rendering by stale telemetry.
let errors=[mk(99)];
errors=applyProjectPatch(errors,'job-099',{status:'error',progress:100,stage:'Ошибка: fixture failure',error:'fixture failure'});
errors=applyProjectPatch(errors,'job-099',{status:'rendering',progress:97,stage:'Финальная проверка FFprobe'});
assert.equal(errors[0].status,'error');
assert.equal(errors[0].progress,100);
assert.match(errors[0].stage,/Ошибка/);

console.log('PASS: ENDLUME 8.58 queue finalization race regression — terminal state is monotonic for 40/40 jobs');
