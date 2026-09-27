#!/usr/bin/env python3
from __future__ import annotations
import argparse, struct
from pathlib import Path


def read_boxes(buf:bytes,start:int=0,end:int|None=None):
    end=len(buf) if end is None else end
    p=start
    while p+8<=end:
        size=struct.unpack_from('>I',buf,p)[0]; typ=buf[p+4:p+8]; hdr=8
        if size==1:
            if p+16>end: raise ValueError('truncated extended box')
            size=struct.unpack_from('>Q',buf,p+8)[0]; hdr=16
        elif size==0:
            size=end-p
        if size<hdr or p+size>end: raise ValueError(f'bad box {typ!r} size={size} at {p}')
        yield p,size,typ,hdr
        p+=size
    if p!=end: raise ValueError(f'trailing bytes {end-p}')


def make_box(typ:bytes,payload:bytes)->bytes:
    size=8+len(payload)
    if size < (1<<32): return struct.pack('>I4s',size,typ)+payload
    return struct.pack('>I4sQ',1,typ,size+8)+payload


def payload(box:bytes)->bytes:
    size=struct.unpack_from('>I',box,0)[0]
    return box[16:] if size==1 else box[8:]


def child_boxes(box:bytes):
    p=payload(box)
    return [p[o:o+s] for o,s,t,h in read_boxes(p)]


def find_child(box:bytes,typ:bytes):
    for b in child_boxes(box):
        if b[4:8]==typ:return b
    return None


def handler_type(trak:bytes)->bytes|None:
    mdia=find_child(trak,b'mdia')
    hdlr=find_child(mdia,b'hdlr') if mdia else None
    p=payload(hdlr) if hdlr else b''
    return p[8:12] if len(p)>=12 else None


def timing(box:bytes,kind:str)->tuple[int,int]:
    p=payload(box); v=p[0]
    if kind=='mvhd':
        return (struct.unpack_from('>I',p,12)[0],struct.unpack_from('>I',p,16)[0]) if v==0 else (struct.unpack_from('>I',p,20)[0],struct.unpack_from('>Q',p,24)[0])
    if kind=='mdhd':
        return (struct.unpack_from('>I',p,12)[0],struct.unpack_from('>I',p,16)[0]) if v==0 else (struct.unpack_from('>I',p,20)[0],struct.unpack_from('>Q',p,24)[0])
    raise ValueError(kind)


def patch_duration(box:bytes,kind:str,duration:int)->bytes:
    p=bytearray(payload(box)); v=p[0]
    if kind=='mvhd': off=16 if v==0 else 24
    elif kind=='mdhd': off=16 if v==0 else 24
    elif kind=='tkhd': off=20 if v==0 else 28
    else: raise ValueError(kind)
    if v==0:
        if duration >= 1<<32: raise ValueError(f'{kind} v0 duration overflow')
        struct.pack_into('>I',p,off,duration)
    elif v==1: struct.pack_into('>Q',p,off,duration)
    else: raise ValueError(f'{kind} version {v}')
    return make_box(kind.encode(),bytes(p))


def parse_count_entries(box:bytes,entry_fmt:str)->tuple[bytes,list[tuple]]:
    p=payload(box)
    head=p[:4]
    count=struct.unpack_from('>I',p,4)[0]
    sz=struct.calcsize(entry_fmt)
    if len(p)!=8+count*sz: raise ValueError(f'{box[4:8]!r} malformed')
    return head,[struct.unpack_from(entry_fmt,p,8+i*sz) for i in range(count)]


def make_count_entries(typ:bytes,head:bytes,entries:list[tuple],entry_fmt:str)->bytes:
    return make_box(typ,head+struct.pack('>I',len(entries))+b''.join(struct.pack(entry_fmt,*e) for e in entries))


