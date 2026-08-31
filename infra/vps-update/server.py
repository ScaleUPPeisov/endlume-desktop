#!/usr/bin/env python3
import hashlib,hmac,json,mimetypes,os,re,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,quote,unquote,urlparse

ROOT=Path(os.environ.get('ENDLUME_UPDATE_ROOT','/var/lib/endlume-updates')).resolve()
SECRET=os.environ.get('ENDLUME_HMAC_SECRET','').encode()
HOST=os.environ.get('ENDLUME_BIND','127.0.0.1')
PORT=int(os.environ.get('ENDLUME_PORT','8788'))
ALLOWED={'darwin-aarch64','windows-x86_64','windows-aarch64'}
PREFIX='releases/endlume/stable/'

def version_parts(v):
    v=str(v or '').strip().lstrip('v')
    core,*rest=v.split('-',1)
    nums=[int(x) if x.isdigit() else 0 for x in core.split('.')]
    pre=[]
    if rest:
        for x in rest[0].split('.'):
            pre.append(int(x) if x.isdigit() else x)
    return nums,pre

def newer(candidate,current):
    an,ap=version_parts(candidate);bn,bp=version_parts(current)
    n=max(len(an),len(bn),3)
    for i in range(n):
        a=an[i] if i<len(an) else 0;b=bn[i] if i<len(bn) else 0
        if a!=b:return a>b
    if not ap and bp:return True
    if ap and not bp:return False
    for i in range(max(len(ap),len(bp))):
        if i>=len(ap):return False
        if i>=len(bp):return True
        a,b=ap[i],bp[i]
        if a==b:continue
        if isinstance(a,int) and isinstance(b,int):return a>b
        if isinstance(a,int):return False
        if isinstance(b,int):return True
        return str(a)>str(b)
    return False

def sig_for(key,exp):
    return hmac.new(SECRET,f'{key}\n{exp}'.encode(),hashlib.sha256).hexdigest()

def safe_file(key):
    if not key.startswith(PREFIX) or '..' in key.split('/'):
        return None
    p=(ROOT/key).resolve()
    try:p.relative_to(ROOT)
    except ValueError:return None
    return p

class H(BaseHTTPRequestHandler):
    server_version='ENDLUMEUpdate/1.0'
    def log_message(self,fmt,*args):
        print(time.strftime('%Y-%m-%d %H:%M:%S'),self.address_string(),fmt%args,flush=True)
    def j(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode()
        self.send_response(status);self.send_header('content-type','application/json; charset=utf-8');self.send_header('cache-control','no-store');self.send_header('content-length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_HEAD(self):self.handle_req(head=True)
    def do_GET(self):self.handle_req(head=False)
    def handle_req(self,head=False):
        if not SECRET:
            return self.j({'error':'server_secret_missing'},500)
        u=urlparse(self.path)
        if u.path=='/health':return self.j({'ok':True,'service':'endlume-vps-update','storage':'self-hosted-vps'})
        m=re.fullmatch(r'/v1/update/([^/]+)/([^/]+)/([^/]+)',u.path)
        if m:
            target,arch,current=(unquote(x) for x in m.groups())
            platform=f'{target}-{arch}'
            if platform not in ALLOWED:return self.j({'error':'unsupported_platform'},404)
            mf=ROOT/'manifests'/'endlume'/'stable'/f'{platform}.json'
            if not mf.is_file():
                self.send_response(204);self.send_header('cache-control','no-store');self.end_headers();return
            try:data=json.loads(mf.read_text('utf-8'))
            except Exception:return self.j({'error':'invalid_manifest'},500)
            if not all(data.get(k) for k in ('version','object_key','signature')):return self.j({'error':'incomplete_manifest'},500)
            if not newer(data['version'],current):
                self.send_response(204);self.send_header('cache-control','no-store');self.end_headers();return
            exp=int(time.time())+600
            key=data['object_key'];sig=sig_for(key,exp)
            proto=self.headers.get('X-Forwarded-Proto','https')
            host=self.headers.get('Host','')
            dl=f'{proto}://{host}/v1/download?key={quote(key,safe="/")}&exp={exp}&sig={sig}'
            return self.j({'version':data['version'],'notes':data.get('notes',''),'pub_date':data.get('pub_date',''),'url':dl,'signature':data['signature']})
        if u.path=='/v1/download':
            q=parse_qs(u.query);key=(q.get('key') or [''])[0];exp_s=(q.get('exp') or ['0'])[0];sig=(q.get('sig') or [''])[0]
            try:exp=int(exp_s)
            except:exp=0
            if exp<int(time.time()) or not hmac.compare_digest(sig,sig_for(key,exp)):return self.j({'error':'expired_or_invalid'},403)
            p=safe_file(key)
            if not p or not p.is_file():return self.j({'error':'not_found'},404)
            size=p.stat().st_size;ctype=mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
            self.send_response(200);self.send_header('content-type',ctype);self.send_header('content-length',str(size));self.send_header('content-disposition',f'attachment; filename="{p.name}"');self.send_header('cache-control','private, no-store');self.end_headers()
            if not head:
                with p.open('rb') as f:
                    while True:
                        b=f.read(1024*1024)
                        if not b:break
                        self.wfile.write(b)
            return
        self.j({'error':'not_found'},404)

if __name__=='__main__':
    ROOT.mkdir(parents=True,exist_ok=True)
    print(f'ENDLUME update server {HOST}:{PORT} root={ROOT}',flush=True)
    ThreadingHTTPServer((HOST,PORT),H).serve_forever()
