import React from 'react';

export function Logo({compact=false}:{compact?:boolean}){
  return <div className={`brandMark ${compact?'compact':''}`} aria-label="ENDLUME Studio">
    <span className="infinity"><i/><i/></span>
    <span className="brandText"><b>ENDLUME</b>{!compact&&<small>STUDIO</small>}</span>
  </div>
}

export function Icon({name}:{name:'folder'|'image'|'crossfade'|'pingpong'|'original'|'effects'|'subscribe'|'ambient'|'settings'|'library'|'render'|'project'|'play'|'save'|'trash'|'refresh'}){
  const paths:Record<string,React.ReactNode>={
    folder:<><path d="M3 7h6l2 2h10v10H3z"/><path d="M3 7V5h6l2 2"/></>,
    image:<><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="m5 17 5-5 3 3 2-2 4 4"/></>,
    crossfade:<><path d="M3 8h7l4 8h7"/><path d="M3 16h7l4-8h7"/></>,
    pingpong:<><path d="M4 8h14"/><path d="m15 5 3 3-3 3"/><path d="M20 16H6"/><path d="m9 13-3 3 3 3"/></>,
    original:<><path d="M4 8h16v8H4z"/><path d="M4 8v8M20 8v8"/></>,
    effects:<><path d="m12 3 1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/><path d="m19 14 .8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8z"/></>,
    subscribe:<><rect x="3" y="6" width="18" height="12" rx="4"/><path d="m10 10 5 2-5 2z"/></>,
    ambient:<><path d="M4 15c3-6 5 6 8 0s5 6 8 0"/><path d="M4 10c3-6 5 6 8 0s5 6 8 0"/></>,
    settings:<><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/></>,
    library:<><rect x="4" y="3" width="5" height="18" rx="1"/><rect x="10" y="3" width="5" height="18" rx="1"/><path d="m16 5 4-1 2 16-4 1z"/></>,
    render:<><path d="M4 4h16v16H4z"/><path d="M7 16h2V9H7zm4 0h2V6h-2zm4 0h2v-4h-2z"/></>,
    project:<><path d="M4 5h16v14H4z"/><path d="M8 9h8M8 13h5"/></>,
    play:<path d="m9 7 8 5-8 5z"/>,save:<><path d="M5 4h12l2 2v14H5z"/><path d="M8 4v6h8V4M8 20v-6h8v6"/></>,
    trash:<><path d="M5 7h14M9 7V4h6v3M8 10v7M12 10v7M16 10v7M7 7l1 13h8l1-13"/></>,
    refresh:<><path d="M19 7V3l-2 2a8 8 0 1 0 2 10"/><path d="M19 3h-4"/></>
  };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>
}

export function Toggle({checked,onChange,label,help}:{checked:boolean;onChange:(v:boolean)=>void;label:string;help?:string}){
  return <label className="toggleRow"><button type="button" className={`toggle ${checked?'on':''}`} onClick={()=>onChange(!checked)} aria-pressed={checked}><i/></button><span>{label}{help&&<small>{help}</small>}</span></label>
}

export function Range({value,min,max,step=1,onChange,unit,minLabel,maxLabel}:{value:number;min:number;max:number;step?:number;onChange:(v:number)=>void;unit?:string;minLabel?:string;maxLabel?:string}){
  const pct=((value-min)/(max-min))*100;
  return <div className="rangeWrap">
    <input className="range" type="range" min={min} max={max} step={step} value={value} onChange={e=>onChange(Number(e.target.value))} style={{'--pct':`${pct}%`} as React.CSSProperties}/>
    <div className="rangeEnds"><span>{minLabel??`${min}${unit||''}`}</span><span>{maxLabel??`${max}${unit||''}`}</span></div>
  </div>
}

export const fmtSeconds=(s?:number)=>{if(s==null||!Number.isFinite(s))return '—';const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),x=Math.floor(s%60);return h?`${h}:${String(m).padStart(2,'0')}:${String(x).padStart(2,'0')}`:`${m}:${String(x).padStart(2,'0')}`};
export const fmtBytes=(n?:number)=>{if(!n)return '—';const u=['Б','КБ','МБ','ГБ','ТБ'];let i=0,x=n;while(x>=1024&&i<u.length-1){x/=1024;i++}return `${x.toFixed(i>2?2:i?1:0)} ${u[i]}`};
export const finishAt=(sec?:number)=>sec==null?'—':new Date(Date.now()+sec*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
