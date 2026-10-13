#!/usr/bin/env python3
from pathlib import Path

p = Path('vyron-product/src-tauri/src/inventory_watch.rs')
s = p.read_text(encoding='utf-8')
marker = 'physical_external_read_does_not_retrigger_inventory_6111'
if marker in s:
    print('VYRON_6111_PHYSICAL_LOOP_TEST=ALREADY_PRESENT')
    raise SystemExit(0)

insert = r'''

    #[test]
    fn physical_external_read_does_not_retrigger_inventory_6111() {
        use std::{fs, io::Read, sync::mpsc, time::{Duration, Instant}};
        let root_raw=std::env::var("VYRON_PHYSICAL_ROOT_FOR_TEST").expect("physical root env");
        let render_root=PathBuf::from(root_raw).join("Render");
        let mut channels=fs::read_dir(&render_root).expect("Render root")
            .filter_map(Result::ok).map(|e|e.path()).filter(|p|p.is_dir()).collect::<Vec<_>>();
        channels.sort();
        let root=channels.into_iter().next().expect("at least one channel render dir").canonicalize().expect("canonical channel dir");

        let (tx,rx)=mpsc::channel();
        let mut watcher=RecommendedWatcher::new(
            move |r:notify::Result<Event>|{let _=tx.send(r);},
            Config::default(),
        ).expect("watcher");
        watcher.watch(&root,RecursiveMode::Recursive).expect("watch physical render channel");
        std::thread::sleep(Duration::from_millis(900));

        // Prove the physical watcher is alive using one isolated fixture mutation.
        let target=root.join(format!(".VYRON-6111-INVENTORY-LOOP-QA-{}.mov",std::process::id()));
        let _=fs::remove_file(&target);
        fs::write(&target,b"vyron-6111-physical-inventory-loop-fixture").expect("create fixture");
        let create_deadline=Instant::now()+Duration::from_secs(10);
        let mut actionable_create=false;
        while Instant::now()<create_deadline && !actionable_create {
            match rx.recv_timeout(Duration::from_millis(400)) {
                Ok(Ok(event)) if event.paths.iter().any(|p|p==&root||p.starts_with(&root)) => {
                    if event_can_change_inventory(&event) { actionable_create=true; }
                }
                Ok(_)=>{},
                Err(mpsc::RecvTimeoutError::Timeout)=>{},
                Err(e)=>panic!("watch channel failed during create: {e}"),
            }
        }
        assert!(actionable_create,"physical watcher did not observe actionable create/write event");

        // Drain create/write noise before the read-only phase.
        let drain_deadline=Instant::now()+Duration::from_millis(1200);
        while Instant::now()<drain_deadline {
            match rx.recv_timeout(Duration::from_millis(120)) {
                Ok(_)=>{},
                Err(mpsc::RecvTimeoutError::Timeout)=>break,
                Err(e)=>panic!("watch channel failed while draining: {e}"),
            }
        }

        // Model VYRON inventory fingerprinting: open/read/stat the same physical
        // file repeatedly. Those reads must never feed an actionable inventory
        // event back into the scan loop.
        for _ in 0..40 {
            let _=fs::metadata(&target).expect("fixture metadata");
            let mut file=fs::File::open(&target).expect("open fixture for read");
            let mut buf=Vec::new();
            file.read_to_end(&mut buf).expect("read fixture");
            assert!(!buf.is_empty());
        }

        let observe_deadline=Instant::now()+Duration::from_secs(4);
        let mut raw_events=0usize;
        let mut accepted_events=Vec::<String>::new();
        while Instant::now()<observe_deadline {
            match rx.recv_timeout(Duration::from_millis(250)) {
                Ok(Ok(event)) if event.paths.iter().any(|p|p==&root||p.starts_with(&root)) => {
                    raw_events+=1;
                    if event_can_change_inventory(&event) {
                        accepted_events.push(format!("{:?} {:?}",event.kind,event.paths));
                    }
                }
                Ok(_)=>{},
                Err(mpsc::RecvTimeoutError::Timeout)=>{},
                Err(e)=>panic!("watch channel failed during read phase: {e}"),
            }
        }

        drop(watcher);
        let _=fs::remove_file(&target);
        println!("VYRON_6111_PHYSICAL_READ_RAW_EVENTS={raw_events}");
        println!("VYRON_6111_PHYSICAL_READ_ACCEPTED_EVENTS={}",accepted_events.len());
        assert!(accepted_events.is_empty(),"read-only physical access retriggered inventory: {accepted_events:?}");
    }
'''
pos = s.rfind('\n}')
if pos < 0:
    raise SystemExit('inventory_watch tests module closing brace not found')
p.write_text(s[:pos] + insert + s[pos:], encoding='utf-8')
print('VYRON_6111_PHYSICAL_LOOP_TEST=INJECTED')
