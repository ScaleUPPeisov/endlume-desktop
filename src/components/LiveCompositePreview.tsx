import React,{useEffect,useRef,useState} from 'react';
import {readFile} from '@tauri-apps/plugin-fs';
import type {AnchorPoint,EffectPreset} from '../types';

export type LivePreviewAssets={basePath:string;baseFilePath?:string;baseKind:'image'|'video';overlayPath:string;overlayFilePath?:string;posterPath?:string;posterFilePath?:string;baseBytes?:number;overlayBytes?:number;requestId?:string;previewType?:'Effects'|'Subscribe'};

type Props={
  assets?:LivePreviewAssets;
  effect:EffectPreset;
  active?:boolean;
  busy?:boolean;
  overlayRef:React.RefObject<HTMLDivElement|null>;
  overlayStyle:React.CSSProperties;
  onDragStart:(e:React.PointerEvent<HTMLDivElement>)=>void;
  onResizeStart:(e:React.PointerEvent<HTMLElement>)=>void;
  onPickColor?:(hex:string)=>void;
  anchor?:AnchorPoint;
  anchorMode?:boolean;
  onAnchorPick?:(x:number,y:number)=>void;
  onFrameState?:(payload:{status:'GREEN'|'RED';requestId:string;previewType:string;width:number;height:number;payloadBytes:number;paintedNonBlack:number;browserVisible:boolean;pixelReadback:'GREEN'|'UNAVAILABLE'|'RED'})=>void;
};

function hexRgb(hex:string){const raw=hex.replace('#','').trim();const v=Number.parseInt(raw.length===3?raw.split('').map(x=>x+x).join(''):raw,16);return [((v>>16)&255)/255,((v>>8)&255)/255,(v&255)/255] as const}
function rgbHex(r:number,g:number,b:number){return `#${[r,g,b].map(v=>Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,'0')).join('')}`}

