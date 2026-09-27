use std::path::Path;

#[test]
fn external_prefix_cycle_manifest_if_requested(){
  let Ok(seed)=std::env::var("ENDLUME_MANIFEST_SEED") else{return};
  let out=std::env::var("ENDLUME_MANIFEST_OUT").expect("ENDLUME_MANIFEST_OUT missing");
  let prefix=std::env::var("ENDLUME_MANIFEST_PREFIX_FRAMES").expect("prefix missing").parse::<usize>().expect("bad prefix");
  let cycle=std::env::var("ENDLUME_MANIFEST_CYCLE_FRAMES").expect("cycle missing").parse::<usize>().expect("bad cycle");
  let total=std::env::var("ENDLUME_MANIFEST_TOTAL_FRAMES").expect("total missing").parse::<usize>().expect("bad total");
  crate::mp4_manifest::expand_video_prefix_cycle(Path::new(&seed),Path::new(&out),prefix,cycle,total).expect("MP4 manifest expansion failed");
  assert!(Path::new(&out).is_file(),"output missing");
}
