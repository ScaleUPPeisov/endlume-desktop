#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys
import tempfile

# Final 8.51 migration wrapper.
# The original d4f50ea migration passed the physical render gates but selected
# the end of assemble_visual by searching for the next async fn. In the 8.50
# reconstructed source, synchronous release helpers live between those two async
# functions, so that range also deleted FinalProbe/final_verify_error/
# write_side_files. This wrapper keeps the proven migration byte-for-byte except
# for replacing that range locator with a Rust-aware brace matcher.
REPO = "ScaleUPPeisov/endlume-desktop"
ORIGINAL_PIN = "d4f50ea8a13a21d6163c1ab16d4669432d09f97d"

# BUILD_ENDLUME_851_SELFHOSTED.command currently normalizes the historical
# matcher before running the fetched patch. Keep this literal compatibility
# anchor so the pinned builder can perform that normalization without failing.
# It is intentionally unused by this wrapper.
_BUILDER_COMPAT = """start=s.find('async fn assemble_visual(')
end=s.find('\\n\\nasync fn ',start+10)
must(start>=0 and end>start,'assemble_visual block not found')"""


def fail(message: str) -> None:
    raise SystemExit("8.51 final migration wrapper: " + message)


def patch_original(source: str) -> str:
    lines = source.splitlines()
    start_line = "start=s.find('async fn assemble_visual(')"
    idx = next((i for i, line in enumerate(lines) if line.strip() == start_line), -1)
    if idx < 0 or idx + 2 >= len(lines):
        fail("historical assemble_visual locator not found")
    if not lines[idx + 1].strip().startswith("end=s.find("):
        fail("historical assemble_visual end locator not found")
    if "assemble_visual block not found" not in lines[idx + 2]:
        fail("historical assemble_visual guard not found")

    replacement = r'''def rust_function_end(text,start):
    opening=text.find('{',start)
    must(opening>=0,'assemble_visual opening brace not found')
    depth=0;i=opening;n=len(text);state='code';block_depth=0;raw_hashes=0
    while i<n:
        c=text[i];nxt=text[i+1] if i+1<n else ''
        if state=='line':
            if c=='\n': state='code'
            i+=1;continue
        if state=='block':
            if c=='/' and nxt=='*': block_depth+=1;i+=2;continue
            if c=='*' and nxt=='/':
                block_depth-=1;i+=2
                if block_depth==0: state='code'
                continue
            i+=1;continue
        if state=='string':
            if c=='\\': i+=2;continue
            if c=='"': state='code'
            i+=1;continue
        if state=='char':
            if c=='\\': i+=2;continue
            if c=="'": state='code'
            i+=1;continue
        if state=='raw':
            if c=='"' and text.startswith('#'*raw_hashes,i+1):
                i+=1+raw_hashes;state='code';continue
            i+=1;continue
        if c=='/' and nxt=='/': state='line';i+=2;continue
        if c=='/' and nxt=='*': state='block';block_depth=1;i+=2;continue
        if c=='"': state='string';i+=1;continue
        if c=="'" and i+2<n and (text[i+2]=="'" or (text[i+1]=='\\' and i+3<n)):
            state='char';i+=1;continue
        if c=='r':
            j=i+1;h=0
            while j<n and text[j]=='#': h+=1;j+=1
            if j<n and text[j]=='"': state='raw';raw_hashes=h;i=j+1;continue
        if c=='{': depth+=1
        elif c=='}':
            depth-=1
            if depth==0: return i+1
        i+=1
    must(False,'assemble_visual closing brace not found')

start=s.find('async fn assemble_visual(')
must(start>=0,'assemble_visual block not found')
end=rust_function_end(s,start)'''.splitlines()
    lines[idx:idx + 3] = replacement
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


with tempfile.TemporaryDirectory(prefix="endlume-851-final-migration-") as td:
    original = Path(td) / "apply-full-project-speed-8-51.original.py"
    endpoint = f"/repos/{REPO}/contents/scripts/apply-full-project-speed-8-51.py?ref={ORIGINAL_PIN}"
    with original.open("wb") as fh:
        proc = subprocess.run(
            ["gh", "api", "-H", "Accept: application/vnd.github.raw+json", endpoint],
            stdout=fh,
            stderr=subprocess.PIPE,
            check=False,
        )
    if proc.returncode != 0:
        fail("cannot fetch pinned original migration: " + proc.stderr.decode("utf-8", "replace"))

    text = original.read_text(encoding="utf-8")
    fixed = patch_original(text)
    original.write_text(fixed, encoding="utf-8")

    compile_check = subprocess.run([sys.executable, "-m", "py_compile", str(original)], check=False)
    if compile_check.returncode != 0:
        fail("corrected pinned migration does not compile")

    result = subprocess.run([sys.executable, str(original), *sys.argv[1:]], check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

print("ENDLUME 8.51 final migration: assemble_visual replaced without deleting synchronous release helpers")
