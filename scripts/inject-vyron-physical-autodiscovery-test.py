#!/usr/bin/env python3
from pathlib import Path

p = Path('vyron-product/src-tauri/src/inventory_watch.rs')
s = p.read_text(encoding='utf-8')
marker = 'physical_external_render_event_is_observed_1015'
if marker in s:
    print('VYRON_PHYSICAL_AUTODISCOVERY_TEST=ALREADY_PRESENT')
    raise SystemExit(0)

insert = r'''

    #[test]
    fn physical_external_render_event_is_observed_1015() {
        use std::{fs, sync::mpsc, time::{Duration, Instant}};
        let root_raw=std::env::var("VYRON_PHYSICAL_ROOT_FOR_TEST").expect("physical root env");
        let render_root=PathBuf::from(root_raw).join("Render");
        let mut channels=fs::read_dir(&render_root).expect("Render root")
            .filter_map(Result::ok).map(|e|e.path()).filter(|p|p.is_dir()).collect::<Vec<_>>();
        channels.sort();
        let root=channels.into_iter().next().expect("at least one channel render dir").canonicalize().expect("canonical channel dir");
        let (tx,rx)=mpsc::channel();
        let mut watcher=RecommendedWatcher::new(move |r:notify::Result<Event>|{let _=tx.send(r);},Config::default()).expect("watcher");
        watcher.watch(&root,RecursiveMode::Recursive).expect("watch physical render channel");
        std::thread::sleep(Duration::from_millis(700));
        let target=root.join(format!(".ENDLUME-VYRON-AUTODISCOVERY-QA-{}.mov",std::process::id()));
        let _=fs::remove_file(&target);
        fs::write(&target,b"qa-video-event").expect("create physical render fixture");
        let deadline=Instant::now()+Duration::from_secs(10);
        let mut found=false;
        while Instant::now()<deadline && !found {
            match rx.recv_timeout(Duration::from_millis(500)) {
                Ok(Ok(event)) if event.paths.iter().any(|p|p==&root||p.starts_with(&root))=>found=true,
                Ok(_)=>{},
                Err(mpsc::RecvTimeoutError::Timeout)=>{},
                Err(e)=>panic!("watch channel failed: {e}"),
            }
        }
        drop(watcher);
        let _=fs::remove_file(&target);
        assert!(found,"VYRON native watcher did not observe actual external Render channel");
    }
'''
pos = s.rfind('\n}')
if pos < 0:
    raise SystemExit('inventory_watch tests module closing brace not found')
p.write_text(s[:pos] + insert + s[pos:], encoding='utf-8')
print('VYRON_PHYSICAL_AUTODISCOVERY_TEST=INJECTED')
