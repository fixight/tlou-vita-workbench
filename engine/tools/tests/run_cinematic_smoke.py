"""Run the real cinematic loader/sampler with host GL stubs and exported assets."""
from pathlib import Path
import re,struct,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
source=(root/'Engine/SkinnedModel.cpp').read_text()
functions=set(re.findall(r'\b(gl\w+)\(',source))
constants=set(re.findall(r'\bGL_[A-Z_0-9]+',source))
with tempfile.TemporaryDirectory(prefix='vita-cinematic-test-') as temporary:
    work=Path(temporary)
    (work/'app0:').symlink_to(root/'assets',target_is_directory=True)
    header='#pragma once\n#include <cassert>\nusing GLuint=unsigned; using GLint=int; using GLenum=unsigned; using GLsizeiptr=long; using GLsizei=int;\n'
    for index,name in enumerate(constants,10):header+=f'constexpr GLenum {name}={index};\n'
    functions.discard("glGenBuffers");functions.discard("glGenTextures")
    header+="inline void glGenBuffers(int n,GLuint* p){static unsigned id=1;while(n--)*p++=id++;}\ninline void glGenTextures(int,GLuint* p){*p=101;}\n"
    for name in functions:header+=f'template<class... A> inline GLuint {name}(A...){{return 1;}}\n'
    (work/'vitaGL.h').write_text(header)
    (work/'psp2/kernel').mkdir(parents=True);(work/'psp2common').mkdir()
    (work/'psp2/kernel/clib.h').write_text('#pragma once\n#include <cstdio>\n#define sceClibPrintf std::printf\n')
    (work/'psp2/ctrl.h').write_text('#pragma once\nstruct SceCtrlData{unsigned buttons=0;unsigned char lx=128,ly=128,rx=128,ry=128;};\nconstexpr unsigned SCE_CTRL_SELECT=1,SCE_CTRL_SQUARE=2,SCE_CTRL_LTRIGGER=4,SCE_CTRL_RTRIGGER=8;\ninline int sceCtrlPeekBufferPositive(int,SceCtrlData*,int){return 1;}\n')
    (work/'psp2common/ctrl.h').write_text('#pragma once\n#include <psp2/ctrl.h>\n')
    native=(root/'assets/assets/cinematics/bedroom/scene.vcn').read_bytes()
    lens_bytes=12+912*40
    # V3 adds runtime records after the complete V2 timeline.
    v2_end=190194
    runtime_bytes=native[v2_end:]
    native=native[:v2_end]
    v2=bytearray(native);struct.pack_into('<I',v2,4,2)
    (work/'v2.vcn').write_bytes(v2)
    def text(value):
        data=value.encode();return struct.pack('<I',len(data))+data
    events=struct.pack('<I',3)+struct.pack('<fI',0,3)+struct.pack('<fI',1,9)+struct.pack('<fI',2,3)
    events+=struct.pack('<I',1)+text('app0:/assets/audio/level.vabk')+struct.pack('<I',2)
    for time in [0,1.5]:
        events+=struct.pack('<f',time)+text('sarah.phone.call')+struct.pack('<ffI',1,0,0)
    test_scene=bytearray(native);struct.pack_into('<I',test_scene,4,3)
    (work/'events.vcn').write_bytes(test_scene+events)
    (work/'bad-events.vcn').write_bytes(test_scene+events[:-1])
    legacy=bytearray(native[:-lens_bytes]);struct.pack_into('<I',legacy,4,1)
    name_length=struct.unpack_from('<I',legacy,8)[0]
    stage_offset=12+name_length+20
    struct.pack_into('<f',legacy,stage_offset+4,60)
    (work/'legacy.vcn').write_bytes(legacy)
    malformed=bytearray(native);struct.pack_into('<I',malformed,len(native)-lens_bytes+4,911)
    (work/'malformed.vcn').write_bytes(malformed)
    (work/'test.cpp').write_text(r'''#include "Engine/CinematicPlayer.h"
#include "Objects/CameraActor.h"
#include "Objects/Character.h"
#include "Memory/MemoryManager.h"
#include <unordered_map>
#include <cassert>
struct AudioManager::Impl {};
static unsigned playedSounds=0, stoppedSounds=0;
AudioManager::AudioManager(std::unique_ptr<Audio::Backend>) : impl(new Impl) {}
AudioManager::~AudioManager() = default;
bool AudioManager::loadBank(const char*) { return true; }
std::string AudioManager::getLastError() const { return {}; }
SoundHandle AudioManager::playSound(SoundId,const SoundOptions&) { ++playedSounds; return {playedSounds}; }
bool AudioManager::stopSound(SoundHandle,float) { ++stoppedSounds; return true; }
MemoryManager::MemoryManager(){} MemoryManager::~MemoryManager(){}
Texture* MemoryManager::getTexture(const std::string& path){static std::unordered_map<std::string,Texture> textures;auto& t=textures[path];t.size_x=t.size_y=512;t.textureID=42;return &t;}
Mesh* MemoryManager::getMesh(const std::string& path){static std::unordered_map<std::string,Mesh> meshes;return &meshes[path];}
int main(){
 MemoryManager memory;CinematicPlayer scene;CameraActor camera;Character player;
 if(!scene.Load("app0:/assets/cinematics/bedroom/scene.vcn",memory)){fprintf(stderr,"%s\n",scene.GetLastError().c_str());return 1;}
 AudioManager audio;
 assert(scene.PrepareAudio(audio));
 assert(scene.GetControl().characterPose==PoseOwner::Cinematic);
 assert(!scene.GetControl().movement);
 assert(!scene.IsPlaying());assert(scene.Play());assert(!scene.Play());
 assert(playedSounds==2);
 camera.SetPlayerControl(PlayerControl::FullCinematic());
 scene.ApplyCamera(camera);assert(std::abs(camera.GetPosition().x-14.453819f)<.0001f);
 assert(std::abs(camera.GetPosition().y-33.80655f)<.0001f);
 assert(camera.HasCinematicLens());
 assert(std::abs(camera.GetCinematicLens().focalLengthMm-50.f)<.0001f);
 assert(std::abs(camera.GetCinematicLens().horizontalFov-39.5977527f)<.0001f);
 assert(camera.GetCinematicLens().hasDepthOfField);
 assert(std::abs(camera.GetCinematicLens().nearEnd-3.0395136f)<.0001f);
 assert(std::abs(camera.GetCinematicLens().farStart-5.8479533f)<.0001f);
 auto view=camera.GetViewMatrix(),projection=camera.GetProjectionMatrix();
 assert(std::abs(projection[0][0]-50.f/18.f)<.0001f);
 assert(std::abs(projection[1][1]-(50.f/18.f)*(960.f/544.f))<.0001f);
 assert(CinematicLens::BlendWeight(1,0,0)==0);
 assert(CinematicLens::BlendWeight(1,0,.5f)==1);
 assert(CinematicLens::BlendWeight(1,1,.5f)==.5f);
 for(unsigned i=0;i<16;++i)assert(std::isfinite((&view[0][0])[i])&&std::isfinite((&projection[0][0])[i]));
 RenderStats stats;scene.Draw(&camera,{},1,stats);assert(stats.drawCalls==49);assert(stats.triangles==40930);
 scene.Update(756.5/30); assert(playedSounds==3); scene.ApplyCamera(camera);
 assert(std::abs(camera.GetCinematicLens().focalLengthMm-23.458f)<.0001f);
 assert(scene.Play()==false);scene.Cancel();assert(stoppedSounds==3);assert(scene.Play());assert(playedSounds==5);
 scene.Update(15);scene.ApplyPlayerAnchor(player);assert(std::isfinite(player.GetPosition().y));
 assert(!scene.ConsumeFinished());scene.Update(100);assert(!scene.IsPlaying());
 assert(stoppedSounds==6);assert(scene.ConsumeFinished());assert(!scene.ConsumeFinished());scene.ApplyGameplayHandoff(player);
 assert(std::abs(player.GetPosition().x-16.5814f)<.001f);assert(std::abs(player.GetPosition().y-31.412724f)<.001f);
 std::vector<Instance> world(1897);Mesh original{};for(auto& i:world)i.mesh=&original;
 assert(scene.LoadWorldMask("app0:/assets/cinematics/bedroom/mask/world.vcm","app0:/level.bin",world,memory));
 scene.ApplyWorldMask(world,true);unsigned changed=0;for(auto& i:world)changed+=i.mesh!=&original;assert(changed==4);
 scene.ApplyWorldMask(world,false);for(auto& i:world)assert(i.mesh==&original);
 assert(!scene.LoadWorldMask("app0:/assets/cinematics/bedroom/mask/world.vcm","app0:/assets/cinematics/bedroom/scene.vcn",world,memory));
 assert(scene.Play());scene.Cancel();assert(!scene.IsPlaying());assert(!scene.ConsumeFinished());
 CinematicPlayer events;
 assert(events.Load("events.vcn",memory));assert(events.PrepareAudio(audio));
 const unsigned before=playedSounds, stopped=stoppedSounds;
 assert(events.Play());assert(playedSounds==before+1);
 events.Update(1.1);assert(events.GetControl().cameraLook);assert(!events.GetControl().movement);
 assert(events.GetControl().cameraPose==PoseOwner::Gameplay);
 events.Update(.6);assert(playedSounds==before+2);
 events.Update(.1);assert(playedSounds==before+2);
 events.Update(.3);assert(events.GetControl().cameraPose==PoseOwner::Cinematic);
 events.Cancel();assert(stoppedSounds==stopped+2);
 assert(!events.Load("bad-events.vcn",memory));
 CinematicPlayer v2Scene;assert(v2Scene.Load("v2.vcn",memory));assert(v2Scene.Play());v2Scene.Cancel();
 CinematicPlayer oldScene;
 assert(oldScene.Load("legacy.vcn",memory));assert(oldScene.Play());oldScene.ApplyCamera(camera);
 assert(!camera.HasCinematicLens());
 assert(std::abs(camera.GetProjectionMatrix()[1][1]-1.7320508f)<.0001f);
 assert(!oldScene.Load("malformed.vcn",memory));oldScene.Cancel();
 assert(!oldScene.Load("malformed.vcn",memory));
 assert(oldScene.GetLastError()=="Camera/lens samples disagree");
 puts("PASS cinematic: real SK16 actors, shared clock, native camera, handoff, completion once, cancel, exact world mask binding/restoration");
}
''')
    binary=work/'test'
    command=['g++','-std=c++17','-Wall','-Wextra','-I'+str(work),'-I'+str(root),'-I'+str(root/'Engine'),'-I'+str(root/'Engine/glm'),str(work/'test.cpp')]
    command += [str(root/p) for p in ['Engine/SkinnedModel.cpp','Engine/CinematicPlayer.cpp','Objects/Character.cpp','Objects/CameraActor.cpp']]
    command += ['-o',str(binary)]
    subprocess.run(command,check=True)
    subprocess.run([str(binary)],cwd=work,check=True)
