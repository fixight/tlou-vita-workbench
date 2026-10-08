"""Host overlap and ABI checks for the actual engine TriggerManager."""
from pathlib import Path
import struct, subprocess, tempfile
root = Path(__file__).resolve().parents[2]
def encode(records):
    data=bytearray(struct.pack('<4sII',b'VTGR',1,len(records)))
    for identity,name,boxes in records:
        for value in (identity,name):
            text=value.encode();data.extend(struct.pack('<I',len(text)));data.extend(text)
        data.extend(struct.pack('<I',len(boxes)))
        for box in boxes:data.extend(struct.pack('<6f',*box))
    return data
with tempfile.TemporaryDirectory(prefix='vita-trigger-test-') as temporary:
    folder=Path(temporary)
    fixture=encode([('outer','OUTER',[(0,0,0,1,1,1),(3,0,0,4,1,1)]),
                    ('inner','INNER',[(.25,.25,.25,.75,.75,.75)])])
    (folder/'valid.bin').write_bytes(fixture)
    (folder/'truncated.bin').write_bytes(fixture[:-1])
    invalid=encode([('bad','BAD',[(2,0,0,1,1,1)])])
    (folder/'invalid.bin').write_bytes(invalid)
    (folder/'nan.bin').write_bytes(encode([('bad','BAD',[(float('nan'),0,0,1,1,1)])]))
    (folder/'version.bin').write_bytes(b'VTGR'+struct.pack('<II',2,0))
    (folder/'tail.bin').write_bytes(fixture+b'X')
    (folder/'limit.bin').write_bytes(b'VTGR'+struct.pack('<II',1,5000))
    (folder/'test.cpp').write_text(r'''#include "Engine/TriggerManager.h"
#include <cassert>
#include <cmath>
#include <iostream>
#include <limits>
int main(int argc,char** argv){
    assert(argc==3);std::string folder=argv[1]; TriggerManager triggers;
    assert(triggers.Load((folder+"/valid.bin").c_str()));
    TriggerManager::Box point{{.5f,.5f,.5f},{.5f,.5f,.5f}};
    triggers.Update(point);assert(triggers.GetActiveCount()==2);
    assert(triggers.GetHudText().find("LAST ENTER: INNER")!=std::string::npos);
    auto same=triggers.GetHudText();triggers.Update(point);assert(triggers.GetHudText()==same);
    triggers.Update({{2,.5f,.5f},{2,.5f,.5f}});assert(triggers.GetActiveCount()==0);
    triggers.Update({{1,.5f,.5f},{1,.5f,.5f}});assert(triggers.GetActiveCount()==1);
    triggers.Update({{1.2f,.2f,.2f},{3.2f,.3f,.3f}},true);assert(triggers.GetActiveCount()==1);
    assert(triggers.GetHudText().find("PROBE CAMERA")!=std::string::npos);
    triggers.Update({{std::numeric_limits<float>::quiet_NaN(),0,0},{1,1,1}});
    assert(triggers.GetActiveCount()==1);
    for(auto name:{"truncated","invalid","nan","version","tail","limit","missing"}){
        assert(!triggers.Load((folder+"/"+name+".bin").c_str()));
        assert(triggers.GetTriggers().empty());assert(triggers.GetActiveCount()==0);
        assert(!triggers.GetError().empty());
    }
    assert(triggers.Load(argv[2]));assert(!triggers.GetTriggers().empty());
    for(const auto& trigger:triggers.GetTriggers())for(const auto& box:trigger.volumes){
        TriggerManager::Box center;
        for(unsigned i=0;i<3;++i)center.min[i]=center.max[i]=(box.min[i]+box.max[i])*.5f;
        triggers.Update(center);assert(triggers.GetActiveCount()>0);
    }
    std::cout<<"Trigger smoke passed: overlap, disjoint volumes, entry/exit, camera probe, malformed files, "
             <<triggers.GetTriggers().size()<<" exported triggers\n";
}
''')
    binary=folder/'smoke'
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I'+str(root),
                    str(folder/'test.cpp'),str(root/'Engine/TriggerManager.cpp'),'-o',str(binary)],check=True)
    subprocess.run([str(binary),str(folder),str(root/'assets/assets/metadata/triggers.bin')],check=True)
