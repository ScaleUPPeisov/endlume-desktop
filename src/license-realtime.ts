import type { LicenseStatus } from './types';

const PROJECT_REF='odlseljmogaguyqdlkyv';
const PUBLISHABLE_KEY='sb_publishable_zKjzhQTdTG8f9BfR2X5NVg_zQgjo70f';

export function watchManagedLicenseRealtime(status:LicenseStatus,onRefresh:()=>void){
  if(!/Windows/i.test(navigator.userAgent)||!status.valid||!status.realtimeTopic)return ()=>{};
  let closed=false;
  let socket:WebSocket|undefined;
  let reconnect:number|undefined;
  let heartbeat:number|undefined;
  let refreshTimer:number|undefined;
  let refs=1;
  let retry=1000;
  const topic=`realtime:${status.realtimeTopic}`;
  const url=`wss://${PROJECT_REF}.supabase.co/realtime/v1/websocket?apikey=${encodeURIComponent(PUBLISHABLE_KEY)}&vsn=1.0.0`;

  const scheduleRefresh=()=>{
    if(refreshTimer!==undefined)window.clearTimeout(refreshTimer);
    refreshTimer=window.setTimeout(()=>{refreshTimer=undefined;if(!closed)onRefresh()},120);
  };
  const sendHeartbeat=()=>{
    if(socket?.readyState!==WebSocket.OPEN)return;
    const ref=String(refs++);
    socket.send(JSON.stringify({topic:'phoenix',event:'heartbeat',payload:{},ref}));
  };
  const connect=()=>{
    if(closed)return;
    socket=new WebSocket(url);
    socket.onopen=()=>{
      retry=1000;
      const ref=String(refs++);
      socket?.send(JSON.stringify({topic,event:'phx_join',payload:{config:{broadcast:{ack:false,self:false},presence:{enabled:false},private:false}},ref,join_ref:ref}));
      if(heartbeat!==undefined)window.clearInterval(heartbeat);
      heartbeat=window.setInterval(sendHeartbeat,25_000);
    };
    socket.onmessage=(event)=>{
      try{
        const msg=JSON.parse(String(event.data||''));
        if(msg?.topic!==topic)return;
        const broadcast=msg?.event==='broadcast'?msg?.payload:null;
        const eventName=broadcast?.event||msg?.event;
        if(eventName==='license_changed'||eventName==='device_changed')scheduleRefresh();
      }catch{}
    };
    socket.onclose=()=>{
      if(heartbeat!==undefined){window.clearInterval(heartbeat);heartbeat=undefined;}
      if(closed)return;
      reconnect=window.setTimeout(connect,retry);
      retry=Math.min(retry*2,15_000);
    };
    socket.onerror=()=>socket?.close();
  };
  connect();
  return()=>{
    closed=true;
    if(reconnect!==undefined)window.clearTimeout(reconnect);
    if(heartbeat!==undefined)window.clearInterval(heartbeat);
    if(refreshTimer!==undefined)window.clearTimeout(refreshTimer);
    if(socket&&socket.readyState<2)socket.close(1000,'ENDLUME shutdown');
  };
}
