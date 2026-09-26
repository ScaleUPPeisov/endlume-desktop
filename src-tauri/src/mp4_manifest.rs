use std::{collections::HashSet,fs,io::{Read,Seek,SeekFrom,Write},path::Path};

#[derive(Clone,Copy,Debug)]
struct Atom{off:usize,size:usize,typ:[u8;4],hdr:usize}

fn be32(b:&[u8],o:usize)->Result<u32,String>{if o+4>b.len(){return Err("MP4: u32 overflow".into())}Ok(u32::from_be_bytes(b[o..o+4].try_into().unwrap()))}
fn be64(b:&[u8],o:usize)->Result<u64,String>{if o+8>b.len(){return Err("MP4: u64 overflow".into())}Ok(u64::from_be_bytes(b[o..o+8].try_into().unwrap()))}
fn put32(v:&mut[u8],o:usize,x:u32)->Result<(),String>{if o+4>v.len(){return Err("MP4: write u32 overflow".into())}v[o..o+4].copy_from_slice(&x.to_be_bytes());Ok(())}
fn put64(v:&mut[u8],o:usize,x:u64)->Result<(),String>{if o+8>v.len(){return Err("MP4: write u64 overflow".into())}v[o..o+8].copy_from_slice(&x.to_be_bytes());Ok(())}
fn atom_type(a:&[u8])->[u8;4]{a.get(4..8).and_then(|x|x.try_into().ok()).unwrap_or(*b"????")}

fn atoms(buf:&[u8])->Result<Vec<Atom>,String>{
  let mut out=Vec::new();let mut p=0usize;
  while p+8<=buf.len(){
    let n=be32(buf,p)?;let typ: [u8;4]=buf[p+4..p+8].try_into().unwrap();let (size,hdr)=if n==1{(be64(buf,p+8)? as usize,16)}else if n==0{(buf.len()-p,8)}else{(n as usize,8)};
    if size<hdr||p.checked_add(size).filter(|e|*e<=buf.len()).is_none(){return Err(format!("MP4: invalid {:?} atom size {} at {}",String::from_utf8_lossy(&typ),size,p))}
    out.push(Atom{off:p,size,typ,hdr});p+=size;
  }
  if p!=buf.len(){return Err(format!("MP4: {} trailing atom bytes",buf.len()-p))}Ok(out)
}

fn file_atoms(path:&Path)->Result<(Vec<Atom>,usize),String>{
  let mut f=fs::File::open(path).map_err(|e|format!("MP4 manifest: open {}: {e}",path.display()))?;
  let len=f.metadata().map_err(|e|format!("MP4 manifest: metadata {}: {e}",path.display()))?.len() as usize;
  let mut out=Vec::new();let mut p=0usize;
  while p+8<=len{
    f.seek(SeekFrom::Start(p as u64)).map_err(|e|format!("MP4 manifest: seek atom {}: {e}",path.display()))?;
    let mut head=[0u8;16];f.read_exact(&mut head[..8]).map_err(|e|format!("MP4 manifest: read atom header {}: {e}",path.display()))?;
    let n=u32::from_be_bytes(head[..4].try_into().unwrap());let typ:[u8;4]=head[4..8].try_into().unwrap();
    let (size,hdr)=if n==1{
      f.read_exact(&mut head[8..16]).map_err(|e|format!("MP4 manifest: read large atom header {}: {e}",path.display()))?;
      (u64::from_be_bytes(head[8..16].try_into().unwrap()) as usize,16)
    }else if n==0{(len-p,8)}else{(n as usize,8)};
    if size<hdr||p.checked_add(size).filter(|e|*e<=len).is_none(){return Err(format!("MP4: invalid {:?} atom size {} at {}",String::from_utf8_lossy(&typ),size,p))}
    out.push(Atom{off:p,size,typ,hdr});p+=size;
  }
  if p!=len{return Err(format!("MP4: {} trailing atom bytes",len-p))}
  Ok((out,len))
}

fn read_file_range(path:&Path,off:usize,size:usize)->Result<Vec<u8>,String>{
  let mut f=fs::File::open(path).map_err(|e|format!("MP4 manifest: open {}: {e}",path.display()))?;
  f.seek(SeekFrom::Start(off as u64)).map_err(|e|format!("MP4 manifest: seek {}: {e}",path.display()))?;
  let mut out=vec![0u8;size];f.read_exact(&mut out).map_err(|e|format!("MP4 manifest: read range {}: {e}",path.display()))?;Ok(out)
}

