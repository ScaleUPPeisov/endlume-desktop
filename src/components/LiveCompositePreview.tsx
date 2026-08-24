import React,{useEffect,useRef,useState} from 'react';
import type {EffectPreset} from '../types';

export type LivePreviewAssets={basePath:string;baseKind:'image'|'video';overlayPath:string};

type Props={
  assets?:LivePreviewAssets;
  effect:EffectPreset;
  busy?:boolean;
  overlayRef:React.RefObject<HTMLDivElement|null>;
  overlayStyle:React.CSSProperties;
  onDragStart:(e:React.PointerEvent<HTMLDivElement>)=>void;
  onResizeStart:(e:React.PointerEvent<HTMLElement>)=>void;
  onPickColor?:(hex:string)=>void;
};

function hexRgb(hex:string){const raw=hex.replace('#','').trim();const v=Number.parseInt(raw.length===3?raw.split('').map(x=>x+x).join(''):raw,16);return [((v>>16)&255)/255,((v>>8)&255)/255,(v&255)/255] as const}
function rgbHex(r:number,g:number,b:number){return `#${[r,g,b].map(v=>Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,'0')).join('')}`}

export function LiveCompositePreview({assets,effect,busy,overlayRef,overlayStyle,onDragStart,onResizeStart,onPickColor}:Props){
  const canvasRef=useRef<HTMLCanvasElement>(null),videoRef=useRef<HTMLVideoElement>(null),rafRef=useRef<number|undefined>(undefined),effectRef=useRef(effect),brushRaf=useRef<number|undefined>(undefined),lastBrushPoint=useRef<{x:number;y:number}>(),brushDown=useRef(false);
  const [picker,setPicker]=useState(false);
  effectRef.current=effect;

  const sampleAt=(clientX:number,clientY:number)=>{
    const video=videoRef.current,host=overlayRef.current;if(!video||!host||video.readyState<2||video.videoWidth<2||video.videoHeight<2||!onPickColor)return;
    const r=host.getBoundingClientRect();if(r.width<2||r.height<2)return;
    const u=Math.max(0,Math.min(1,(clientX-r.left)/r.width)),v=Math.max(0,Math.min(1,(clientY-r.top)/r.height));
    const sx=Math.max(0,Math.min(video.videoWidth-1,Math.floor(u*video.videoWidth))),sy=Math.max(0,Math.min(video.videoHeight-1,Math.floor(v*video.videoHeight)));
    const c=document.createElement('canvas');c.width=1;c.height=1;const ctx=c.getContext('2d',{willReadFrequently:true});if(!ctx)return;
    try{ctx.drawImage(video,sx,sy,1,1,0,0,1,1);const p=ctx.getImageData(0,0,1,1).data;onPickColor(rgbHex(p[0],p[1],p[2]));}catch{}
  };
  const scheduleSample=(x:number,y:number)=>{lastBrushPoint.current={x,y};if(brushRaf.current!=null)return;brushRaf.current=requestAnimationFrame(()=>{brushRaf.current=undefined;const p=lastBrushPoint.current;if(p)sampleAt(p.x,p.y)})};

  useEffect(()=>{
    const canvas=canvasRef.current,video=videoRef.current;if(!canvas||!video||!assets?.overlayPath)return;
    const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:false,antialias:false,preserveDrawingBuffer:false});if(!gl)return;
    const vs=gl.createShader(gl.VERTEX_SHADER)!,fs=gl.createShader(gl.FRAGMENT_SHADER)!;
    gl.shaderSource(vs,'attribute vec2 p;attribute vec2 t;varying vec2 v;void main(){gl_Position=vec4(p,0.,1.);v=t;}');
    // Fidelity rule: RGB of kept pixels is never modified. Only alpha is calculated.
    // This makes the preview keep the original overlay colours instead of globally boosting saturation/despill.
    gl.shaderSource(fs,`precision mediump float;varying vec2 v;uniform sampler2D tex;uniform vec3 key;uniform float sim;uniform float blend;uniform float mode;uniform float lthr;uniform float ltol;void main(){vec4 px=texture2D(tex,v);vec3 c=px.rgb;float a=px.a;if(mode<.5){float d=distance(c,key)/1.7320508;float lo=max(0.,sim);float hi=min(1.,lo+max(.001,blend));a*=smoothstep(lo,hi,d);}else if(mode<1.5){float l=dot(c,vec3(.2126,.7152,.0722));float lo=max(0.,lthr-ltol);float hi=min(1.,lthr+ltol);a*=smoothstep(lo,hi,l);}gl_FragColor=vec4(c,a);}`);
    gl.compileShader(vs);gl.compileShader(fs);const program=gl.createProgram()!;gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);gl.useProgram(program);
    const pos=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,pos);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);const p=gl.getAttribLocation(program,'p');gl.enableVertexAttribArray(p);gl.vertexAttribPointer(p,2,gl.FLOAT,false,0,0);
    const tc=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,tc);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([0,1,1,1,0,0,0,0,1,1,1,0]),gl.STATIC_DRAW);const t=gl.getAttribLocation(program,'t');gl.enableVertexAttribArray(t);gl.vertexAttribPointer(t,2,gl.FLOAT,false,0,0);
    const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    const uKey=gl.getUniformLocation(program,'key'),uSim=gl.getUniformLocation(program,'sim'),uBlend=gl.getUniformLocation(program,'blend'),uMode=gl.getUniformLocation(program,'mode'),uLthr=gl.getUniformLocation(program,'lthr'),uLtol=gl.getUniformLocation(program,'ltol');
    const draw=()=>{rafRef.current=requestAnimationFrame(draw);if(video.readyState<2||video.videoWidth<2)return;const w=Math.min(640,video.videoWidth),h=Math.max(2,Math.round(w*video.videoHeight/video.videoWidth));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h)}const e=effectRef.current,[r,g,b]=hexRgb(e.keyColor);gl.uniform3f(uKey,r,g,b);gl.uniform1f(uSim,Math.max(.001,Math.min(.6,e.similarity)));gl.uniform1f(uBlend,Math.max(.001,Math.min(.35,e.blend)));gl.uniform1f(uMode,e.mode==='luma'?1:e.mode==='screen'?2:0);gl.uniform1f(uLthr,e.lumaThreshold);gl.uniform1f(uLtol,e.lumaTolerance);gl.bindTexture(gl.TEXTURE_2D,texture);try{gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,video);gl.drawArrays(gl.TRIANGLES,0,6)}catch{}};
    const start=()=>{video.play().catch(()=>{});if(rafRef.current==null)rafRef.current=requestAnimationFrame(draw)};video.addEventListener('loadeddata',start);if(video.readyState>=2)start();
    return()=>{video.removeEventListener('loadeddata',start);if(rafRef.current!=null)cancelAnimationFrame(rafRef.current);rafRef.current=undefined;gl.deleteTexture(texture);gl.deleteBuffer(pos);gl.deleteBuffer(tc);gl.deleteProgram(program);gl.deleteShader(vs);gl.deleteShader(fs)};
  },[assets?.overlayPath]);

  useEffect(()=>()=>{if(brushRaf.current!=null)cancelAnimationFrame(brushRaf.current)},[]);
  if(!assets)return <div className="livePreviewEmpty"><span>{busy?'Подготавливаю Live Preview…':'Выберите проект на основном экране'}</span></div>;
  const base=assets.baseKind==='video'?<video className="livePreviewBase" src={assets.basePath} autoPlay loop muted playsInline/>:<img className="livePreviewBase" src={assets.basePath} draggable={false}/>;
  return <div className={`liveComposite ${picker?'chromaPicking':''}`}>
    {base}
    {effect.mode==='chromakey'&&<button type="button" className={`chromaPickerButton ${picker?'active':''}`} onClick={e=>{e.preventDefault();e.stopPropagation();setPicker(v=>!v)}}>{picker?'✓ ВЫБЕРИ/ПРОВЕДИ ПО ФОНУ':'⌾ ПИПЕТКА / КИСТЬ'}</button>}
    <div ref={overlayRef} className={`liveGpuOverlay ${effect.fullscreen?'fullscreen':''}`} style={overlayStyle}
      onPointerDown={e=>{if(picker){e.preventDefault();e.stopPropagation();brushDown.current=true;scheduleSample(e.clientX,e.clientY);return}onDragStart(e)}}
      onPointerMove={e=>{if(picker&&brushDown.current){e.preventDefault();e.stopPropagation();scheduleSample(e.clientX,e.clientY)}}
      onPointerUp={e=>{if(picker){e.preventDefault();e.stopPropagation();brushDown.current=false;sampleAt(e.clientX,e.clientY)}}
      onPointerCancel={()=>{brushDown.current=false}}>
      <video ref={videoRef} className="liveOverlaySource" src={assets.overlayPath} autoPlay loop muted playsInline/>
      <canvas ref={canvasRef} className="liveOverlayCanvas" style={{mixBlendMode:effect.mode==='screen'?'screen':'normal'}}/>
      {!effect.fullscreen&&!picker&&<><i className="corner nw"/><i className="corner ne"/><i className="corner sw"/><i className="corner se" onPointerDown={onResizeStart}/></>}
    </div>
    {busy&&<div className="livePreviewPreparing">Обновляю proxy…</div>}
  </div>
}
