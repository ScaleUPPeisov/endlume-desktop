const json=(value,status=200,headers={})=>new Response(JSON.stringify(value),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store',...headers}});

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

export default {
  async fetch(request,env){
    const url=new URL(request.url);
    if(request.method!=='GET')return json({error:'method_not_allowed'},405);
    if(url.pathname==='/health')return json({ok:true,service:'endlume-update-api',storage:'private-r2'});

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
      if(!newer(manifest.version,current))return new Response(null,{status:204,headers:{'cache-control':'no-store'}});
      const exp=Math.floor(Date.now()/1000)+600;
      const message=`${manifest.object_key}\n${exp}`;
      const sig=await hmac(env.DOWNLOAD_HMAC_SECRET,message);
      const download=new URL('/v1/download',url.origin);
      download.searchParams.set('key',manifest.object_key);
      download.searchParams.set('exp',String(exp));
      download.searchParams.set('sig',sig);
      return json({
        version:manifest.version,
        notes:manifest.notes||'',
        pub_date:manifest.pub_date||new Date().toISOString(),
        url:download.toString(),
        signature:manifest.signature
      });
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
