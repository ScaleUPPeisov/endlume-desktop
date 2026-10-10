function run(argv){
  const pid=Number(argv[0]),cmd=argv[1],a1=argv[2]||'',a2=argv[3]||'';
  const se=Application('System Events');
  const ps=se.applicationProcesses.whose({unixId:pid})();
  if(ps.length!==1)throw new Error('candidate missing');
  const p=ps[0];p.frontmost=true;delay(.12);
  const ws=p.windows();if(!ws.length)throw new Error('no window');const w=ws[0];
  const str=f=>{try{const v=f();return v==null?'':String(v)}catch(_){return ''}};
  function nodes(){let out=[],st=[w],n=0;while(st.length&&n<7000){const e=st.pop();n++;let pos=[],size=[];try{pos=e.position()}catch(_){}try{size=e.size()}catch(_){}out.push({e,role:str(()=>e.role()),name:str(()=>e.name()),desc:str(()=>e.description()),pos,size});let k=[];try{k=e.uiElements()}catch(_){}for(let i=0;i<k.length;i++)st.push(k[i]);}return out;}
  function exact(t,r){return nodes().filter(x=>(x.name===t||x.desc===t)&&(!r||x.role===r));}
  function press(t){const x=exact(t,'AXButton');if(x.length!==1)throw new Error(`button ${t} count=${x.length}`);x[0].e.click();delay(.35);return 'OK';}
  function scroll(t){for(let i=0;i<16;i++){const x=exact(t);if(!x.length)throw new Error(`missing ${t}`);const y=x[0].pos?.[1]||0,wp=w.position(),ws=w.size(),wy=wp[1],wh=ws[1];if(y>wy+70&&y<wy+wh-90)return 'OK';se.keyCode(y>=wy+wh-90?121:116);delay(.2);}throw new Error(`not visible ${t}`);}
  function near(label,names){scroll(label);const ns=nodes(),l=ns.find(x=>x.name===label||x.desc===label);if(!l)throw new Error('label');const ly=(l.pos?.[1]||0)+(l.size?.[1]||0)/2,lx=(l.pos?.[0]||0)+(l.size?.[0]||0)/2;let bs=ns.filter(x=>x.role==='AXButton'&&names.includes(x.name));bs.sort((a,b)=>{const ay=(a.pos?.[1]||0)+(a.size?.[1]||0)/2,by=(b.pos?.[1]||0)+(b.size?.[1]||0)/2,ax=(a.pos?.[0]||0)+(a.size?.[0]||0)/2,bx=(b.pos?.[0]||0)+(b.size?.[0]||0)/2;return (Math.abs(ay-ly)*10+Math.abs(ax-lx))-(Math.abs(by-ly)*10+Math.abs(bx-lx));});if(!bs.length)throw new Error('near button missing');return bs[0];}
  if(cmd==='press')return press(a1);
  if(cmd==='scroll')return scroll(a1);
  if(cmd==='has')return String(exact(a1).length);
  if(cmd==='nearpress'){const b=near(a1,[a2]);b.e.click();delay(.4);return 'OK';}
  if(cmd==='feature'){const want=a2==='ON',b=near(a1,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']),on=b.name==='ВЫКЛЮЧИТЬ';if(on!==want){b.e.click();delay(.45);}const c=near(a1,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']);if((c.name==='ВЫКЛЮЧИТЬ')!==want)throw new Error('feature failed');return 'OK';}
  if(cmd==='geom'){const p=w.position(),s=w.size();return `${p[0]},${p[1]},${s[0]},${s[1]}`;}
  throw new Error('bad cmd');
}
