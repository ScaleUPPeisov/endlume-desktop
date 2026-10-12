#!/usr/bin/env python3
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'src-tauri'/'src'/'vyron_bridge.rs'
text=path.read_text(encoding='utf-8')

# Explicit VYRON outputDir is canonical and may intentionally live on /Volumes
# (or another Windows drive). Do not constrain it to batch/workspace ancestry.
text,n=re.subn(
    r'''fn validate_output_scope\(output:&Path,batch_root:&Path\)->Result<\(\),String>\{.*?\n\}\n''',
    '',
    text,
    count=1,
    flags=re.S,
)
if n!=1:
    raise SystemExit(f'vyron_bridge.rs: expected one validate_output_scope helper, got {n}')
needle='    validate_output_scope(&output,batch_root)?;\n'
if text.count(needle)!=1:
    raise SystemExit(f'vyron_bridge.rs: expected one explicit scope call, got {text.count(needle)}')
text=text.replace(needle,'',1)
path.write_text(text,encoding='utf-8')

qa=ROOT/'scripts'/'qa-endlume-1014-hotfix.py'
qa_text=qa.read_text(encoding='utf-8')
anchor='assert "v.get(\\"outputDir\\")" in vyron and "validate_output_writable" in vyron\n'
if anchor not in qa_text:
    raise SystemExit('qa-endlume-1014-hotfix.py: VYRON QA anchor missing')
qa_text=qa_text.replace(anchor,anchor+'assert "validate_output_scope(&output,batch_root)?" not in vyron\n',1)
qa.write_text(qa_text,encoding='utf-8')

print('PASS: explicit VYRON outputDir remains valid outside workspace, including external volumes')