fn payload(a:&[u8])->Result<&[u8],String>{let xs=atoms(a)?;if xs.len()!=1||xs[0].off!=0||xs[0].size!=a.len(){return Err("MP4: expected one atom".into())}Ok(&a[xs[0].hdr..])}
fn make_atom(typ:[u8;4],p:&[u8])->Result<Vec<u8>,String>{let size=8usize.checked_add(p.len()).ok_or("MP4 atom too large")?;if size>u32::MAX as usize{return Err("MP4 atom >4GB unsupported".into())}let mut v=Vec::with_capacity(size);v.extend_from_slice(&(size as u32).to_be_bytes());v.extend_from_slice(&typ);v.extend_from_slice(p);Ok(v)}
fn children(a:&[u8])->Result<Vec<Vec<u8>>,String>{let p=payload(a)?;Ok(atoms(p)?.into_iter().map(|x|p[x.off..x.off+x.size].to_vec()).collect())}
fn find_child(a:&[u8],t:[u8;4])->Result<Option<Vec<u8>>,String>{for b in children(a)?{if atom_type(&b)==t{return Ok(Some(b))}}Ok(None)}

fn handler_type(trak:&[u8])->Result<Option<[u8;4]>,String>{
  let Some(mdia)=find_child(trak,*b"mdia")? else{return Ok(None)};let Some(hdlr)=find_child(&mdia,*b"hdlr")? else{return Ok(None)};let p=payload(&hdlr)?;if p.len()<12{return Ok(None)}Ok(Some(p[8..12].try_into().unwrap()))
}
fn timing(a:&[u8],kind:[u8;4])->Result<(u32,u64),String>{let p=payload(a)?;if p.len()<4{return Err("MP4 timing atom short".into())}match (kind,p[0]){(k,0) if k==*b"mvhd"||k==*b"mdhd"=>Ok((be32(p,12)?,be32(p,16)? as u64)),(k,1) if k==*b"mvhd"||k==*b"mdhd"=>Ok((be32(p,20)?,be64(p,24)?)),_=>Err(format!("MP4: unsupported timing {:?} v{}",String::from_utf8_lossy(&kind),p[0]))}}
fn promote_duration_v0(p:&[u8],kind:[u8;4],duration:u64)->Result<Vec<u8>,String>{
  if p.len()<24||p.first().copied()!=Some(0){return Err(format!("MP4: cannot promote {:?} timing atom",String::from_utf8_lossy(&kind)))}
  let mut q=Vec::with_capacity(p.len()+12);q.extend_from_slice(&p[..4]);q[0]=1;
  match kind{
    k if k==*b"mvhd"||k==*b"mdhd"=>{
      q.extend_from_slice(&(be32(p,4)? as u64).to_be_bytes());
      q.extend_from_slice(&(be32(p,8)? as u64).to_be_bytes());
      q.extend_from_slice(&p[12..16]);
      q.extend_from_slice(&duration.to_be_bytes());
      q.extend_from_slice(&p[20..]);
    },
    k if k==*b"tkhd"=>{
      q.extend_from_slice(&(be32(p,4)? as u64).to_be_bytes());
      q.extend_from_slice(&(be32(p,8)? as u64).to_be_bytes());
      q.extend_from_slice(&p[12..20]);
      q.extend_from_slice(&duration.to_be_bytes());
      q.extend_from_slice(&p[24..]);
    },
    _=>return Err(format!("MP4: unsupported duration promotion {:?}",String::from_utf8_lossy(&kind)))
  }
  Ok(q)
}
fn patch_duration(a:&[u8],kind:[u8;4],duration:u64)->Result<Vec<u8>,String>{
  let mut p=payload(a)?.to_vec();if p.is_empty(){return Err("MP4 duration atom short".into())}
  if p[0]==0&&duration>u32::MAX as u64{p=promote_duration_v0(&p,kind,duration)?;return make_atom(kind,&p)}
  let off=match (kind,p[0]){(k,0) if k==*b"mvhd"||k==*b"mdhd"=>16,(k,1) if k==*b"mvhd"||k==*b"mdhd"=>24,(k,0) if k==*b"tkhd"=>20,(k,1) if k==*b"tkhd"=>28,_=>return Err(format!("MP4: unsupported duration {:?} v{}",String::from_utf8_lossy(&kind),p[0]))};
  if p[0]==0{put32(&mut p,off,duration as u32)?}else{put64(&mut p,off,duration)?}make_atom(kind,&p)
}

