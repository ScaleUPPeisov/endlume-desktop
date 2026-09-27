import fs from 'node:fs';

const app=fs.readFileSync('src/pages/App.tsx','utf8');
const main=fs.readFileSync('src/main.tsx','utf8');
const css=fs.readFileSync('src/motion-polish.css','utf8');
const runtime=fs.readFileSync('src/motion.ts','utf8');
const baseCss=fs.readFileSync('src/styles.css','utf8');
const project=fs.readFileSync('src/pages/ProjectPage.tsx','utf8');

const pageSceneRule=(css.match(/\.pageScene\s*\{([^}]*)\}/)||[])[1]||'';
const pageKeyframes=(css.match(/@keyframes\s+endlumePageIn\s*\{([^\n]*)\}/)||[])[1]||'';
const queueRule=(css.match(/\.queueCard\s*\{([^}]*)\}/)||[])[1]||'';

const checks=[
  ['motion stylesheet imported',main.includes("import './motion-polish.css'")],
  ['page content keyed for route animation',app.includes('key={page} className="pageScene"')],
  ['page transition is opacity-only',css.includes('@keyframes endlumePageIn{from{opacity:.38}to{opacity:1}}')&&!pageKeyframes.includes('transform')&&!pageKeyframes.includes('filter')],
  ['page wrapper cannot capture fixed footer',pageSceneRule.includes('transform:none!important')&&pageSceneRule.includes('filter:none!important')&&pageSceneRule.includes('perspective:none!important')&&pageSceneRule.includes('contain:none!important')],
  ['project page still renders fixed queue footer',project.includes('className="projectBottom"')&&baseCss.includes('.projectBottom{position:fixed')],
  ['motion layer reasserts viewport-fixed footer',css.includes('.projectBottom{')&&css.includes('position:fixed!important')&&css.includes('bottom:0!important')&&css.includes('z-index:50!important')],
  ['project content reserves footer space',css.includes('.projectColumn{padding-bottom:105px!important}')],
  ['native scroll runtime has no wheel listener',!runtime.includes("addEventListener('wheel'")&&!runtime.includes('preventDefault')],
  ['native scroll runtime has no scroll listener',!runtime.includes("addEventListener('scroll'")],
  ['no per-frame FPS governor during interaction',!runtime.includes('requestAnimationFrame')&&!runtime.includes('motion-lite')],
  ['WebView scrollbar is hidden',css.includes('::-webkit-scrollbar')&&css.includes('width:0!important')&&css.includes('scrollbar-width:none!important')],
  ['no stable scrollbar gutter',css.includes('scrollbar-gutter:auto!important')&&!css.includes('scrollbar-gutter:stable')],
  ['8.41 queue virtualization is scoped to queueCard',queueRule.includes('content-visibility:auto!important')&&queueRule.includes('contain:layout paint style!important')&&queueRule.includes('contain-intrinsic-size:90px!important')],
  ['content visibility is not applied to pageScene',!pageSceneRule.includes('content-visibility:auto')],
  ['button motion avoids filter/box-shadow transitions',css.includes('transition-property:transform,opacity,color,border-color,background-color')],
  ['reduced-motion accessibility exists',css.includes('@media (prefers-reduced-motion:reduce)')],
  ['no transition all in motion layer',!css.includes('transition:all')&&!css.includes('transition: all')],
];

for(const [name,ok] of checks){
  if(!ok){console.error(`FAIL: ${name}`);process.exit(1)}
  console.log(`PASS: ${name}`);
}
console.log(`ENDLUME 8.41 Motion/layout UI validation passed: ${checks.length}/${checks.length}`);
