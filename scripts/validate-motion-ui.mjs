import fs from 'node:fs';

const app=fs.readFileSync('src/pages/App.tsx','utf8');
const main=fs.readFileSync('src/main.tsx','utf8');
const css=fs.readFileSync('src/motion-polish.css','utf8');
const runtime=fs.readFileSync('src/motion.ts','utf8');

const checks=[
  ['motion stylesheet imported',main.includes("import './motion-polish.css'")],
  ['page content keyed for route animation',app.includes('key={page} className="pageScene"')],
  ['page animation is compositor-only',css.includes('@keyframes endlumePageIn')&&css.includes('translate3d')&&!css.includes('scale(.997)')],
  ['native scroll runtime has no wheel listener',!runtime.includes("addEventListener('wheel'")&&!runtime.includes('preventDefault')],
  ['native scroll runtime has no scroll listener',!runtime.includes("addEventListener('scroll'")],
  ['no RAF FPS governor during interaction',!runtime.includes('requestAnimationFrame')&&!runtime.includes('motion-lite')],
  ['WebView scrollbar is hidden',css.includes('::-webkit-scrollbar')&&css.includes('width:0!important')&&css.includes('scrollbar-width:none!important')],
  ['no stable scrollbar gutter',css.includes('scrollbar-gutter:auto!important')&&!css.includes('scrollbar-gutter:stable')],
  ['no content-visibility auto',!css.includes('content-visibility:auto')],
  ['no layout/style paint containment on scrolling cards',!css.includes('contain:layout')&&!css.includes('contain:layout style paint')],
  ['button motion avoids filter/box-shadow transitions',css.includes('transition-property:transform,opacity,color,border-color,background-color')],
  ['reduced-motion accessibility exists',css.includes('@media (prefers-reduced-motion:reduce)')],
  ['no transition all in motion layer',!css.includes('transition:all')&&!css.includes('transition: all')],
];

for(const [name,ok] of checks){
  if(!ok){console.error(`FAIL: ${name}`);process.exit(1)}
  console.log(`PASS: ${name}`);
}
console.log(`Motion UI validation passed: ${checks.length}/${checks.length}`);