fn stsz_sizes(a:&[u8])->Result<Vec<u32>,String>{let p=payload(a)?;let fixed=be32(p,4)?;let n=be32(p,8)? as usize;if fixed!=0{return Ok(vec![fixed;n])}if p.len()!=12+n*4{return Err("MP4: malformed stsz".into())}(0..n).map(|i|be32(p,12+i*4)).collect()}
fn stco_offsets(a:&[u8])->Result<Vec<u64>,String>{let p=payload(a)?;let n=be32(p,4)? as usize;let wide=atom_type(a)==*b"co64";let step=if wide{8}else{4};if p.len()!=8+n*step{return Err("MP4: malformed stco/co64".into())}(0..n).map(|i|if wide{be64(p,8+i*8)}else{be32(p,8+i*4).map(|x|x as u64)}).collect()}
fn stsc_entries(a:&[u8])->Result<Vec<(u32,u32,u32)>,String>{let p=payload(a)?;let n=be32(p,4)? as usize;if p.len()!=8+n*12{return Err("MP4: malformed stsc".into())}let mut v=Vec::with_capacity(n);for i in 0..n{v.push((be32(p,8+i*12)?,be32(p,12+i*12)?,be32(p,16+i*12)?))}Ok(v)}
fn expand_stts(a:&[u8],n_samples:usize)->Result<Vec<u32>,String>{let p=payload(a)?;let n=be32(p,4)? as usize;if p.len()!=8+n*8{return Err("MP4: malformed stts".into())}let mut out=Vec::with_capacity(n_samples);for i in 0..n{let c=be32(p,8+i*8)? as usize;let d=be32(p,12+i*8)?;out.extend(std::iter::repeat(d).take(c))}if out.len()!=n_samples{return Err(format!("MP4: stts samples {} != stsz {}",out.len(),n_samples))}Ok(out)}
fn expand_ctts(a:&[u8],n_samples:usize)->Result<(u8,Vec<i64>),String>{let p=payload(a)?;let version=*p.first().ok_or("MP4: ctts short")?;let n=be32(p,4)? as usize;if p.len()!=8+n*8{return Err("MP4: malformed ctts".into())}let mut out=Vec::with_capacity(n_samples);for i in 0..n{let c=be32(p,8+i*8)? as usize;let raw=be32(p,12+i*8)?;let v=if version==1{(raw as i32) as i64}else{raw as i64};out.extend(std::iter::repeat(v).take(c))}if out.len()!=n_samples{return Err("MP4: ctts sample count mismatch".into())}Ok((version,out))}
fn stss_set(a:&[u8])->Result<HashSet<u32>,String>{let p=payload(a)?;let n=be32(p,4)? as usize;if p.len()!=8+n*4{return Err("MP4: malformed stss".into())}let mut s=HashSet::with_capacity(n);for i in 0..n{s.insert(be32(p,8+i*4)?);}Ok(s)}

fn sample_layout(stbl:&[u8])->Result<(Vec<u32>,Vec<u64>,Vec<u32>),String>{
  let cs=children(stbl)?;let stsz=cs.iter().find(|x|atom_type(x)==*b"stsz").ok_or("MP4: video stsz missing")?;let sizes=stsz_sizes(stsz)?;let stco=cs.iter().find(|x|matches!(atom_type(x),t if t==*b"stco"||t==*b"co64")).ok_or("MP4: video chunk offsets missing")?;let chunks=stco_offsets(stco)?;let stsc=cs.iter().find(|x|atom_type(x)==*b"stsc").ok_or("MP4: video stsc missing")?;let map=stsc_entries(stsc)?;if map.is_empty(){return Err("MP4: empty stsc".into())}
  let mut offsets=Vec::with_capacity(sizes.len());let mut descs=Vec::with_capacity(sizes.len());let mut sample=0usize;let mut entry=0usize;
  for (ci,start) in chunks.iter().enumerate(){let chunk=(ci+1) as u32;while entry+1<map.len()&&map[entry+1].0<=chunk{entry+=1}let (_,spc,desc)=map[entry];let mut off=*start;for _ in 0..spc{if sample>=sizes.len(){return Err("MP4: stsc exceeds sample count".into())}offsets.push(off);descs.push(desc);off=off.checked_add(sizes[sample] as u64).ok_or("MP4: sample offset overflow")?;sample+=1}}
  if sample!=sizes.len(){return Err(format!("MP4: mapped {} of {} samples",sample,sizes.len()))}Ok((sizes,offsets,descs))
}

