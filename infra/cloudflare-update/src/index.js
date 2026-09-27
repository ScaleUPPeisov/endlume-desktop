const SUPABASE_URL='https://odlseljmogaguyqdlkyv.supabase.co';
const SUPABASE_PUB='sb_publishable_zKjzhQTdTG8f9BfR2X5NVg_zQgjo70f';
const CLIENT_API=SUPABASE_URL+'/functions/v1/endlume-client-api';
const ADMIN_API=SUPABASE_URL+'/functions/v1/endlume-admin-licenses';
const CORS={'access-control-allow-origin':'*','access-control-allow-headers':'authorization,content-type,apikey,x-endlume-session','access-control-allow-methods':'GET,POST,PUT,DELETE,OPTIONS'};
const json=(value,status=200,headers={})=>new Response(JSON.stringify(value),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store',...CORS,...headers}});
async function clientCall(session,body){
  const r=await fetch(CLIENT_API,{method:'POST',headers:{'content-type':'application/json','x-endlume-session':session},body:JSON.stringify(body)});
  const j=await r.json().catch(()=>({ok:false,code:'bad_response'}));return {status:r.status,body:j};
}
async function adminCall(auth,body){
  const r=await fetch(ADMIN_API,{method:'POST',headers:{'content-type':'application/json','authorization':auth,'apikey':SUPABASE_PUB},body:JSON.stringify(body)});
  const j=await r.json().catch(()=>({ok:false,code:'bad_response'}));return {status:r.status,body:j};
}

function platformKey(target,arch){
  const key=`${target}-${arch}`;
  return new Set(['darwin-aarch64','windows-x86_64','windows-aarch64']).has(key)?key:null;
}

function splitVersion(v){
  const clean=String(v||'').trim().replace(/^v/,'');
  const [core,pre='']=clean.split('-',2);
  const nums=core.split('.').map(x=>Number.parseInt(x,10)||0);
  const preParts=pre?pre.split('.').map(x=>/^\d+$/.test(x)?Number(x):x):[];
  return {nums,pre:preParts};
}
function newer(candidate,current){
  const a=splitVersion(candidate),b=splitVersion(current);
  for(let i=0;i<Math.max(a.nums.length,b.nums.length,3);i++){
    const av=a.nums[i]||0,bv=b.nums[i]||0;if(av!==bv)return av>bv;
  }
  if(a.pre.length===0&&b.pre.length>0)return true;
  if(a.pre.length>0&&b.pre.length===0)return false;
  for(let i=0;i<Math.max(a.pre.length,b.pre.length);i++){
    if(i>=a.pre.length)return false;if(i>=b.pre.length)return true;
    const av=a.pre[i],bv=b.pre[i];if(av===bv)continue;
    if(typeof av==='number'&&typeof bv==='number')return av>bv;
    if(typeof av==='number'&&typeof bv!=='number')return false;
    if(typeof av!=='number'&&typeof bv==='number')return true;
    return String(av)>String(bv);
  }
  return false;
}

function validSha256(value){return typeof value==='string'&&/^[0-9a-fA-F]{64}$/.test(value.trim())}

function b64url(bytes){
  let s='';for(const b of new Uint8Array(bytes))s+=String.fromCharCode(b);
  return btoa(s).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
async function hmac(secret,message){
  const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  return b64url(await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(message)));
}
async function equalSig(a,b){
  if(a.length!==b.length)return false;let x=0;for(let i=0;i<a.length;i++)x|=a.charCodeAt(i)^b.charCodeAt(i);return x===0;
}


async function authorizeRenderUpload(request,renderId){
  const session=request.headers.get('x-endlume-session')||'';
  if(!session)return {error:json({error:'session_missing'},401)};
  const a=await clientCall(session,{action:'artifact_authorize',render_id:renderId});
  if(a.status<200||a.status>=300||!a.body?.ok)return {error:json({error:a.body?.code||'upload_not_allowed'},a.status||403)};
  return {session,artifact:a.body};
}
async function renderUploadStart(request,env,url){
  const renderId=url.searchParams.get('render_id')||'';
  if(!renderId)return json({error:'render_id'},400);
  const a=await authorizeRenderUpload(request,renderId);if(a.error)return a.error;
  const key=a.artifact.objectKey;
  const upload=await env.UPDATES.createMultipartUpload(key,{httpMetadata:{contentType:'video/mp4'}});
  return json({ok:true,renderId,objectKey:key,uploadId:upload.uploadId,partSize:25*1024*1024,expiresAt:a.artifact.expiresAt});
}
async function renderUploadPart(request,env,url){
  const renderId=url.searchParams.get('render_id')||'';
  const uploadId=url.searchParams.get('upload_id')||'';
  const part=Number(url.searchParams.get('part')||0);
  if(!renderId||!uploadId||!Number.isInteger(part)||part<1||part>10000)return json({error:'upload_part_args'},400);
  const a=await authorizeRenderUpload(request,renderId);if(a.error)return a.error;
  if(!request.body)return json({error:'empty_part'},400);
  const upload=env.UPDATES.resumeMultipartUpload(a.artifact.objectKey,uploadId);
  const p=await upload.uploadPart(part,request.body);
  return json({ok:true,partNumber:p.partNumber,etag:p.etag});
}
async function renderUploadComplete(request,env,url){
  const renderId=url.searchParams.get('render_id')||'';
  const uploadId=url.searchParams.get('upload_id')||'';
  if(!renderId||!uploadId)return json({error:'upload_complete_args'},400);
  const a=await authorizeRenderUpload(request,renderId);if(a.error)return a.error;
  let body;try{body=await request.json()}catch{return json({error:'bad_json'},400)}
  const parts=Array.isArray(body?.parts)?body.parts:[];
  if(!parts.length)return json({error:'parts_missing'},400);
  const upload=env.UPDATES.resumeMultipartUpload(a.artifact.objectKey,uploadId);
  await upload.complete(parts.map(x=>({partNumber:Number(x.partNumber),etag:String(x.etag)})));
  const fin=await clientCall(a.session,{action:'artifact_uploaded',render_id:renderId,size_bytes:Number(body?.sizeBytes)||0,sha256:String(body?.sha256||''),filename:String(body?.filename||'')});
  if(fin.status<200||fin.status>=300||!fin.body?.ok)return json({error:fin.body?.code||'artifact_finalize_failed'},fin.status||500);
  return json({ok:true,renderId,status:'ready'});
}
async function renderUploadAbort(request,env,url){
  const renderId=url.searchParams.get('render_id')||'';
  const uploadId=url.searchParams.get('upload_id')||'';
  if(!renderId||!uploadId)return json({error:'upload_abort_args'},400);
  const a=await authorizeRenderUpload(request,renderId);if(a.error)return a.error;
  try{await env.UPDATES.resumeMultipartUpload(a.artifact.objectKey,uploadId).abort()}catch{}
  return json({ok:true});
}
async function renderDownloadTicket(request,env,url){
  const renderId=url.searchParams.get('render_id')||'';
  const auth=request.headers.get('authorization')||'';
  if(!renderId||!auth)return json({error:'auth_or_render_missing'},401);
  const a=await adminCall(auth,{action:'artifact_download',render_id:renderId});
  if(a.status<200||a.status>=300||!a.body?.ok)return json({error:a.body?.code||'download_not_allowed'},a.status||403);
  const exp=Math.floor(Date.now()/1000)+600;
  const message='render:'+a.body.objectKey+'\n'+exp;
  const sig=await hmac(env.DOWNLOAD_HMAC_SECRET,message);
  const dl=new URL('/v1/render-download',url.origin);
  dl.searchParams.set('key',a.body.objectKey);dl.searchParams.set('exp',String(exp));dl.searchParams.set('sig',sig);dl.searchParams.set('filename',a.body.filename||'ENDLUME-render.mp4');
  return json({ok:true,url:dl.toString(),expiresAt:exp,sizeBytes:a.body.sizeBytes||null});
}
async function renderDownload(env,url){
  const key=url.searchParams.get('key')||'';
  const exp=Number(url.searchParams.get('exp')||0);
  const sig=url.searchParams.get('sig')||'';
  const filename=(url.searchParams.get('filename')||'ENDLUME-render.mp4').replace(/[\r\n"]/g,'_');
  if(!key.startsWith('renders/endlume/')||!Number.isFinite(exp)||exp<Math.floor(Date.now()/1000))return json({error:'expired_or_invalid'},403);
  const expected=await hmac(env.DOWNLOAD_HMAC_SECRET,'render:'+key+'\n'+exp);
  if(!(await equalSig(sig,expected)))return json({error:'bad_signature'},403);
  const object=await env.UPDATES.get(key);if(!object)return json({error:'not_found'},404);
  const headers=new Headers(CORS);object.writeHttpMetadata(headers);headers.set('etag',object.httpEtag);headers.set('cache-control','private, max-age=0, no-store');headers.set('content-disposition','attachment; filename="'+filename+'"');
  return new Response(object.body,{status:200,headers});
}
async function renderDelete(request,env,url){
  const renderId=url.searchParams.get('render_id')||'';
  const auth=request.headers.get('authorization')||'';
  if(!renderId||!auth)return json({error:'auth_or_render_missing'},401);
  const a=await adminCall(auth,{action:'artifact_download',render_id:renderId});
  if(a.status<200||a.status>=300||!a.body?.ok)return json({error:a.body?.code||'delete_not_allowed'},a.status||403);
  await env.UPDATES.delete(a.body.objectKey);
  await adminCall(auth,{action:'artifact_deleted',render_id:renderId});
  return json({ok:true});
}
export default {
  async fetch(request,env){
    const url=new URL(request.url);
    if(request.method==='OPTIONS')return new Response(null,{status:204,headers:CORS});
    if(url.pathname==='/health')return json({ok:true,service:'endlume-update-api',storage:'private-r2',renderArtifacts:'multipart-r2'});
    if(url.pathname==='/v1/render-upload/start'&&request.method==='POST')return renderUploadStart(request,env,url);
    if(url.pathname==='/v1/render-upload/part'&&request.method==='PUT')return renderUploadPart(request,env,url);
    if(url.pathname==='/v1/render-upload/complete'&&request.method==='POST')return renderUploadComplete(request,env,url);
    if(url.pathname==='/v1/render-upload/abort'&&request.method==='POST')return renderUploadAbort(request,env,url);
    if(url.pathname==='/v1/render-download-ticket'&&request.method==='GET')return renderDownloadTicket(request,env,url);
    if(url.pathname==='/v1/render-download'&&request.method==='GET')return renderDownload(env,url);
    if(url.pathname==='/v1/render-delete'&&request.method==='DELETE')return renderDelete(request,env,url);
    if(request.method!=='GET')return json({error:'method_not_allowed'},405);

    const update=url.pathname.match(/^\/v1\/update\/([^/]+)\/([^/]+)\/([^/]+)$/);
    if(update){
      const [,target,arch,currentEncoded]=update;
      const platform=platformKey(target,arch);
      if(!platform)return json({error:'unsupported_platform'},404);
      const current=decodeURIComponent(currentEncoded);
      const manifestKey=`manifests/endlume/stable/${platform}.json`;
      const object=await env.UPDATES.get(manifestKey);
      if(!object)return new Response(null,{status:204,headers:{'cache-control':'no-store'}});
      let manifest;try{manifest=JSON.parse(await object.text())}catch{return json({error:'invalid_manifest'},500)}
      if(!manifest.version||!manifest.object_key||!manifest.signature)return json({error:'incomplete_manifest'},500);
      if(platform.startsWith('windows-')&&!validSha256(manifest.sha256))return json({error:'windows_manifest_missing_sha256'},500);
      if(!newer(manifest.version,current))return new Response(null,{status:204,headers:{'cache-control':'no-store'}});
      const exp=Math.floor(Date.now()/1000)+600;
      const message=`${manifest.object_key}\n${exp}`;
      const sig=await hmac(env.DOWNLOAD_HMAC_SECRET,message);
      const download=new URL('/v1/download',url.origin);
      download.searchParams.set('key',manifest.object_key);
      download.searchParams.set('exp',String(exp));
      download.searchParams.set('sig',sig);
      const response={
        version:manifest.version,
        notes:manifest.notes||'',
        pub_date:manifest.pub_date||new Date().toISOString(),
        url:download.toString(),
        signature:manifest.signature
      };
      if(validSha256(manifest.sha256))response.sha256=manifest.sha256.trim().toLowerCase();
      return json(response);
    }

    if(url.pathname==='/v1/download'){
      const key=url.searchParams.get('key')||'';
      const exp=Number(url.searchParams.get('exp')||0);
      const sig=url.searchParams.get('sig')||'';
      if(!key.startsWith('releases/endlume/stable/')||!Number.isFinite(exp)||exp<Math.floor(Date.now()/1000))return json({error:'expired_or_invalid'},403);
      const expected=await hmac(env.DOWNLOAD_HMAC_SECRET,`${key}\n${exp}`);
      if(!(await equalSig(sig,expected)))return json({error:'bad_signature'},403);
      const object=await env.UPDATES.get(key);
      if(!object)return json({error:'not_found'},404);
      const headers=new Headers();
      object.writeHttpMetadata(headers);headers.set('etag',object.httpEtag);headers.set('cache-control','private, max-age=0, no-store');headers.set('content-disposition','attachment');
      return new Response(object.body,{status:200,headers});
    }

    return json({error:'not_found'},404);
  }
};
