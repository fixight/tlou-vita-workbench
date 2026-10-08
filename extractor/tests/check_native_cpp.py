"""Generate and compare real-game selector/geometry cases against the C++ reader."""
import json
import random
import subprocess
import sys
import shlex
from pathlib import Path
from tlou_extractor.streaming_native import GameState,select_native

root=Path(__file__).resolve().parents[1]
fixture=Path(sys.argv[1]) if len(sys.argv)>1 else Path(r'D:\TLOUPS4\AustinStreaming')
doc=json.loads((fixture/'streaming_runtime.json').read_text(encoding='utf-8'))
home=doc['task_graphs']['home'];regions=[r for r in doc['regions'] if r['source_level']=='world-home']
points=[];random.seed(314159)
for region in regions:
    for shape in region['shapes']:
        lo,hi=shape['bounds_min'],shape['bounds_max']
        points.append([(a+b)/2 for a,b in zip(lo,hi)])
        points.extend([[random.uniform(a,b) for a,b in zip(lo,hi)] for _ in range(8)])
points.extend([[0,0,0],[100000,100000,100000]])
expected=[];lines=[str(len(home['nodes'])), ' '.join(str(int(k,16)) for k in home['nodes'])]
for phase in range(4):
    state=GameState({(home['id'],t):'complete' if phase==1 else 'pending' for t in home['nodes']}, {'0x69c85a6d':phase==3}, {('0x4f12da44','0x69c85a6d'):phase==3})
    if phase>=2:state.tasks[home['id'],'0xa6b62704']='active'
    for point in points:
        # Quantize identically to C++ input float.
        import struct
        point=list(struct.unpack('<3f',struct.pack('<3f',*point)))
        s=select_native(doc,'world-home',point,state)
        region=next((i for i,r in enumerate(regions) if r['id']==s['region_id']),-1)
        expected.append(' '.join([str(region),str(s['variant']),*sorted(s['display']),'|',*sorted(s['resident_only'])]))
        lines.append(str(phase)+' '+' '.join(format(v,'.9g') for v in point))
case=root/'tests_temp_out/native_streaming_cases.txt';case.parent.mkdir(exist_ok=True);case.write_text('\n'.join(lines))
binary=fixture/'world-home.tltr'
wsl_binary='/mnt/'+binary.drive[0].lower()+binary.as_posix()[2:]
command='g++ -std=c++17 -O2 -Wall -Wextra -Werror /mnt/d/TLOUPS4/fervent-pascal/tests/native_streaming_smoke.cpp -o /tmp/tlou_streaming_smoke && /tmp/tlou_streaming_smoke '+shlex.quote(wsl_binary)+' /mnt/d/TLOUPS4/fervent-pascal/tests_temp_out/native_streaming_cases.txt'
run=subprocess.run(['wsl.exe','-d','Ubuntu','--','bash','-lc',command],capture_output=True,text=True,encoding='utf-8')
if run.returncode:raise RuntimeError(run.stderr)
actual=run.stdout.splitlines()
assert len(actual)==len(expected),(len(actual),len(expected))
for i,(a,b) in enumerate(zip(actual,expected)):
    assert a.strip()==b.strip(),(i,a,b)
print(f'PASS: C++/Python parity across {len(expected)} real world-position/story-state cases; readiness barrier checked')