fn compress_u32(vals:&[u32])->Vec<(u32,u32)>{let mut out=Vec::new();for &v in vals{if let Some(last)=out.last_mut(){let x:&mut(u32,u32)=last;if x.1==v{x.0+=1;continue}}out.push((1,v))}out}
fn compress_i64(vals:&[i64])->Vec<(u32,i64)>{let mut out=Vec::new();for &v in vals{if let Some(last)=out.last_mut(){let x:&mut(u32,i64)=last;if x.1==v{x.0+=1;continue}}out.push((1,v))}out}
fn make_stts(head:&[u8],vals:&[u32])->Result<Vec<u8>,String>{let runs=compress_u32(vals);let mut p=head[..4].to_vec();p.extend_from_slice(&(runs.len() as u32).to_be_bytes());for(c,d)in runs{p.extend_from_slice(&c.to_be_bytes());p.extend_from_slice(&d.to_be_bytes())}make_atom(*b"stts",&p)}
fn make_ctts(head:&[u8],version:u8,vals:&[i64])->Result<Vec<u8>,String>{let runs=compress_i64(vals);let mut p=head[..4].to_vec();p[0]=version;p.extend_from_slice(&(runs.len() as u32).to_be_bytes());for(c,v)in runs{p.extend_from_slice(&c.to_be_bytes());if version==1{let x=i32::try_from(v).map_err(|_|"MP4: ctts i32 overflow")?;p.extend_from_slice(&x.to_be_bytes())}else{let x=u32::try_from(v).map_err(|_|"MP4: ctts u32 overflow")?;p.extend_from_slice(&x.to_be_bytes())}}make_atom(*b"ctts",&p)}
fn make_stsz(head:&[u8],sizes:&[u32])->Result<Vec<u8>,String>{let mut p=head[..4].to_vec();p.extend_from_slice(&0u32.to_be_bytes());p.extend_from_slice(&(sizes.len() as u32).to_be_bytes());for x in sizes{p.extend_from_slice(&x.to_be_bytes())}make_atom(*b"stsz",&p)}
fn make_offsets(head:&[u8],offs:&[u64],wide:bool)->Result<Vec<u8>,String>{let mut p=head[..4].to_vec();p.extend_from_slice(&(offs.len() as u32).to_be_bytes());if wide{for x in offs{p.extend_from_slice(&x.to_be_bytes())}make_atom(*b"co64",&p)}else{for x in offs{let y=u32::try_from(*x).map_err(|_|"MP4: stco overflow")?;p.extend_from_slice(&y.to_be_bytes())}make_atom(*b"stco",&p)}}
fn make_stsc(head:&[u8],descs:&[u32])->Result<Vec<u8>,String>{if descs.is_empty(){return Err("MP4: empty output samples".into())}let mut entries=vec![(1u32,1u32,descs[0])];for(i,&d)in descs.iter().enumerate().skip(1){if d!=descs[i-1]{entries.push(((i+1) as u32,1,d))}}let mut p=head[..4].to_vec();p.extend_from_slice(&(entries.len() as u32).to_be_bytes());for(a,b,c)in entries{p.extend_from_slice(&a.to_be_bytes());p.extend_from_slice(&b.to_be_bytes());p.extend_from_slice(&c.to_be_bytes())}make_atom(*b"stsc",&p)}
fn make_stss(head:&[u8],selected:&[usize],sync:&HashSet<u32>)->Result<Vec<u8>,String>{let vals=selected.iter().enumerate().filter_map(|(i,&s)|sync.contains(&((s+1)as u32)).then_some((i+1)as u32)).collect::<Vec<_>>();let mut p=head[..4].to_vec();p.extend_from_slice(&(vals.len() as u32).to_be_bytes());for x in vals{p.extend_from_slice(&x.to_be_bytes())}make_atom(*b"stss",&p)}
fn make_sdtp(head:&[u8],bytes:&[u8],selected:&[usize])->Result<Vec<u8>,String>{let mut p=head[..4].to_vec();for&i in selected{p.push(*bytes.get(i).ok_or("MP4: sdtp index overflow")?)}make_atom(*b"sdtp",&p)}