def repeat_run_table(box:bytes,repeats:int,signed_second:bool=False)->bytes:
    typ=box[4:8]; p=payload(box); head=p[:4]
    count=struct.unpack_from('>I',p,4)[0]
    fmt='>Ii' if signed_second else '>II'
    sz=8
    entries=[struct.unpack_from(fmt,p,8+i*sz) for i in range(count)]
    seq=entries*repeats
    merged=[]
    for n,v in seq:
        if merged and merged[-1][1]==v: merged[-1]=(merged[-1][0]+n,v)
        else: merged.append((n,v))
    return make_count_entries(typ,head,merged,fmt)


def repeat_stsz(box:bytes,repeats:int)->tuple[bytes,int]:
    p=payload(box); head=p[:4]; sample_size,sample_count=struct.unpack_from('>II',p,4)
    total=sample_count*repeats
    if sample_size:
        return make_box(b'stsz',head+struct.pack('>II',sample_size,total)),sample_count
    vals=list(struct.unpack_from('>'+('I'*sample_count),p,12)) if sample_count else []
    vals=vals*repeats
    body=head+struct.pack('>II',0,total)+(struct.pack('>'+('I'*len(vals)),*vals) if vals else b'')
    return make_box(b'stsz',body),sample_count


def repeat_stss(box:bytes,repeats:int,sample_count:int)->bytes:
    p=payload(box); head=p[:4]; n=struct.unpack_from('>I',p,4)[0]
    vals=list(struct.unpack_from('>'+('I'*n),p,8)) if n else []
    out=[]
    for r in range(repeats): out.extend(v+r*sample_count for v in vals)
    return make_box(b'stss',head+struct.pack('>I',len(out))+(struct.pack('>'+('I'*len(out)),*out) if out else b''))


def repeat_offsets(box:bytes,repeats:int)->tuple[bytes,int]:
    typ=box[4:8]; p=payload(box); head=p[:4]; n=struct.unpack_from('>I',p,4)[0]
    fmt='Q' if typ==b'co64' else 'I'; sz=8 if typ==b'co64' else 4
    vals=[struct.unpack_from('>'+fmt,p,8+i*sz)[0] for i in range(n)]
    out=vals*repeats
    return make_box(typ,head+struct.pack('>I',len(out))+b''.join(struct.pack('>'+fmt,v) for v in out)),n


def repeat_stsc(box:bytes,repeats:int,chunks:int)->bytes:
    p=payload(box); head=p[:4]; n=struct.unpack_from('>I',p,4)[0]
    entries=[struct.unpack_from('>III',p,8+i*12) for i in range(n)]
    out=[]
    for r in range(repeats):
        base=r*chunks
        for first,spc,desc in entries: out.append((first+base,spc,desc))
    # Merge a repeated boundary if the mapping stays identical.
    compact=[]
    for e in out:
        if compact and compact[-1][1:]==e[1:]:
            continue
        compact.append(e)
    return make_count_entries(b'stsc',head,compact,'>III')


def repeat_sdtp(box:bytes,repeats:int)->bytes:
    p=payload(box)
    return make_box(b'sdtp',p[:4]+p[4:]*repeats)


def rebuild_stbl(stbl:bytes,repeats:int)->tuple[bytes,int,int]:
    children=child_boxes(stbl)
    stsz=next((b for b in children if b[4:8]==b'stsz'),None)
    offs=next((b for b in children if b[4:8] in (b'stco',b'co64')),None)
    if stsz is None or offs is None: raise ValueError('stsz/stco missing')
    new_stsz,sample_count=repeat_stsz(stsz,repeats)
    new_offs,chunks=repeat_offsets(offs,repeats)
    out=[]
    for b in children:
        typ=b[4:8]
        if typ==b'stsz': out.append(new_stsz)
        elif typ in (b'stco',b'co64'): out.append(new_offs)
        elif typ==b'stsc': out.append(repeat_stsc(b,repeats,chunks))
        elif typ==b'stts': out.append(repeat_run_table(b,repeats,False))
        elif typ==b'ctts': out.append(repeat_run_table(b,repeats,payload(b)[0]==1))
        elif typ==b'stss': out.append(repeat_stss(b,repeats,sample_count))
        elif typ==b'sdtp': out.append(repeat_sdtp(b,repeats))
        else: out.append(b)
    return make_box(b'stbl',b''.join(out)),sample_count,chunks


