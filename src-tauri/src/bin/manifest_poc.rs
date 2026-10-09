#[cfg(feature="acceptance-harness")]
fn main(){
  use std::{env,path::Path};
  let args=env::args().collect::<Vec<_>>();
  if args.len()!=5{
    eprintln!("usage: manifest_poc <seed.mp4> <prefix_frames> <cycle_frames> <total_frames>");
    std::process::exit(2);
  }
  let seed=Path::new(&args[1]);
  let prefix=args[2].parse::<usize>().expect("prefix_frames");
  let cycle=args[3].parse::<usize>().expect("cycle_frames");
  let total=args[4].parse::<usize>().expect("total_frames");
  if let Err(e)=endlume_lib::mp4_manifest::expand_video_prefix_cycle(seed,seed,prefix,cycle,total){
    eprintln!("manifest_poc: {e}");
    std::process::exit(1);
  }
}

#[cfg(not(feature="acceptance-harness"))]
fn main(){
  eprintln!("manifest_poc requires --features acceptance-harness");
  std::process::exit(2);
}