fn remap_sbgp(a:&[u8],selected:&[usize],n_samples:usize)->Result<Vec<u8>,String>{
  let p=payload(a)?;if p.len()<12{return Err("MP4: sbgp short".into())}let version=p[0];let extra=if version==1{4}else{0};let head_len=12+extra;if p.len()<head_len{return Err("MP4: sbgp header short".into())}let entries=be32(p,8+extra)? as usize;if p.len()!=head_len+entries*8{return Err("MP4: malformed sbgp".into())}let mut groups=Vec::with_capacity(n_samples);for i in 0..entries{let o=head_len+i*8;let c=be32(p,o)? as usize;let g=be32(p,o+4)?;groups.extend(std::iter::repeat(g).take(c))}if groups.len()!=n_samples{return Err("MP4: sbgp sample count mismatch".into())}let chosen=selected.iter().map(|&i|groups[i]).collect::<Vec<_>>();let runs=compress_u32(&chosen);let mut q=p[..8+extra].to_vec();q.extend_from_slice(&(runs.len()as u32).to_be_bytes());for(c,g)in runs{q.extend_from_slice(&c.to_be_bytes());q.extend_from_slice(&g.to_be_bytes())}make_atom(*b"sbgp",&q)
}

fn rebuild_stbl(stbl:&[u8],selected:&[usize])->Result<(Vec<u8>,u64,bool),String>{
  let cs=children(stbl)?;let stsz=cs.iter().find(|x|atom_type(x)==*b"stsz").ok_or("MP4: stsz missing")?;let n_samples=stsz_sizes(stsz)?.len();if selected.iter().any(|&i|i>=n_samples){return Err("MP4: selected sample outside video pool".into())}
  let (sizes,offs,descs)=sample_layout(stbl)?;let stts=cs.iter().find(|x|atom_type(x)==*b"stts").ok_or("MP4: stts missing")?;let deltas=expand_stts(stts,n_samples)?;let ctts=cs.iter().find(|x|atom_type(x)==*b"ctts").map(|x|expand_ctts(x,n_samples)).transpose()?;let stss=cs.iter().find(|x|atom_type(x)==*b"stss").map(|x|stss_set(x)).transpose()?;let sdtp=cs.iter().find(|x|atom_type(x)==*b"sdtp").map(|x|payload(x).map(|p|p[4..].to_vec())).transpose()?;
  let chosen_sizes=selected.iter().map(|&i|sizes[i]).collect::<Vec<_>>();let chosen_offs=selected.iter().map(|&i|offs[i]).collect::<Vec<_>>();let chosen_descs=selected.iter().map(|&i|descs[i]).collect::<Vec<_>>();let chosen_deltas=selected.iter().map(|&i|deltas[i]).collect::<Vec<_>>();let duration=chosen_deltas.iter().map(|&x|x as u64).sum::<u64>();
  let use_co64=chosen_offs.iter().any(|&x|x>u32::MAX as u64)||cs.iter().any(|x|atom_type(x)==*b"co64");
  let mut out=Vec::new();for b in cs{let typ=atom_type(&b);match typ{
    t if t==*b"stts"=>out.push(make_stts(payload(&b)?,&chosen_deltas)?),
    t if t==*b"ctts"=>{let(ver,all)=ctts.as_ref().ok_or("MP4: ctts vanished")?;let v=selected.iter().map(|&i|all[i]).collect::<Vec<_>>();out.push(make_ctts(payload(&b)?,*ver,&v)?)},
    t if t==*b"stsz"=>out.push(make_stsz(payload(&b)?,&chosen_sizes)?),
    t if t==*b"stsc"=>out.push(make_stsc(payload(&b)?,&chosen_descs)?),
    t if t==*b"stco"||t==*b"co64"=>{if (t==*b"co64")==(use_co64){out.push(make_offsets(payload(&b)?,&chosen_offs,use_co64)?)}else if t==*b"stco"&&use_co64{out.push(make_offsets(payload(&b)?,&chosen_offs,true)?)}},
    t if t==*b"stss"=>out.push(make_stss(payload(&b)?,selected,stss.as_ref().ok_or("MP4: stss vanished")?)?),
    t if t==*b"sdtp"=>out.push(make_sdtp(payload(&b)?,sdtp.as_ref().ok_or("MP4: sdtp vanished")?,selected)?),
    t if t==*b"sbgp"=>out.push(remap_sbgp(&b,selected,n_samples)?),
    t if matches!(t, [b's',b'u',b'b',b's']|[b's',b'a',b'i',b'z']|[b's',b'a',b'i',b'o']|[b's',b'e',b'n',b'c'])=>return Err(format!("MP4: unsupported sample-indexed atom {}",String::from_utf8_lossy(&t))),
    _=>out.push(b)
  }}
  let sync_ok=match stss{None=>true,Some(ref s)=>s.contains(&1)};Ok((make_atom(*b"stbl",&out.concat())?,duration,sync_ok))
}
fn rebuild_minf(minf:&[u8],selected:&[usize])->Result<(Vec<u8>,u64,bool),String>{let mut out=Vec::new();let mut dur=None;let mut sync=false;for b in children(minf)?{if atom_type(&b)==*b"stbl"{let(x,d,s)=rebuild_stbl(&b,selected)?;out.push(x);dur=Some(d);sync=s}else{out.push(b)}}Ok((make_atom(*b"minf",&out.concat())?,dur.ok_or("MP4: minf/stbl missing")?,sync))}
fn rebuild_mdia(mdia:&[u8],selected:&[usize])->Result<(Vec<u8>,u32,u64,bool),String>{let mdhd=find_child(mdia,*b"mdhd")?.ok_or("MP4: mdhd missing")?;let(ts,_)=timing(&mdhd,*b"mdhd")?;let mut out=Vec::new();let mut dur=None;let mut sync=false;for b in children(mdia)?{if atom_type(&b)==*b"minf"{let(x,d,s)=rebuild_minf(&b,selected)?;out.push(x);dur=Some(d);sync=s}else{out.push(b)}}let d=dur.ok_or("MP4: video duration missing")?;for b in out.iter_mut(){if atom_type(b)==*b"mdhd"{*b=patch_duration(b,*b"mdhd",d)?}}Ok((make_atom(*b"mdia",&out.concat())?,ts,d,sync))}
fn rebuild_video_trak(trak:&[u8],selected:&[usize],movie_ts:u32)->Result<(Vec<u8>,u64,bool),String>{let mut out=Vec::new();let mut media=None;let mut sync=false;for b in children(trak)?{match atom_type(&b){t if t==*b"mdia"=>{let(x,ts,d,s)=rebuild_mdia(&b,selected)?;media=Some((ts,d));sync=s;out.push(x)},t if t==*b"edts"=>{},_=>out.push(b)}}let(ts,d)=media.ok_or("MP4: video mdia missing")?;let movie_dur=((d as u128*movie_ts as u128+ts as u128/2)/ts as u128)as u64;for b in out.iter_mut(){if atom_type(b)==*b"tkhd"{*b=patch_duration(b,*b"tkhd",movie_dur)?}}Ok((make_atom(*b"trak",&out.concat())?,movie_dur,sync))}

