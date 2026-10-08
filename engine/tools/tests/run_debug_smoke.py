"""Host behavioral tests against the actual engine sources, with GL/controller mocks.
Does not validate Vita shader compilation, pixels or real hardware performance.
"""
from pathlib import Path
import re,subprocess,tempfile,struct
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='vita-debug-test-') as temporary:
    folder=Path(temporary)
    source='\n'.join((root/p).read_text() for p in ['Engine/Render.cpp','Engine/DebugHud.cpp','Engine/TriggerDebugView.cpp','Engine/SkinnedModel.cpp'])
    constants=sorted(set(re.findall(r'\bGL_[A-Z0-9_]+\b',source)))
    functions=set(re.findall(r'\bgl[A-Z][A-Za-z0-9_]+\b',source))
    special={'glDrawArrays','glBindTexture','glGenTextures','glGenBuffers','glGetShaderiv','glGetProgramiv','glGetAttribLocation'}
    header='''#pragma once
#include <cstdint>
#include <cstddef>
#include <cassert>
#include <cstring>
using GLuint=unsigned int;using GLenum=unsigned int;using GLint=int;using GLsizei=int;
using GLsizeiptr=std::ptrdiff_t;using GLintptr=std::ptrdiff_t;using GLboolean=unsigned char;
inline unsigned gDrawCalls=0,gLastDrawVertices=0,gBoundTexture=0;
inline bool gExpectSceneTexture=false;
inline void glDrawArrays(GLenum,int,GLsizei count){if(gExpectSceneTexture)assert(gBoundTexture==42);++gDrawCalls;gLastDrawVertices=count;}
inline void glBindTexture(GLenum,GLuint texture){gBoundTexture=texture;}
inline void glGenTextures(GLsizei,GLuint* texture){*texture=101;}
inline void glGenBuffers(GLsizei,GLuint* buffer){*buffer=102;}
inline void glGetShaderiv(GLuint,GLenum,GLint* value){*value=1;}
inline void glGetProgramiv(GLuint,GLenum,GLint* value){*value=1;}
inline GLint glGetAttribLocation(GLuint,const char* name){return !strcmp(name,"aPosition")?0:!strcmp(name,"aTexCoord")?1:2;}
'''
    for index,name in enumerate(constants,10):header+=f'constexpr GLenum {name}={0 if name=="GL_FALSE" else 1 if name=="GL_TRUE" else index};\n'
    for name in sorted(functions-special):header+=f'template<class... Args> inline GLuint {name}(Args...){{return 1;}}\n'
    (folder/'vitaGL.h').write_text(header)
    for directory in ['psp2/kernel','psp2common']:(folder/directory).mkdir(parents=True)
    (folder/'psp2/kernel/clib.h').write_text('#pragma once\n#include <cstdio>\n#define sceClibPrintf std::printf\n')
    (folder/'psp2/ctrl.h').write_text('''#pragma once
struct SceCtrlData{unsigned buttons=0;unsigned char lx=128,ly=128,rx=128,ry=128;};
constexpr unsigned SCE_CTRL_SELECT=1,SCE_CTRL_SQUARE=2,SCE_CTRL_LTRIGGER=4,SCE_CTRL_RTRIGGER=8;
inline SceCtrlData gPad;
inline int sceCtrlPeekBufferPositive(int,SceCtrlData* out,int){*out=gPad;return 1;}
''')
    (folder/'psp2common/ctrl.h').write_text('#pragma once\n#include <psp2/ctrl.h>\n')
    (folder/'memory_stub.cpp').write_text('#include "Memory/MemoryManager.h"\nTexture* MemoryManager::getTexture(const std::string&){return nullptr;}\n')
    fixture=bytearray(struct.pack('<4sII',b'VTGR',1,7))
    boxes=[(-1,-1,-6,1,1,-4),(-.8,-.8,-7,.8,.8,-5),(-.6,-.6,-8,.6,.6,-6),
           (-.5,-.5,-9,.5,.5,-7),(-1,-1,-30,1,1,-28),(-1,-1,4,1,1,6),(-50,-50,-50,50,50,50)]
    names=['NEAR ONE','NEAR TWO','NEAR THREE','NEAR FOUR','FAR','BEHIND','HUGE']
    for name,box in zip(names,boxes):
        for value in (name,name):
            raw=value.encode();fixture.extend(struct.pack('<I',len(raw)));fixture.extend(raw)
        fixture.extend(struct.pack('<I6f',1,*box))
    (folder/'triggers.bin').write_bytes(fixture)
    binary=folder/'smoke'
    subprocess.run(['g++','-std=c++17','-O0','-I'+str(folder),'-I'+str(root),'-I'+str(root/'Engine'),'-I'+str(root/'Engine/glm'),
                    str(root/'tools/tests/render_debug_smoke.cpp'),str(root/'Engine/Render.cpp'),
                    str(root/'Engine/SkinnedModel.cpp'),str(folder/'memory_stub.cpp'),str(root/'Engine/DebugHud.cpp'),str(root/'Engine/TriggerDebugView.cpp'),str(root/'Engine/TriggerManager.cpp'),str(root/'Objects/Character.cpp'),str(root/'Objects/CameraActor.cpp'),
                    '-o',str(binary)],check=True)
    subprocess.run([str(binary),str(folder/'triggers.bin')],check=True)
