#!/usr/bin/env python3
from __future__ import annotations
import argparse, struct
from pathlib import Path

CONTAINERS={b'moov',b'trak',b'mdia',b'minf',b'stbl',b'edts'}

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

def fullbox_version(p:bytes)->int:
    return p[0]

def mvhd_timescale_duration(box:bytes):
    p=payload(box); v=fullbox_version(p)
    if v==0: return struct.unpack_from('>I',p,12)[0],struct.unpack_from('>I',p,16)[0]
    if v==1: return struct.unpack_from('>I',p,20)[0],struct.unpack_from('>Q',p,24)[0]
    raise ValueError('mvhd version')

def patch_mvhd_duration(box:bytes,duration:int)->bytes:
    p=bytearray(payload(box)); v=p[0]
    if v==0:
        if duration >= 1<<32: raise ValueError('mvhd v0 duration overflow')
        struct.pack_into('>I',p,16,duration)
    elif v==1: struct.pack_into('>Q',p,24,duration)
    else: raise ValueError('mvhd version')
    return make_box(b'mvhd',bytes(p))

def patch_tkhd_duration(box:bytes,duration:int)->bytes:
    p=bytearray(payload(box)); v=p[0]
    if v==0:
        if duration >= 1<<32: raise ValueError('tkhd v0 duration overflow')
        struct.pack_into('>I',p,20,duration)
    elif v==1: struct.pack_into('>Q',p,28,duration)
    else: raise ValueError('tkhd version')
    return make_box(b'tkhd',bytes(p))

def mdhd_timescale_duration(box:bytes):
    p=payload(box); v=p[0]
    if v==0: return struct.unpack_from('>I',p,12)[0],struct.unpack_from('>I',p,16)[0]
    if v==1: return struct.unpack_from('>I',p,20)[0],struct.unpack_from('>Q',p,24)[0]
    raise ValueError('mdhd version')

def child_boxes(box:bytes):
    p=payload(box)
    return [p[o:o+s] for o,s,t,h in read_boxes(p)]

def find_child(box:bytes,typ:bytes):
    for b in child_boxes(box):
        if b[4:8]==typ:return b
    return None

def handler_type(trak:bytes)->bytes|None:
    mdia=find_child(trak,b'mdia')
    if not mdia:return None
    hdlr=find_child(mdia,b'hdlr')
    if not hdlr:return None
    p=payload(hdlr)
    return p[8:12] if len(p)>=12 else None

def video_media_timing(trak:bytes):
    mdia=find_child(trak,b'mdia'); mdhd=find_child(mdia,b'mdhd') if mdia else None
    if not mdhd: raise ValueError('video mdhd missing')
    return mdhd_timescale_duration(mdhd)

def make_repeat_edts(repeats:int,media_duration:int,media_timescale:int,movie_timescale:int)->tuple[bytes,int]:
    seg=round(media_duration*movie_timescale/media_timescale)
    total=seg*repeats
    ep=bytearray(b'\x01\x00\x00\x00'+struct.pack('>I',repeats))
    for _ in range(repeats): ep += struct.pack('>Qqhh',seg,0,1,0)
    return make_box(b'edts',make_box(b'elst',bytes(ep))),total

def rebuild_video_trak(trak:bytes,movie_timescale:int,repeats:int)->tuple[bytes,int]:
    mts,mdur=video_media_timing(trak)
    edts,total=make_repeat_edts(repeats,mdur,mts,movie_timescale)
    out=[]; inserted=False
    for b in child_boxes(trak):
        typ=b[4:8]
        if typ==b'tkhd':
            out.append(patch_tkhd_duration(b,total)); out.append(edts); inserted=True
        elif typ==b'edts':
            continue
        else: out.append(b)
    if not inserted: raise ValueError('video tkhd missing')
    return make_box(b'trak',b''.join(out)),total

def patch_repeat(src:Path,dst:Path,repeats:int):
    data=src.read_bytes(); tops=list(read_boxes(data))
    moovs=[x for x in tops if x[2]==b'moov']; mdats=[x for x in tops if x[2]==b'mdat']
    if len(moovs)!=1 or not mdats: raise ValueError('need one moov and mdat')
    moov_off,moov_size,_,_=moovs[0]
    if moov_off < max(x[0] for x in mdats): raise ValueError('POC requires moov after mdat so chunk offsets stay valid')
    moov=data[moov_off:moov_off+moov_size]
    mvhd=find_child(moov,b'mvhd')
    if not mvhd: raise ValueError('mvhd missing')
    movie_ts,_=mvhd_timescale_duration(mvhd)
    rebuilt=[]; video_total=None
    for b in child_boxes(moov):
        typ=b[4:8]
        if typ==b'trak' and handler_type(b)==b'vide':
            if video_total is not None: raise ValueError('multiple video tracks not supported')
            nb,video_total=rebuild_video_trak(b,movie_ts,repeats); rebuilt.append(nb)
        elif typ==b'mvhd': rebuilt.append(b)  # patched after total is known
        else: rebuilt.append(b)
    if video_total is None: raise ValueError('video track missing')
    rebuilt=[patch_mvhd_duration(b,video_total) if b[4:8]==b'mvhd' else b for b in rebuilt]
    new_moov=make_box(b'moov',b''.join(rebuilt))
    dst.write_bytes(data[:moov_off]+new_moov+data[moov_off+moov_size:])
    print(f'PATCHED repeats={repeats} movie_timescale={movie_ts} duration_ticks={video_total} bytes={dst.stat().st_size}')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('src',type=Path);ap.add_argument('dst',type=Path);ap.add_argument('--repeats',type=int,required=True);a=ap.parse_args()
    if a.repeats<1: raise SystemExit('repeats must be >=1')
    patch_repeat(a.src,a.dst,a.repeats)
if __name__=='__main__':main()