fn remap_video_samples_impl(seed:&Path,out:&Path,selected:&[usize])->Result<(),String>{
  if selected.is_empty(){return Err("MP4 manifest: empty selected sample map".into())}
  let (top,file_len)=file_atoms(seed)?;
  let moovs=top.iter().filter(|x|x.typ==*b"moov").copied().collect::<Vec<_>>();
  if moovs.len()!=1{return Err("MP4 manifest: expected one moov".into())}
  let moov_ref=moovs[0];
  let last_mdat=top.iter().filter(|x|x.typ==*b"mdat").map(|x|x.off+x.size).max().ok_or("MP4 manifest: mdat missing")?;
  if moov_ref.off<last_mdat{return Err("MP4 manifest: moov must be after mdat (do not use faststart for seed)".into())}

  // 8.64 Turbo: read only the metadata atom. The old implementation read the
  // entire multi-hundred-MB seed into RAM just to rewrite moov.
  let moov=read_file_range(seed,moov_ref.off,moov_ref.size)?;
  let mvhd=find_child(&moov,*b"mvhd")?.ok_or("MP4 manifest: mvhd missing")?;let(movie_ts,old_movie_dur)=timing(&mvhd,*b"mvhd")?;
  let mut kids=Vec::new();let mut video_dur=None;let mut video_seen=0usize;
  for b in children(&moov)?{
    if atom_type(&b)==*b"trak"&&handler_type(&b)?==Some(*b"vide"){
      video_seen+=1;if video_seen>1{return Err("MP4 manifest: multiple video tracks unsupported".into())}
      let stbl=find_child(&find_child(&find_child(&b,*b"mdia")?.ok_or("MP4: mdia")?,*b"minf")?.ok_or("MP4: minf")?,*b"stbl")?.ok_or("MP4: stbl")?;
      let count=stsz_sizes(&find_child(&stbl,*b"stsz")?.ok_or("MP4: stsz")?)?.len();
      if selected.iter().any(|&i|i>=count){return Err(format!("MP4 manifest: selected video sample outside pool of {count} samples"))}
      let(x,d,sync0)=rebuild_video_trak(&b,selected,movie_ts)?;
      if !sync0{return Err("MP4 manifest: source sample 1 is not sync/keyframe".into())}
      video_dur=Some(d);kids.push(x)
    }else{kids.push(b)}
  }
  let vd=video_dur.ok_or("MP4 manifest: video track missing")?;let new_movie_dur=old_movie_dur.max(vd);
  for b in kids.iter_mut(){if atom_type(b)==*b"mvhd"{*b=patch_duration(b,*b"mvhd",new_movie_dur)?}}
  let new_moov=make_atom(*b"moov",&kids.concat())?;
  let tail_off=moov_ref.off+moov_ref.size;
  let tail_len=file_len.saturating_sub(tail_off);

  if seed==out{
    // mdat remains untouched on disk. Only the old moov (and rare small tail)
    // is replaced, removing an O(final_file_size) memory read/copy.
    let tail=if tail_len>0{read_file_range(seed,tail_off,tail_len)?}else{Vec::new()};
    let mut f=fs::OpenOptions::new().read(true).write(true).open(seed).map_err(|e|format!("MP4 manifest: open in-place {}: {e}",seed.display()))?;
    f.set_len(moov_ref.off as u64).map_err(|e|format!("MP4 manifest: truncate in-place {}: {e}",seed.display()))?;
    f.seek(SeekFrom::Start(moov_ref.off as u64)).map_err(|e|format!("MP4 manifest: seek in-place {}: {e}",seed.display()))?;
    f.write_all(&new_moov).map_err(|e|format!("MP4 manifest: write moov in-place {}: {e}",seed.display()))?;
    if !tail.is_empty(){f.write_all(&tail).map_err(|e|format!("MP4 manifest: write tail in-place {}: {e}",seed.display()))?;}
    f.sync_all().map_err(|e|format!("MP4 manifest: sync in-place {}: {e}",seed.display()))?;
    Ok(())
  }else{
    // External output path also streams the payload instead of materializing
    // the full MP4 in a Vec.
    let mut src=fs::File::open(seed).map_err(|e|format!("MP4 manifest: open {}: {e}",seed.display()))?;
    let mut dst=fs::File::create(out).map_err(|e|format!("MP4 manifest: create {}: {e}",out.display()))?;
    {
      let mut prefix=(&mut src).take(moov_ref.off as u64);
      std::io::copy(&mut prefix,&mut dst).map_err(|e|format!("MP4 manifest: copy prefix {}: {e}",out.display()))?;
    }
    dst.write_all(&new_moov).map_err(|e|format!("MP4 manifest: write moov {}: {e}",out.display()))?;
    src.seek(SeekFrom::Start(tail_off as u64)).map_err(|e|format!("MP4 manifest: seek tail {}: {e}",seed.display()))?;
    std::io::copy(&mut src,&mut dst).map_err(|e|format!("MP4 manifest: copy tail {}: {e}",out.display()))?;
    dst.sync_all().map_err(|e|format!("MP4 manifest: sync {}: {e}",out.display()))?;
    Ok(())
  }
}

