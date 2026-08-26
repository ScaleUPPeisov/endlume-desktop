from pathlib import Path
import re

p=Path('scripts/apply-hybrid-fidelity-8-28.py')
text=p.read_text(encoding='utf-8')

# 8.29 fidelity budget: 4K static background + sparse overlay stays visually
# near-lossless while landing near ~1 GB/2h together with 320 kbps source audio.
text=text.replace('"-crf","14"','"-crf","22"')
text=text.replace('CRF14','CRF22')
text=text.replace('crf 14','crf 22')

# The old 8.28 patcher relied on one exact minified render_sub_segment line.
# Previous release patches can legitimately reformat/replace that line, so use
# a function-scoped regex fallback instead of aborting installation.
old_block='''if old in text:text=text.replace(old,new,1)\nelif new not in text:raise SystemExit('8.28: Subscribe encoder marker missing')'''
new_block='''if new not in text:\n    if old in text:\n        text=text.replace(old,new,1)\n    else:\n        fn_pat=r'async fn render_sub_segment\\(.*?\\n}\\n\\nasync fn assemble_visual'\n        m=re.search(fn_pat,text,flags=re.S)\n        if not m: raise SystemExit('8.29: render_sub_segment function missing')\n        fn=m.group(0)\n        desired='if smart_repeat_project(job){args.extend(hybrid_fidelity_args(&job.settings));}else{args.extend(encoder_args(encoder,&job.settings,false));}'\n        if desired not in fn:\n            candidates=[\n                r'args\\.extend\\(encoder_args\\(encoder,&job\\.settings,false\\)\\);',\n                r'args\\.extend\\(if smart_repeat_project\\(job\\)\\{fidelity_video_args\\(encoder,&job\\.settings\\)\\}else\\{encoder_args\\(encoder,&job\\.settings,false\\)\\}\\);'\n            ]\n            fn2=fn; changed=0\n            for pat in candidates:\n                fn2,n=re.subn(pat,desired,fn2,count=1)\n                if n:\n                    changed=1\n                    break\n            if not changed: raise SystemExit('8.29: Subscribe encoder insertion point missing')\n            text=text[:m.start()]+fn2+text[m.end():]'''
if old_block not in text:
    raise SystemExit('8.29: old Subscribe patcher block missing')
text=text.replace(old_block,new_block,1)

# Output marker fallback: only the `let out=` assignment matters, not the exact
# surrounding minified function layout.
old="elif new_out not in text:raise SystemExit('8.28: render output marker missing')"
new="""elif new_out not in text:\n    simple='let out=unique_output(&out_dir,&job.project.name);'\n    repl='let out=if smart_repeat_project(job){unique_output_ext(&out_dir,&job.project.name,\\\"mov\\\")}else{unique_output(&out_dir,&job.project.name)};'\n    if simple not in text: raise SystemExit('8.29: render output assignment missing')\n    text=text.replace(simple,repl,1)"""
if old in text:text=text.replace(old,new,1)

# Encoder selector fallback: the only forbidden path is q95 VideoToolbox for the
# smart project. Replace the smart selector directly if surrounding text changed.
old="elif new_sel not in text:raise SystemExit('8.28: fidelity encoder selector marker missing')"
new="""elif new_sel not in text:\n    if 'choose_fidelity_encoder(app,attempt).await' not in text: raise SystemExit('8.29: fidelity selector missing')\n    text=text.replace('choose_fidelity_encoder(app,attempt).await','\\\"libx265\\\".to_string()',1)"""
if old in text:text=text.replace(old,new,1)

# Final mux fallback: insert faststart after the exact copy/copy pair even if the
# surrounding Vec formatting changed.
old="elif new_mux not in text:raise SystemExit('8.28: final mux marker missing')"
new="""elif new_mux not in text:\n    needle='\\\"-c:v\\\",\\\"copy\\\",\\\"-c:a\\\",\\\"copy\\\"'\n    if needle not in text: raise SystemExit('8.29: final copy/copy mux pair missing')\n    text=text.replace(needle,needle+',\\\"-movflags\\\",\\\"+faststart\\\"',1)"""
if old in text:text=text.replace(old,new,1)

p.write_text(text,encoding='utf-8')
print('ENDLUME 8.29: Hybrid Fidelity patcher repaired and quality budget set to CRF22')