def rebuild_minf(minf:bytes,repeats:int)->tuple[bytes,int,int]:
    out=[]; sc=ch=0
    for b in child_boxes(minf):
        if b[4:8]==b'stbl': nb,sc,ch=rebuild_stbl(b,repeats);out.append(nb)
        else: out.append(b)
    if not sc: raise ValueError('video sample table missing')
    return make_box(b'minf',b''.join(out)),sc,ch


def rebuild_mdia(mdia:bytes,repeats:int)->tuple[bytes,int,int,int]:
    mdhd=find_child(mdia,b'mdhd')
    if not mdhd: raise ValueError('mdhd missing')
    ts,dur=timing(mdhd,'mdhd')
    out=[]; sc=ch=0
    for b in child_boxes(mdia):
        if b[4:8]==b'mdhd': out.append(patch_duration(b,'mdhd',dur*repeats))
        elif b[4:8]==b'minf': nb,sc,ch=rebuild_minf(b,repeats);out.append(nb)
        else: out.append(b)
    return make_box(b'mdia',b''.join(out)),ts,dur*repeats,sc


def rebuild_video_trak(trak:bytes,repeats:int,movie_ts:int)->tuple[bytes,int,int]:
    out=[]; media_ts=media_dur=sc=0
    for b in child_boxes(trak):
        if b[4:8]==b'mdia': nb,media_ts,media_dur,sc=rebuild_mdia(b,repeats);out.append(nb)
        elif b[4:8]==b'edts':
            # Sample timing is now real; old edit lists would double-apply timing.
            continue
        else: out.append(b)
    movie_dur=round(media_dur*movie_ts/media_ts)
    out=[patch_duration(b,'tkhd',movie_dur) if b[4:8]==b'tkhd' else b for b in out]
    return make_box(b'trak',b''.join(out)),movie_dur,sc


def patch_repeat(src:Path,dst:Path,repeats:int):
    data=src.read_bytes(); tops=list(read_boxes(data))
    moovs=[x for x in tops if x[2]==b'moov']; mdats=[x for x in tops if x[2]==b'mdat']
    if len(moovs)!=1 or not mdats: raise ValueError('need one moov and mdat')
    moov_off,moov_size,_,_=moovs[0]
    if moov_off < max(x[0] for x in mdats): raise ValueError('POC requires moov after mdat')
    moov=data[moov_off:moov_off+moov_size]
    mvhd=find_child(moov,b'mvhd')
    if not mvhd: raise ValueError('mvhd missing')
    movie_ts,old_movie_dur=timing(mvhd,'mvhd')
    rebuilt=[]; video_movie_dur=None; samples=0
    for b in child_boxes(moov):
        if b[4:8]==b'trak' and handler_type(b)==b'vide':
            if video_movie_dur is not None: raise ValueError('multiple video tracks unsupported')
            nb,video_movie_dur,samples=rebuild_video_trak(b,repeats,movie_ts);rebuilt.append(nb)
        else: rebuilt.append(b)
    if video_movie_dur is None: raise ValueError('video track missing')
    target=max(old_movie_dur,video_movie_dur)
    rebuilt=[patch_duration(b,'mvhd',target) if b[4:8]==b'mvhd' else b for b in rebuilt]
    new_moov=make_box(b'moov',b''.join(rebuilt))
    dst.write_bytes(data[:moov_off]+new_moov+data[moov_off+moov_size:])
    print(f'PATCHED_SAMPLE_TABLE repeats={repeats} samples_per_cycle={samples} duration_ticks={video_movie_dur} bytes={dst.stat().st_size}')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('src',type=Path);ap.add_argument('dst',type=Path);ap.add_argument('--repeats',type=int,required=True);a=ap.parse_args()
    if a.repeats<1: raise SystemExit('repeats must be >=1')
    patch_repeat(a.src,a.dst,a.repeats)

if __name__=='__main__':main()
