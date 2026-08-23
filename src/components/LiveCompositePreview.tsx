import React,{useEffect,useRef} from 'react';
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
};

function hexRgb(hex:string){const raw=hex.replace('#','').trim();const v=Number.parseInt(raw.length===3?raw.split('').map(x=>x+x).join(''):raw,16);return [((v>>16)&255)/255,((v>>8)&255)/255,(v&255)/255] as const}

export function LiveCompositePreview({assets,effect,busy,overlayRef,overlayStyle,onDragStart,onResizeStart}:Props){
  const canvasRef=useRef<HTMLCanvasElement>(null),videoRef=useRef<HTMLVideoElement>(null),rafRef=useRef<number|undefined>(undefined),effectRef=useRef(effect);
  effectRef.current=effect;
  useEffect(()=>{
    const canvas=canvasRef.current,video=videoRef.current;if(!canvas||!video||!assets?.overlayPath)return;
    const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:false,antialias:false,preserveDrawingBuffer:false});if(!gl)return;
    const vs=gl.createShader(gl.VERTEX_SHADER)!,fs=gl.createShader(gl.FRAGMENT_SHADER)!;
    gl.shaderSource(vs,'attribute vec2 p;attribute vec2 t;varying vec2 v;void main(){gl_Position=vec4(p,0.,1.);v=t;}');
    gl.shaderSource(fs,`precision mediump float;varying vec2 v;uniform sampler2D tex;uniform vec3 key;uniform float sim;uniform float blend;uniform float mode;uniform float lthr;uniform float ltol;uniform float sat;vec3 saturation(vec3 c,float s){float l=dot(c,vec3(.2126,.7152,.0722));return mix(vec3(l),c,s);}void main(){vec4 px=texture2D(tex,v);vec3 c=saturation(px.rgb,sat);float a=1.;if(mode<.5){float d=distance(c,key);a=smoothstep(sim,max(sim+.001,sim+blend),d);if(a<.99){c.g*=mix(.78,1.,a);}}else if(mode<1.5){float l=dot(c,vec3(.2126,.7152,.0722));a=smoothstep(max(0.,lthr-ltol),min(1.,lthr+ltol),l);}gl_FragColor=vec4(c,a*px.a);}`);
    gl.compileShader(vs);gl.compileShader(fs);const program=gl.createProgram()!;gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);gl.useProgram(program);
    const pos=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,pos);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);const p=gl.getAttribLocation(program,'p');gl.enableVertexAttribArray(p);gl.vertexAttribPointer(p,2,gl.FLOAT,false,0,0);
    const tc=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,tc);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([0,1,1,1,0,0,0,0,1,1,1,0]),gl.STATIC_DRAW);const t=gl.getAttribLocation(program,'t');gl.enableVertexAttribArray(t);gl.vertexAttribPointer(t,2,gl.FLOAT,false,0,0);
    const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    const draw=()=>{rafRef.current=requestAnimationFrame(draw);if(video.readyState<2||video.videoWidth<2)return;const w=Math.min(640,video.videoWidth),h=Math.max(2,Math.round(w*video.videoHeight/video.videoWidth));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h)}const e=effectRef.current,[r,g,b]=hexRgb(e.keyColor);gl.uniform3f(gl.getUniformLocation(program,'key'),r,g,b);gl.uniform1f(gl.getUniformLocation(program,'sim'),Math.max(.001,e.similarity));gl.uniform1f(gl.getUniformLocation(program,'blend'),Math.max(.001,e.blend));gl.uniform1f(gl.getUniformLocation(program,'mode'),e.mode==='luma'?1:e.mode==='screen'?2:0);gl.uniform1f(gl.getUniformLocation(program,'lthr'),e.lumaThreshold);gl.uniform1f(gl.getUniformLocation(program,'ltol'),e.lumaTolerance);gl.uniform1f(gl.getUniformLocation(program,'sat'),e.saturation||1);gl.bindTexture(gl.TEXTURE_2D,texture);try{gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,video);gl.drawArrays(gl.TRIANGLES,0,6)}catch{}};
    const start=()=>{video.play().catch(()=>{});if(rafRef.current==null)rafRef.current=requestAnimationFrame(draw)};video.addEventListener('loadeddata',start);if(video.readyState>=2)start();
    return()=>{video.removeEventListener('loadeddata',start);if(rafRef.current!=null)cancelAnimationFrame(rafRef.current);rafRef.current=undefined;gl.deleteTexture(texture);gl.deleteBuffer(pos);gl.deleteBuffer(tc);gl.deleteProgram(program);gl.deleteShader(vs);gl.deleteShader(fs)};
  },[assets?.overlayPath]);
  if(!assets)return <div className="livePreviewEmpty"><span>{busy?'Подготавливаю Live Preview…':'Выберите проект на основном экране'}</span></div>;
  const base=assets.baseKind==='video'?<video className="livePreviewBase" src={assets.basePath} autoPlay loop muted playsInline/>:<img className="livePreviewBase" src={assets.basePath} draggable={false}/>;
  return <div className="liveComposite">
    {base}
    <div ref={overlayRef} className={`liveGpuOverlay ${effect.fullscreen?'fullscreen':''}`} style={overlayStyle} onPointerDown={onDragStart}>
      <video ref={videoRef} className="liveOverlaySource" src={assets.overlayPath} autoPlay loop muted playsInline/>
      <canvas ref={canvasRef} className="liveOverlayCanvas" style={{mixBlendMode:effect.mode==='screen'?'screen':'normal'}}/>
      {!effect.fullscreen&&<><i className="corner nw"/><i className="corner ne"/><i className="corner sw"/><i className="corner se" onPointerDown={onResizeStart}/></>}
    </div>
    {busy&&<div className="livePreviewPreparing">Обновляю proxy…</div>}
  </div>
}
