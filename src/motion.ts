export function installMotionRuntime(){
  const root=document.documentElement;
  let scrollTimer:number|undefined;
  let interactTimer:number|undefined;
  let raf=0;
  let last=performance.now();
  let frames:number[]=[];

  const ensureSampler=()=>{
    if(raf)return;
    last=performance.now();
    const tick=(now:number)=>{
      const active=root.classList.contains('motion-scrolling')||root.classList.contains('motion-interacting');
      if(!active){raf=0;frames=[];return;}
      const dt=now-last;last=now;
      if(dt>0&&dt<80)frames.push(1000/dt);
      if(frames.length>=36){
        const sorted=[...frames].sort((a,b)=>a-b);
        const trimmed=sorted.slice(4,-4);
        const avg=trimmed.reduce((sum,v)=>sum+v,0)/Math.max(1,trimmed.length);
        if(avg<48)root.classList.add('motion-lite');
        else if(avg>56)root.classList.remove('motion-lite');
        frames=[];
      }
      raf=requestAnimationFrame(tick);
    };
    raf=requestAnimationFrame(tick);
  };

  const markScrolling=()=>{
    root.classList.add('motion-scrolling');
    if(scrollTimer)window.clearTimeout(scrollTimer);
    scrollTimer=window.setTimeout(()=>root.classList.remove('motion-scrolling'),130);
    ensureSampler();
  };

  const markInteracting=()=>{
    root.classList.add('motion-interacting');
    if(interactTimer)window.clearTimeout(interactTimer);
    interactTimer=window.setTimeout(()=>root.classList.remove('motion-interacting'),220);
    ensureSampler();
  };

  const onScroll=()=>markScrolling();
  const onWheel=()=>markScrolling();
  const onPointerDown=()=>markInteracting();
  const onPointerUp=()=>markInteracting();
  const onKeyDown=(e:KeyboardEvent)=>{
    if(['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(e.key))markScrolling();
  };

  document.addEventListener('scroll',onScroll,{capture:true,passive:true});
  document.addEventListener('wheel',onWheel,{capture:true,passive:true});
  document.addEventListener('pointerdown',onPointerDown,{capture:true,passive:true});
  document.addEventListener('pointerup',onPointerUp,{capture:true,passive:true});
  document.addEventListener('keydown',onKeyDown,{capture:true});

  return()=>{
    if(scrollTimer)window.clearTimeout(scrollTimer);
    if(interactTimer)window.clearTimeout(interactTimer);
    if(raf)cancelAnimationFrame(raf);
    root.classList.remove('motion-scrolling','motion-interacting','motion-lite');
    document.removeEventListener('scroll',onScroll,true);
    document.removeEventListener('wheel',onWheel,true);
    document.removeEventListener('pointerdown',onPointerDown,true);
    document.removeEventListener('pointerup',onPointerUp,true);
    document.removeEventListener('keydown',onKeyDown,true);
  };
}