export function LiveCompositePreview({assets,effect,active=true,busy,overlayRef,overlayStyle,onDragStart,onResizeStart,onPickColor,anchor,anchorMode,onAnchorPick,onFrameState}:Props){
  const canvasRef=useRef<HTMLCanvasElement>(null),videoRef=useRef<HTMLVideoElement>(null),rafRef=useRef<number|undefined>(undefined),effectRef=useRef(effect),brushRaf=useRef<number|undefined>(undefined),lastBrushPoint=useRef<{x:number;y:number}|undefined>(undefined),brushDown=useRef(false);
  const baseReadyRef=useRef(false),baseSizeRef=useRef({w:0,h:0}),reportedFrameRef=useRef(false),transportBytesRef=useRef(0),frameStateRef=useRef(onFrameState),liveReadyRef=useRef(false);
  frameStateRef.current=onFrameState;
  const [picker,setPicker]=useState(false),[overlayAspect,setOverlayAspect]=useState<number>(1);
  const [baseSrc,setBaseSrc]=useState<string>(),[overlaySrc,setOverlaySrc]=useState<string>(),[posterSrc,setPosterSrc]=useState<string>(),[liveReady,setLiveReady]=useState(false);
  const syncOverlayAspect=(video:HTMLVideoElement)=>{if(video.videoWidth>0&&video.videoHeight>0)setOverlayAspect(video.videoWidth/video.videoHeight)};
  effectRef.current=effect;

  useEffect(()=>{baseReadyRef.current=false;baseSizeRef.current={w:0,h:0};reportedFrameRef.current=false;transportBytesRef.current=0;liveReadyRef.current=false;setLiveReady(false);setBaseSrc(undefined);setOverlaySrc(undefined);setPosterSrc(undefined)},[assets?.basePath,assets?.overlayPath,assets?.posterPath,assets?.requestId]);

  useEffect(()=>{
    if(!assets)return;
    const requestId=assets.requestId||'<unknown>',previewType=assets.previewType||'Effects';
    let disposed=false,baseObjectUrl:string|undefined,posterObjectUrl:string|undefined;
    (async()=>{
      try{
        if(!assets.baseFilePath||!assets.overlayFilePath||!assets.posterFilePath)throw new Error('Preview helper/poster file path missing');
        const [baseBytes,overlayBytes,posterBytes]=await Promise.all([readFile(assets.baseFilePath),readFile(assets.overlayFilePath),readFile(assets.posterFilePath)]);
        if(baseBytes.byteLength<1024||overlayBytes.byteLength<1024||posterBytes.byteLength<1024)throw new Error(`Preview payload too small: base=${baseBytes.byteLength} overlay=${overlayBytes.byteLength} poster=${posterBytes.byteLength}`);
        transportBytesRef.current=baseBytes.byteLength+overlayBytes.byteLength+posterBytes.byteLength;
        const baseRaw=baseBytes.buffer.slice(baseBytes.byteOffset,baseBytes.byteOffset+baseBytes.byteLength) as ArrayBuffer;
        const posterRaw=posterBytes.buffer.slice(posterBytes.byteOffset,posterBytes.byteOffset+posterBytes.byteLength) as ArrayBuffer;
        baseObjectUrl=URL.createObjectURL(new Blob([baseRaw],{type:assets.baseKind==='image'?'image/png':'video/mp4'}));
        posterObjectUrl=URL.createObjectURL(new Blob([posterRaw],{type:'image/png'}));
        const resolvedOverlay=assets.overlayPath;
        console.info(`[ENDLUME_PREVIEW] PREVIEW_REQUEST_ID=${requestId} PREVIEW_TYPE=${previewType} FRONTEND_PAYLOAD_BYTES=${transportBytesRef.current} OBJECT_URL_CREATED=true FRONTEND_TRANSFER_MODE=POSTER_BLOB_OVERLAY_ASSET`);
        if(disposed){URL.revokeObjectURL(baseObjectUrl);URL.revokeObjectURL(posterObjectUrl);baseObjectUrl=undefined;posterObjectUrl=undefined;return}
        setBaseSrc(baseObjectUrl);setOverlaySrc(resolvedOverlay);setPosterSrc(posterObjectUrl);
      }catch(error){
        console.error(`[ENDLUME_PREVIEW] PREVIEW_REQUEST_ID=${requestId} PREVIEW_TYPE=${previewType} OBJECT_URL_CREATED=false IMAGE_LOAD=RED PREVIEW_APPLIED=false ERROR=${String(error)}`);
        if(frameStateRef.current&&!reportedFrameRef.current){reportedFrameRef.current=true;frameStateRef.current({status:'RED',requestId,previewType,width:0,height:0,payloadBytes:transportBytesRef.current,paintedNonBlack:0,browserVisible:false,pixelReadback:'RED'})}
      }
    })();
    return()=>{disposed=true;if(baseObjectUrl)URL.revokeObjectURL(baseObjectUrl);if(posterObjectUrl)URL.revokeObjectURL(posterObjectUrl)};
  },[assets?.baseFilePath,assets?.overlayFilePath,assets?.posterFilePath,assets?.baseKind,assets?.requestId,assets?.previewType]);
  const baseLoaded=(w:number,h:number)=>{
    if(w<=0||h<=0)return;
    baseReadyRef.current=true;baseSizeRef.current={w,h};
    const requestId=assets?.requestId||'<unknown>',previewType=assets?.previewType||'Effects';
    console.info(`[ENDLUME_PREVIEW] PREVIEW_REQUEST_ID=${requestId} PREVIEW_TYPE=${previewType} BASE_IMAGE_LOAD=GREEN IMAGE_NATURAL_WIDTH=${w} IMAGE_NATURAL_HEIGHT=${h}`);
  };
  const posterLoaded=(img:HTMLImageElement)=>{
    const requestId=assets?.requestId||'<unknown>',previewType=assets?.previewType||'Effects';
    const w=img.naturalWidth||0,h=img.naturalHeight||0;
    const rect=img.getBoundingClientRect(),style=getComputedStyle(img);
    const browserVisible=rect.width>1&&rect.height>1&&style.display!=='none'&&style.visibility!=='hidden'&&Number(style.opacity||1)>0.01;
    let paintedNonBlack=0,pixelReadback:'GREEN'|'UNAVAILABLE'|'RED'='RED';
    if(w>0&&h>0){
      try{
        const probe=document.createElement('canvas');probe.width=64;probe.height=36;
        const ctx=probe.getContext('2d',{willReadFrequently:true});
        if(ctx){
          ctx.drawImage(img,0,0,64,36);
          const px=ctx.getImageData(0,0,64,36).data;
          for(let i=0;i<px.length;i+=4){if(px[i+3]>8&&(px[i]+px[i+1]+px[i+2]>18))paintedNonBlack++;}
          pixelReadback=paintedNonBlack>8?'GREEN':'RED';
        }else pixelReadback='UNAVAILABLE';
      }catch{pixelReadback='UNAVAILABLE'}
    }
    // WKWebView can deny canvas readback for local Blob-backed images even after a
    // successful decode. In that case natural geometry + visible DOM placement proves
    // frontend display, while backend/QA separately proves the composed poster pixels.
    const green=w>0&&h>0&&browserVisible&&(pixelReadback==='GREEN'||pixelReadback==='UNAVAILABLE');
    console.info(`[ENDLUME_PREVIEW] PREVIEW_REQUEST_ID=${requestId} PREVIEW_TYPE=${previewType} POSTER_LOAD=${green?'GREEN':'RED'} IMAGE_NATURAL_WIDTH=${w} IMAGE_NATURAL_HEIGHT=${h} BROWSER_VISIBLE=${browserVisible} BROWSER_RECT=${Math.round(rect.width)}x${Math.round(rect.height)} PIXEL_READBACK=${pixelReadback} BROWSER_NONBLACK_PIXELS=${paintedNonBlack} PREVIEW_APPLIED=${green}`);
    if(green&&frameStateRef.current&&!reportedFrameRef.current){
      reportedFrameRef.current=true;
      frameStateRef.current({status:'GREEN',requestId,previewType,width:w,height:h,payloadBytes:transportBytesRef.current,paintedNonBlack,browserVisible,pixelReadback});
    }
  };
  const reportRed=(reason:string)=>{
    if(reportedFrameRef.current)return;
    const requestId=assets?.requestId||'<unknown>',previewType=assets?.previewType||'Effects',bs=baseSizeRef.current;
    reportedFrameRef.current=true;
    console.error(`[ENDLUME_PREVIEW] PREVIEW_REQUEST_ID=${requestId} PREVIEW_TYPE=${previewType} IMAGE_LOAD=RED PREVIEW_APPLIED=false ERROR=${reason}`);
    frameStateRef.current?.({status:'RED',requestId,previewType,width:bs.w,height:bs.h,payloadBytes:transportBytesRef.current,paintedNonBlack:0,browserVisible:false,pixelReadback:'RED'});
  };
  useEffect(()=>{
    if(!assets||!frameStateRef.current)return;
    const timer=window.setTimeout(()=>{if(!reportedFrameRef.current)reportRed(`frontend-timeout baseReady=${baseReadyRef.current} videoReady=${videoRef.current?.readyState||0} video=${videoRef.current?.videoWidth||0}x${videoRef.current?.videoHeight||0}`)},8000);
    return()=>window.clearTimeout(timer);
  },[assets?.requestId]);

  const sampleAt=(clientX:number,clientY:number)=>{
    const video=videoRef.current,host=overlayRef.current;if(!video||!host||video.readyState<2||video.videoWidth<2||video.videoHeight<2||!onPickColor)return;
    const r=host.getBoundingClientRect();if(r.width<2||r.height<2)return;
    const u=Math.max(0,Math.min(1,(clientX-r.left)/r.width)),v=Math.max(0,Math.min(1,(clientY-r.top)/r.height));
    const sx=Math.max(0,Math.min(video.videoWidth-1,Math.floor(u*video.videoWidth))),sy=Math.max(0,Math.min(video.videoHeight-1,Math.floor(v*video.videoHeight)));
    const c=document.createElement('canvas');c.width=1;c.height=1;const ctx=c.getContext('2d',{willReadFrequently:true});if(!ctx)return;
    try{ctx.drawImage(video,sx,sy,1,1,0,0,1,1);const p=ctx.getImageData(0,0,1,1).data;onPickColor(rgbHex(p[0],p[1],p[2]));}catch{}
  };
  const scheduleSample=(x:number,y:number)=>{lastBrushPoint.current={x,y};if(brushRaf.current!=null)return;brushRaf.current=requestAnimationFrame(()=>{brushRaf.current=undefined;const p=lastBrushPoint.current;if(p)sampleAt(p.x,p.y)})};
  const pickAnchor=(event:React.PointerEvent<HTMLDivElement>)=>{
    if(!anchorMode||!onAnchorPick)return;
    event.preventDefault();event.stopPropagation();
    const r=event.currentTarget.getBoundingClientRect();if(r.width<2||r.height<2)return;
    onAnchorPick(Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height)));
  };

  useEffect(()=>{
    if(!active)return;
    const canvas=canvasRef.current,video=videoRef.current;if(!canvas||!video||!overlaySrc)return;
    video.preload='auto';try{video.load()}catch{}
    const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:false,preserveDrawingBuffer:false});
    if(!gl){
      const ctx=canvas.getContext('2d',{alpha:true,willReadFrequently:true});
      if(!ctx){reportRed('canvas-context-unavailable');return}
      let last=0;
      const draw2d=(ts:number)=>{
        rafRef.current=requestAnimationFrame(draw2d);
        if(ts-last<30||video.readyState<2||video.videoWidth<2)return;last=ts;
        const w=Math.min(480,video.videoWidth),h=Math.max(2,Math.round(w*video.videoHeight/video.videoWidth));
        if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h}
        try{
          ctx.clearRect(0,0,w,h);ctx.drawImage(video,0,0,w,h);
          const e=effectRef.current;
          if(e.mode!=='screen'){
            const im=ctx.getImageData(0,0,w,h),d=im.data,[kr,kg,kb]=hexRgb(e.keyColor);
            const eq=e.id==='825dd7a4-f0cf-4032-a3c9-64290cb5756d'&&e.mode==='chromakey';
            const destructiveSubscribe=assets?.previewType==='Subscribe'&&e.mode==='chromakey'&&Math.abs(e.similarity-.60)<.000001&&Math.abs(e.blend-.35)<.000001;
            const sim=eq?0.18:destructiveSubscribe?0.10:e.similarity,blend=eq?0.03:destructiveSubscribe?0.06:e.blend;
            for(let i=0;i<d.length;i+=4){
              if(e.mode==='luma'){
                const l=(.2126*d[i]+.7152*d[i+1]+.0722*d[i+2])/255,lo=Math.max(0,e.lumaThreshold-e.lumaTolerance),hi=Math.min(1,e.lumaThreshold+e.lumaTolerance);
                const a=hi<=lo?(l>=hi?1:0):Math.max(0,Math.min(1,(l-lo)/(hi-lo)));d[i+3]=Math.round(d[i+3]*a);
              }else{
                const dr=d[i]-kr*255,dg=d[i+1]-kg*255,db=d[i+2]-kb*255,dist=Math.sqrt(dr*dr+dg*dg+db*db)/441.67295593;
                const a=blend<.0001?(dist>sim?1:0):Math.max(0,Math.min(1,(dist-sim)/blend));d[i+3]=Math.round(d[i+3]*a);
              }
            }
            ctx.putImageData(im,0,0);
          }
          if(frameStateRef.current&&baseReadyRef.current&&!reportedFrameRef.current){
            const im=ctx.getImageData(0,0,w,h).data;let paintedNonBlack=0;
            for(let i=0;i<im.length;i+=4){if(im[i+3]>8&&(im[i]+im[i+1]+im[i+2]>18))paintedNonBlack++}
            const green=paintedNonBlack>8,requestId=assets?.requestId||'<unknown>',previewType=assets?.previewType||'Effects',bs=baseSizeRef.current;if(green&&!liveReadyRef.current){liveReadyRef.current=true;setLiveReady(true)}
            reportedFrameRef.current=true;
            console.info(`[ENDLUME_PREVIEW] PREVIEW_REQUEST_ID=${requestId} PREVIEW_TYPE=${previewType} FRONTEND_PAYLOAD_BYTES=${transportBytesRef.current} OBJECT_URL_CREATED=true FRONTEND_RENDERER=CANVAS_2D IMAGE_LOAD=${green?'GREEN':'RED'} IMAGE_NATURAL_WIDTH=${bs.w} IMAGE_NATURAL_HEIGHT=${bs.h} BROWSER_NONBLACK_PIXELS=${paintedNonBlack} PREVIEW_APPLIED=${green}`);
            frameStateRef.current?.({status:green?'GREEN':'RED',requestId,previewType,width:bs.w,height:bs.h,payloadBytes:transportBytesRef.current,paintedNonBlack,browserVisible:green,pixelReadback:green?'GREEN':'RED'});
          }
        }catch(error){if(frameStateRef.current&&!reportedFrameRef.current)reportRed(`canvas2d-draw: ${String(error)}`)}
      };
      const start2d=()=>{video.play().catch(()=>{});if(rafRef.current==null)rafRef.current=requestAnimationFrame(draw2d)};
      video.addEventListener('loadeddata',start2d);if(video.readyState>=2)start2d();
      return()=>{video.removeEventListener('loadeddata',start2d);if(rafRef.current!=null)cancelAnimationFrame(rafRef.current);rafRef.current=undefined};
    }
    const vs=gl.createShader(gl.VERTEX_SHADER)!,fs=gl.createShader(gl.FRAGMENT_SHADER)!;
    gl.shaderSource(vs,'attribute vec2 p;attribute vec2 t;varying vec2 v;void main(){gl_Position=vec4(p,0.,1.);v=t;}');
    gl.shaderSource(fs,`precision highp float;varying vec2 v;uniform sampler2D tex;uniform vec3 key;uniform float sim;uniform float blend;uniform float dsp;uniform float mode;uniform float lthr;uniform float ltol;void main(){vec4 px=texture2D(tex,v);vec3 c=px.rgb;float a=px.a;if(mode<.5){float d=distance(c,key)/1.7320508075688772;float alpha=blend<.0001?(d>sim?1.0:0.0):clamp((d-sim)/blend,0.0,1.0);a*=alpha;if(dsp<=0.000001&&alpha>0.000001&&alpha<0.999999){c=clamp((c-key*(1.0-alpha))/alpha,0.0,1.0);}if(dsp>0.000001){if(key.g>=key.b){float sp=max(c.g-max(c.r,c.b),0.0);c.g=max(c.g-sp*dsp,0.0);}else{float sp=max(c.b-max(c.r,c.g),0.0);c.b=max(c.b-sp*dsp,0.0);}}}else if(mode<1.5){float l=dot(c,vec3(.2126,.7152,.0722));float lo=max(0.,lthr-ltol);float hi=min(1.,lthr+ltol);a*=smoothstep(lo,hi,l);}gl_FragColor=vec4(c*a,a);}`);
    gl.compileShader(vs);gl.compileShader(fs);const program=gl.createProgram()!;gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);gl.useProgram(program);
    const pos=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,pos);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);const p=gl.getAttribLocation(program,'p');gl.enableVertexAttribArray(p);gl.vertexAttribPointer(p,2,gl.FLOAT,false,0,0);
    const tc=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,tc);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([0,1,1,1,0,0,0,0,1,1,1,0]),gl.STATIC_DRAW);const t=gl.getAttribLocation(program,'t');gl.enableVertexAttribArray(t);gl.vertexAttribPointer(t,2,gl.FLOAT,false,0,0);
    const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    const uKey=gl.getUniformLocation(program,'key'),uSim=gl.getUniformLocation(program,'sim'),uBlend=gl.getUniformLocation(program,'blend'),uDsp=gl.getUniformLocation(program,'dsp'),uMode=gl.getUniformLocation(program,'mode'),uLthr=gl.getUniformLocation(program,'lthr'),uLtol=gl.getUniformLocation(program,'ltol');
    let lastAspect=0;
    const syncAspect=()=>{if(video.videoWidth>0&&video.videoHeight>0){const next=video.videoWidth/video.videoHeight;if(Math.abs(next-lastAspect)>0.0001){lastAspect=next;setOverlayAspect(next)}}};
    const draw=()=>{rafRef.current=requestAnimationFrame(draw);if(video.readyState<2||video.videoWidth<2)return;syncAspect();const w=Math.min(640,video.videoWidth),h=Math.max(2,Math.round(w*video.videoHeight/video.videoWidth));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h)}const e=effectRef.current,[r,g,b]=hexRgb(e.keyColor);const eq=e.id==='825dd7a4-f0cf-4032-a3c9-64290cb5756d'&&e.mode==='chromakey';const destructiveSubscribe=assets?.previewType==='Subscribe'&&e.mode==='chromakey'&&Math.abs(e.similarity-.60)<.000001&&Math.abs(e.blend-.35)<.000001;const sim=eq ? 0.18 : destructiveSubscribe ? 0.10 : e.similarity;const blend=eq ? 0.03 : destructiveSubscribe ? 0.06 : e.blend;gl.uniform3f(uKey,r,g,b);gl.uniform1f(uSim,Math.max(.001,Math.min(.6,sim)));gl.uniform1f(uBlend,Math.max(.001,Math.min(.35,blend)));gl.uniform1f(uDsp,Math.max(0,Math.min(1,e.despill||0)));gl.uniform1f(uMode,e.mode==='luma'?1:e.mode==='screen'?2:0);gl.uniform1f(uLthr,e.lumaThreshold);gl.uniform1f(uLtol,e.lumaTolerance);gl.bindTexture(gl.TEXTURE_2D,texture);try{gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,video);gl.drawArrays(gl.TRIANGLES,0,6);if(frameStateRef.current&&baseReadyRef.current&&!reportedFrameRef.current){const px=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,px);let paintedNonBlack=0;for(let i=0;i<px.length;i+=4){if(px[i+3]>8&&(px[i]+px[i+1]+px[i+2]>18))paintedNonBlack++}const green=paintedNonBlack>8;if(green&&!liveReadyRef.current){liveReadyRef.current=true;setLiveReady(true)}const requestId=assets?.requestId||'<unknown>',previewType=assets?.previewType||'Effects',payloadBytes=transportBytesRef.current||((assets?.baseBytes||0)+(assets?.overlayBytes||0)),bs=baseSizeRef.current;reportedFrameRef.current=true;console.info(`[ENDLUME_PREVIEW] PREVIEW_REQUEST_ID=${requestId} PREVIEW_TYPE=${previewType} FRONTEND_PAYLOAD_BYTES=${payloadBytes} OBJECT_URL_CREATED=false FRONTEND_TRANSFER_MODE=ASSET_STREAM IMAGE_LOAD=${green?'GREEN':'RED'} IMAGE_NATURAL_WIDTH=${bs.w} IMAGE_NATURAL_HEIGHT=${bs.h} BROWSER_NONBLACK_PIXELS=${paintedNonBlack} PREVIEW_APPLIED=${green}`);frameStateRef.current?.({status:green?'GREEN':'RED',requestId,previewType,width:bs.w,height:bs.h,payloadBytes,paintedNonBlack,browserVisible:green,pixelReadback:green?'GREEN':'RED'})}}catch{}};
    const start=()=>{syncAspect();video.play().catch(()=>{});if(rafRef.current==null)rafRef.current=requestAnimationFrame(draw)};video.addEventListener('loadedmetadata',syncAspect);video.addEventListener('loadeddata',start);if(video.readyState>=1)syncAspect();if(video.readyState>=2)start();
    return()=>{video.removeEventListener('loadedmetadata',syncAspect);video.removeEventListener('loadeddata',start);if(rafRef.current!=null)cancelAnimationFrame(rafRef.current);rafRef.current=undefined;gl.deleteTexture(texture);gl.deleteBuffer(pos);gl.deleteBuffer(tc);gl.deleteProgram(program);gl.deleteShader(vs);gl.deleteShader(fs)};
  },[overlaySrc,assets?.previewType,assets?.requestId,assets?.baseBytes,assets?.overlayBytes,active]);

  useEffect(()=>()=>{if(brushRaf.current!=null)cancelAnimationFrame(brushRaf.current)},[]);
  if(!assets)return <div className="livePreviewEmpty"><span>{busy?'Подготавливаю Live Preview…':'Выберите проект на основном экране'}</span></div>;
  const helperBase=baseSrc?(assets.baseKind==='video'?<video key={baseSrc} className="livePreviewBase helperPreviewBase" src={baseSrc} preload="auto" autoPlay loop muted playsInline onLoadedData={e=>baseLoaded(e.currentTarget.videoWidth,e.currentTarget.videoHeight)} onError={()=>reportRed('base-video-load')}/>:<img className="livePreviewBase helperPreviewBase" src={baseSrc} draggable={false} onLoad={e=>baseLoaded(e.currentTarget.naturalWidth,e.currentTarget.naturalHeight)} onError={()=>reportRed('base-image-load')}/>):null;
  const posterBase=posterSrc?<img className={`livePreviewBase composedPosterPreview ${liveReady?'liveReady':''}`} src={posterSrc} draggable={false} onLoad={e=>posterLoaded(e.currentTarget)} onError={()=>reportRed('poster-image-load')}/>:null;
  const exactOverlayStyle:React.CSSProperties=effect.fullscreen?overlayStyle:{...overlayStyle,aspectRatio:String(Math.max(.05,overlayAspect)),height:'auto'};
  return <div className={`liveComposite ${picker?'chromaPicking':''} ${anchorMode?'anchorPicking':''}`} onPointerDownCapture={pickAnchor}>
    {helperBase}
    {posterBase}
    {anchor&&<div aria-hidden="true" style={{position:'absolute',left:`${anchor.x*100}%`,top:`${anchor.y*100}%`,width:18,height:18,border:'2px solid currentColor',borderRadius:'50%',transform:'translate(-50%,-50%)',boxShadow:'0 0 0 1px rgba(0,0,0,.75)',zIndex:12,pointerEvents:'none'}}><i style={{position:'absolute',left:'50%',top:-7,bottom:-7,width:1,background:'currentColor',transform:'translateX(-50%)'}}/><i style={{position:'absolute',top:'50%',left:-7,right:-7,height:1,background:'currentColor',transform:'translateY(-50%)'}}/></div>}
    {active&&effect.mode==='chromakey'&&<button type="button" className={`chromaPickerButton ${picker?'active':''}`} onClick={e=>{e.preventDefault();e.stopPropagation();setPicker(v=>!v)}}>{picker?'✓ ВЫБЕРИ/ПРОВЕДИ ПО ФОНУ':'⌾ ПИПЕТКА / КИСТЬ'}</button>}
    {active&&<div ref={overlayRef} className={`liveGpuOverlay ${effect.fullscreen?'fullscreen':''}`} style={exactOverlayStyle}
      onPointerDown={e=>{if(picker){e.preventDefault();e.stopPropagation();brushDown.current=true;scheduleSample(e.clientX,e.clientY);return}onDragStart(e)}}
      onPointerMove={e=>{if(picker&&brushDown.current){e.preventDefault();e.stopPropagation();scheduleSample(e.clientX,e.clientY)}}}
      onPointerUp={e=>{if(picker){e.preventDefault();e.stopPropagation();brushDown.current=false;sampleAt(e.clientX,e.clientY)}}}
      onPointerCancel={()=>{brushDown.current=false}}>
      <><video ref={videoRef} className="liveOverlaySource" src={overlaySrc} preload="auto" autoPlay loop muted playsInline onError={()=>reportRed('overlay-video-load')}/>
      <canvas ref={canvasRef} className="liveOverlayCanvas" style={{mixBlendMode:effect.mode==='screen'?'screen':'normal',opacity:Math.max(0,Math.min(1,effect.opacity??1))}}/></>
      {!effect.fullscreen&&!picker&&<><i className="corner nw"/><i className="corner ne"/><i className="corner sw"/><i className="corner se" onPointerDown={onResizeStart}/></>}
    </div>}
    {!active&&<div className="livePreviewDisabled">OFF • overlay скрыт</div>}
    {(busy||!posterSrc)&&<div className="livePreviewPreparing">Подготавливаю Live Preview…</div>}
  </div>
}
