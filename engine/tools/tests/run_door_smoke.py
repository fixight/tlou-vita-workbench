"""Exercise the real door controller and triangle collision on a host compiler."""
from pathlib import Path
import struct,tempfile,subprocess
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='vita-door-') as tmp:
 d=Path(tmp);(d/'psp2/kernel').mkdir(parents=True)
 (d/'psp2/kernel/clib.h').write_text('#pragma once\n#include <cstdio>\n#define sceClibPrintf std::printf\n')
 (d/'vitaGL.h').write_text('#pragma once\nusing GLuint=unsigned;\n')
 level=b'test level';(d/'level.bin').write_bytes(level)
 h=14695981039346656037
 for b in level:h=((h^b)*1099511628211)&0xffffffffffffffff
 data=bytearray(struct.pack('<4sIIIQI',b'VDOR',1,1,1,h,1))
 for t in ['door1','TEST DOOR']:
  b=t.encode();data.extend(struct.pack('<I',len(b))+b)
 data.extend(struct.pack('<6f',0,0,0,90,1,.2))
 data.extend(struct.pack('<I6f',1,-2,-1,-2,2,3,2))
 data.extend(struct.pack('<2I',1,0)) # mesh instance
 data.extend(struct.pack('<2I',1,0)) # transfer native triangle
 data.extend(struct.pack('<I9f',1,0,0,0,1,0,0,1,2,0))
 (d/'door.bin').write_bytes(data);(d/'bad.bin').write_bytes(data[:-2])
 (d/'other.bin').write_bytes(b'wrong level')
 binary=d/'test'
 subprocess.run(['g++','-std=c++17','-O0','-I'+str(d),'-I'+str(root),'-I'+str(root/'Engine'),'-I'+str(root/'Engine/glm'),str(root/'tools/tests/door_smoke.cpp'),str(root/'Engine/DoorManager.cpp'),str(root/'Managers/CollisionManager.cpp'),'-o',str(binary)],check=True)
 subprocess.run([str(binary),str(d/'door.bin'),str(d/'level.bin'),str(d/'bad.bin'),str(d/'other.bin')],check=True)

 if (root/'assets/assets/metadata/doors.bin').exists():
  subprocess.run([str(binary),str(root/'assets/assets/metadata/doors.bin'),str(root/'assets/level.bin')],check=True)

 if (root/'assets/assets/metadata/door_interactions.bin').exists():
  subprocess.run([str(binary),str(root/'assets/assets/metadata/doors.bin'),str(root/'assets/level.bin'),str(root/'assets/assets/metadata/door_interactions.bin')],check=True)
