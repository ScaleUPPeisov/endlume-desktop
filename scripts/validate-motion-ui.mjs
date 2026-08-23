import fs from 'node:fs';

const app=fs.readFileSync('src/pages/App.tsx','utf8');
const main=fs.readFileSync('src/main.tsx','utf8');
const css=fs.readFileSync('src/motion-polish.css','utf8');
const runtime=fs.readFileSync('src/motion.ts','utf8');

const checks=[
  ['motion stylesheet imported',main.includes("import './motion-polish.css'")],
  ['motion runtime installed',app.includes('installMotionRuntime()')],
  ['page content keyed for route animation',app.includes('key={page} className="pageScene"')],
  ['page animation uses compositor transform',css.includes('@keyframes endlumePageIn')&&css.includes('translate3d')],
  ['scroll stays native',css.includes('scroll-behavior:smooth')&&!runtime.includes('preventDefault()')],
  ['scroll listeners are passive',runtime.includes("passive:true")],
  ['adaptive low-fps fallback exists',runtime.includes("motion-lite")&&css.includes('html.motion-lite')],
  ['heavy decoration pauses while scrolling',css.includes('html.motion-scrolling')],
  ['reduced-motion accessibility exists',css.includes('@media (prefers-reduced-motion:reduce)')],
  ['no transition all in motion layer',!css.includes('transition:all')&&!css.includes('transition: all')],
];

for(const [name,ok] of checks){
  if(!ok){console.error(`FAIL: ${name}`);process.exit(1)}
  console.log(`PASS: ${name}`);
}
console.log(`Motion UI validation passed: ${checks.length}/${checks.length}`);