pub fn remap_video_samples(seed:&Path,out:&Path,selected:&[usize])->Result<(),String>{remap_video_samples_impl(seed,out,selected)}

pub fn expand_video_prefix_cycle(seed:&Path,out:&Path,prefix_frames:usize,cycle_frames:usize,total_frames:usize)->Result<(),String>{
  if cycle_frames==0||total_frames<prefix_frames{return Err("MP4 manifest: invalid prefix/cycle/total frame counts".into())}
  let needed=prefix_frames.checked_add(cycle_frames).ok_or("MP4 manifest: frame overflow")?;let mut selected=Vec::with_capacity(total_frames);selected.extend(0..prefix_frames);for i in 0..(total_frames-prefix_frames){selected.push(prefix_frames+(i%cycle_frames))}
  if selected.iter().any(|&i|i>=needed){return Err("MP4 manifest: generated sample map outside prefix/cycle pool".into())}
  remap_video_samples_impl(seed,out,&selected)
}

#[cfg(test)]
mod tests{
  use super::*;
  #[test]fn prefix_cycle_index_math(){let p=3usize;let c=4usize;let t=13usize;let mut s=Vec::new();s.extend(0..p);for i in 0..t-p{s.push(p+i%c)}assert_eq!(s,vec![0,1,2,3,4,5,6,3,4,5,6,3,4]);}
  #[test]fn promotes_v0_duration_atoms_to_v1(){
    let long=u32::MAX as u64+12345;
    let mut mvhd=vec![0u8;100];mvhd[12..16].copy_from_slice(&1_000_000u32.to_be_bytes());let mvhd=make_atom(*b"mvhd",&mvhd).unwrap();let mvhd=patch_duration(&mvhd,*b"mvhd",long).unwrap();let p=payload(&mvhd).unwrap();assert_eq!(p[0],1);assert_eq!(be32(p,20).unwrap(),1_000_000);assert_eq!(be64(p,24).unwrap(),long);
    let mut mdhd=vec![0u8;24];mdhd[12..16].copy_from_slice(&60_000u32.to_be_bytes());let mdhd=make_atom(*b"mdhd",&mdhd).unwrap();let mdhd=patch_duration(&mdhd,*b"mdhd",long).unwrap();let p=payload(&mdhd).unwrap();assert_eq!(p[0],1);assert_eq!(be32(p,20).unwrap(),60_000);assert_eq!(be64(p,24).unwrap(),long);
    let mut tkhd=vec![0u8;84];tkhd[12..16].copy_from_slice(&7u32.to_be_bytes());let tkhd=make_atom(*b"tkhd",&tkhd).unwrap();let tkhd=patch_duration(&tkhd,*b"tkhd",long).unwrap();let p=payload(&tkhd).unwrap();assert_eq!(p[0],1);assert_eq!(be32(p,20).unwrap(),7);assert_eq!(be64(p,28).unwrap(),long);
  }
  #[test]fn multistill_sample_schedule_math(){
    let media=3usize;let physical_frames=2usize;let logical_frames=6usize;let total_frames=24usize;
    let mut cycle=Vec::new();
    for image in 0..media{let start=image*physical_frames;for i in 0..logical_frames{cycle.push(start+(i%physical_frames));}}
    assert_eq!(cycle,vec![0,1,0,1,0,1,2,3,2,3,2,3,4,5,4,5,4,5]);
    let selected=(0..total_frames).map(|i|cycle[i%cycle.len()]).collect::<Vec<_>>();
    assert_eq!(selected.len(),24);assert_eq!(&selected[..18],cycle.as_slice());assert_eq!(&selected[18..],&cycle[..6]);
  }
  #[test]fn external_multistill_manifest_if_requested(){
    let Ok(seed)=std::env::var("ENDLUME_MULTI_MANIFEST_SEED") else{return};
    let out=std::env::var("ENDLUME_MULTI_MANIFEST_OUT").expect("ENDLUME_MULTI_MANIFEST_OUT");
    let media=std::env::var("ENDLUME_MULTI_MEDIA_COUNT").unwrap().parse::<usize>().unwrap();
    let physical=std::env::var("ENDLUME_MULTI_PHYSICAL_FRAMES").unwrap().parse::<usize>().unwrap();
    let logical=std::env::var("ENDLUME_MULTI_LOGICAL_FRAMES").unwrap().parse::<usize>().unwrap();
    let total=std::env::var("ENDLUME_MULTI_TOTAL_FRAMES").unwrap().parse::<usize>().unwrap();
    assert!(media>=1&&physical>0&&logical>=physical&&total>=logical*media);
    let mut cycle=Vec::with_capacity(logical*media);
    for image in 0..media{let start=image*physical;for i in 0..logical{cycle.push(start+(i%physical));}}
    let selected=(0..total).map(|i|cycle[i%cycle.len()]).collect::<Vec<_>>();
    remap_video_samples(Path::new(&seed),Path::new(&out),&selected).unwrap();
  }
}
