# Host-test actual SK16 reader and renderer with mocked GL.
from pathlib import Path
import re,subprocess,tempfile,struct
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='vita-skin-test-') as tmp:
    d=Path(tmp);source=(root/'Engine/SkinnedModel.cpp').read_text()+(root/'Memory/MemoryManager.h').read_text();constants=sorted(set(re.findall(r'\bGL_[A-Z0-9_]+\b',source)));functions=set(re.findall(r'\bgl[A-Z][A-Za-z0-9_]+\b',source))
    header=r'''#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cassert>
#include <vector>
using GLuint=unsigned;using GLenum=unsigned;using GLint=int;using GLsizei=int;
inline std::vector<float> capturedPose;
inline unsigned draws=0,attribs=0,paletteUploads=0,uniformMode=0;inline bool checking=false;inline float boneTranslation=0;
inline void glGenBuffers(int n,GLuint* p){static unsigned id=1;while(n--)*p++=id++;}
inline void glGenTextures(int,GLuint* p){*p=101;}
inline GLint glGetAttribLocation(GLuint,const char* n){return !strcmp(n,"aPosition")?0:!strcmp(n,"aTexCoord")?1:!strcmp(n,"aOctNormal")?2:!strcmp(n,"aBoneIds")?3:4;}
inline GLint glGetUniformLocation(GLuint,const char* n){return !strcmp(n,"uBones")?(uniformMode==0?-9:-1):!strcmp(n,"uBones[0]")?(uniformMode==1?-9:-1):1;}
inline void glUniformMatrix4fv(GLint loc,int count,int,const float* p){if(loc==-9){assert(count>0&&count<=24);++paletteUploads;capturedPose.insert(capturedPose.end(),p,p+count*16);boneTranslation+=p[12]+p[13]+p[14];}}
inline void glVertexAttribPointer(GLint a,int components,GLenum,int normalized,int stride,const void* offset){if(checking){assert(stride==16);unsigned expected[]={0,6,10,12,14};assert(size_t(offset)==expected[a]);assert(components==(a==0?3:a==4?1:2));assert(normalized==(a==2||a==4));++attribs;}}
inline void glDrawElements(GLenum,int count,GLenum,const void* offset){assert(count>0&&count%3==0&&!offset);++draws;}
'''
    for i,n in enumerate(constants,10):header+=f'constexpr GLenum {n}={0 if n=="GL_FALSE" else 1 if n=="GL_TRUE" else i};\n'
    special={'glGenBuffers','glGenTextures','glGetAttribLocation','glGetUniformLocation','glUniformMatrix4fv','glVertexAttribPointer','glDrawElements'}
    for n in sorted(functions-special):header+=f'template<class... A>inline GLuint {n}(A...){{return 1;}}\n'
    (d/'vitaGL.h').write_text(header);(d/'psp2/kernel').mkdir(parents=True);(d/'psp2common').mkdir()
    (d/'psp2/kernel/clib.h').write_text('#pragma once\n#include <cstdio>\n#define sceClibPrintf std::printf\n')
    (d/'psp2/ctrl.h').write_text('#pragma once\nstruct SceCtrlData{unsigned buttons=0;unsigned char lx=128,ly=128,rx=128,ry=128;};\nconstexpr unsigned SCE_CTRL_SELECT=1,SCE_CTRL_SQUARE=2,SCE_CTRL_LTRIGGER=4,SCE_CTRL_RTRIGGER=8;\ninline int sceCtrlPeekBufferPositive(int,SceCtrlData*,int){return 1;}\n')
    (d/'psp2common/ctrl.h').write_text('#pragma once\n#include <psp2/ctrl.h>\n')
    (d/'test.cpp').write_text(r'''#include "Engine/SkinnedModel.h"
#include "Memory/MemoryManager.h"
#include "Objects/CameraActor.h"
#include "Objects/Character.h"
#include "Engine/DoorManager.h"
#include "Managers/CollisionManager.h"
#include <unordered_map>
#include <fstream>
#include <cmath>
MemoryManager::MemoryManager(){} MemoryManager::~MemoryManager(){}
Texture* MemoryManager::getTexture(const std::string& path){static std::unordered_map<std::string,Texture> textures;auto& t=textures[path];t.size_x=t.size_y=512;t.textureID=42;return &t;}
void nativeDoorProcess(Character& character,const char* levelPath,const char* doorPath,const char* profilePath){
 std::ifstream f(levelPath,std::ios::binary);char magic[4];f.read(magic,4);assert(!std::memcmp(magic,"LVL5",4));
 unsigned ni,nc,nl;f.read((char*)&ni,4);f.read((char*)&nc,4);f.read((char*)&nl,4);f.seekg(16,std::ios::cur);
 auto point=[&](){float p[3];f.read((char*)p,12);return glm::vec3(p[0],p[1],p[2]);};
 CollisionManager collision;for(unsigned i=0;i<nc;++i){auto a=point(),b=point(),c=point();collision.addTriangle(a,b,c);}
 std::vector<Instance> instances(ni);
 for(auto& instance:instances){f.read((char*)&instance.modelMatrix,64);instance.boundingBox.minBounds=point();instance.boundingBox.maxBounds=point();for(int j=0;j<2;++j){uint16_t length;f.read((char*)&length,2);f.seekg(length,std::ios::cur);}}
 assert(f);DoorManager doors;assert(doors.Load(doorPath,levelPath,instances,collision));assert(doors.LoadInteractions(profilePath,levelPath));
 glm::vec3 positions[]={{14.9f,31.44f,-27.75f},{7.9f,31.44f,-28.2f},{9.6f,31.44f,-38.1f}};
 character.SetCamera(nullptr);
 for(auto p:positions){character.SetPosition(p.x,p.y,p.z);character.SetGrounded(true);
  TriggerManager::Box box{{p.x-.35f,p.y,p.z-.35f},{p.x+.35f,p.y+1.6f,p.z+.35f}};
  doors.Update(0,box,false,true,instances,collision);doors.Update(0,box,true,true,instances,collision);
  InteractionProcess::Plan plan;assert(doors.ConsumeProcess(plan));assert(character.StartInteraction(plan));
  bool began=false;float maxCorrection=0;
  for(unsigned frame=0;frame<400 && character.IsInteracting();++frame){
   character.Update(1.f/60);
   if(character.SampledInteractionThisFrame())doors.SampleProcess(plan.object,character.GetInteraction().PlaybackTime(),instances,collision);
   auto before=character.GetPosition();collision.computeCollision(&character);auto after=character.GetPosition();
   maxCorrection=std::max(maxCorrection,std::sqrt((before.x-after.x)*(before.x-after.x)+(before.z-after.z)*(before.z-after.z)));
   if(character.GetInteraction().GetState()==InteractionProcess::State::Ready && character.BeginInteractionPlayback()){assert(doors.BeginProcess(plan.object));began=true;}
  }
  std::printf("Native process object=%u began=%d state=%d max horizontal collision correction=%.4f\n",plan.object,began,int(character.GetInteraction().GetState()),maxCorrection);
  assert(began&&character.GetInteraction().GetState()==InteractionProcess::State::Finished);
 }
}
std::vector<float> capture(SkinnedModel& model,CameraActor& camera){
 capturedPose.clear();RenderStats stats;model.Draw(glm::mat4(1),&camera,{},1,stats);return capturedPose;
}
void crossFadeTest(const char* path,MemoryManager& memory,CameraActor& camera){
 SkinnedModel model;assert(model.Load(path,memory));
 auto initial=capture(model,camera);assert(initial.size()==16);
 model.Update(0,1);assert(capture(model,camera)==initial);
 model.Update(.09f,1);auto half=capture(model,camera);
 assert(std::abs(half[12]-1.f)<1e-5f); // midpoint translation
 glm::vec3 x(half[0],half[1],half[2]),y(half[4],half[5],half[6]),z(half[8],half[9],half[10]);
 assert(std::abs(glm::length(x)-1)<1e-5f&&std::abs(glm::length(y)-1)<1e-5f&&std::abs(glm::length(z)-1)<1e-5f);
 assert(std::abs(glm::dot(x,z))<1e-5f);
 glm::vec3 centre=glm::mat3(x,y,z)*glm::vec3(1,1,0)+glm::vec3(half[12],half[13],half[14]);
 assert(glm::length(centre-glm::vec3(1,1,0))<1e-5f); // correct bind pivot, no artificial shoulder displacement // 180-degree turn must not collapse the basis
 model.Update(0,0);assert(capture(model,camera)==half); // interrupt from displayed pose
 model.Update(.18f,0);assert(capture(model,camera)==initial);
 model.SampleAt(1,.7f,.09f);assert(std::abs(capture(model,camera)[12]-1.f)<1e-5f);
 model.SampleAt(1,.79f,.09f);auto final=capture(model,camera);assert(std::abs(final[12]-2.f)<1e-5f);
 model.SampleAt(1,1.f,.2f);assert(capture(model,camera)==final); // external clock, no fade restart
 model.SetTransitionDuration(0);model.Update(0,0);assert(capture(model,camera)==initial);
 model.SetTransitionDuration(.5f);model.SampleAt(2,.25f,.5f);assert(std::abs(capture(model,camera)[12]-1.f)<1e-5f);
 model.Update(0,0);model.Update(.25f,0);assert(std::abs(capture(model,camera)[12]-1.f)<1e-5f); // outgoing clip advances
 puts("PASS cross-fade: zero-time continuity, midpoint translation, rigid 180-degree rotation, interrupted fade, external clock, exact completion, disabled fade, fixed bind pivot, live outgoing motion");
}
int main(int argc,char** argv){assert(argc==7);MemoryManager memory;SkinnedModel model;assert(model.Load(argv[1],memory));assert(!model.Load(argv[1],memory));CameraActor camera;RenderStats stats;checking=true;model.Draw(glm::mat4(1),&camera,{},1,stats);assert(stats.drawCalls==30&&stats.triangles==33505&&draws==30&&attribs==150&&paletteUploads==30);float old=boneTranslation;model.Update(.7f,1);uniformMode=1;stats={};model.Draw(glm::mat4(1),&camera,{},1,stats);assert(std::abs(boneTranslation-old)>1e-5f&&stats.triangles==33505);uniformMode=2;stats={};model.Draw(glm::mat4(1),&camera,{},1,stats);assert(stats.drawCalls==0);assert(model.GetClipDuration(0)>0&&model.GetClipDuration(999)==0);uniformMode=0;model.Update(100.f,2,false);boneTranslation=0;stats={};model.Draw(glm::mat4(1),&camera,{},1,stats);float finalPose=boneTranslation;model.Update(1.f,2,false);boneTranslation=0;stats={};model.Draw(glm::mat4(1),&camera,{},1,stats);assert(std::abs(boneTranslation-finalPose)<1e-6f);model.Update(-1.f,0);SkinnedModel broken;assert(!broken.Load(argv[2],memory));assert(model.FindClip("sar-p-open-pull-l--sarah")==3);
assert(model.FindClip("hom1-house-door-push--sarah")==4);
assert(model.FindClip("missing")==-1);
Character character;character.setSkinnedModel(&model);character.SetGrounded(true);character.SetPosition(0,0,0);
InteractionProcess::MotionKey motion[]={{0,{0,0}},{model.GetClipDuration(3),{.2f,.3f}}};
InteractionProcess::Plan plan{0,{1,0,0},90,model.GetClipDuration(3),"sar-p-open-pull-l--sarah",motion,2};
assert(character.StartInteraction(plan));assert(!character.StartInteraction(plan));
character.Update(.05f);assert(character.GetPosition().x>0&&character.GetPosition().x<.1f);
assert(!character.SampledInteractionThisFrame());
for(unsigned i=0;i<80 && character.GetInteraction().GetState()!=InteractionProcess::State::Ready;++i)character.Update(.05f);
assert(character.BeginInteractionPlayback());character.Update(plan.duration*.5f);
assert(character.SampledInteractionThisFrame());assert(std::abs(character.GetPosition().x-1.15f)<.01f);
assert(std::abs(character.GetPosition().z+.1f)<.01f);
character.Update(plan.duration);assert(!character.IsInteracting());
plan.clip="missing";assert(!character.StartInteraction(plan));plan.clip="hom1-house-door-push--sarah";plan.duration=model.GetClipDuration(4);
assert(character.StartInteraction(plan));character.SetCamera(&camera);camera.SetMode(CameraMode::Spectate);character.Update(.1f);
assert(!character.IsInteracting()&&character.GetInteraction().GetState()==InteractionProcess::State::Cancelled);
nativeDoorProcess(character,argv[3],argv[4],argv[5]);
crossFadeTest(argv[6],memory,camera);
puts("PASS interaction: any Character instance, approach/turn, deferred animation, shared clock/root motion, finish, missing clip, noclip cancellation");
puts("PASS SK16 C++: actual loader, truncation rejection, GPU stride/offsets/normalization, indexed draw totals, palettes, animation updates");}
''')
    bad=d/'bad.sk16';bad.write_bytes((root/'assets/characters/sarah16/sarah.sk16').read_bytes()[:30])
    # Two rigid poses differing by 180 degrees: raw matrix lerp would collapse X/Z.
    fixture=d/'blend.sk16'
    texture=b'app0:/characters/test.bin'
    raw=bytearray(struct.pack('<4s4I',b'SK16',2,1,1,3)+struct.pack('<3f',1,1,0))
    raw+=struct.pack('<4I4f',3,3,1,len(texture),0,0,0,.001)+texture
    raw+=struct.pack('<H',0)+bytes(3*16)+struct.pack('<3H',0,1,2)
    for name,values in [(b'idle',[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]),
                        (b'action',[-1,0,0,0,0,1,0,0,0,0,-1,0,2,0,0,1])]:
        raw+=struct.pack('<IIf',len(name),2,1)+name+struct.pack('<32f',*(values*2))
    values=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];end=values.copy();end[12]=4
    raw+=struct.pack('<IIf',6,2,1)+b'moving'+struct.pack('<32f',*(values+end))
    fixture.write_bytes(raw)
    binary=d/'test';subprocess.run(['g++','-std=c++17','-O0','-I'+str(d),'-I'+str(root),'-I'+str(root/'Engine'),'-I'+str(root/'Engine/glm'),str(d/'test.cpp'),str(root/'Engine/SkinnedModel.cpp'),str(root/'Objects/CameraActor.cpp'),str(root/'Objects/Character.cpp'),str(root/'Engine/DoorManager.cpp'),str(root/'Managers/CollisionManager.cpp'),'-o',str(binary)],check=True)
    subprocess.run([str(binary),str(root/'assets/characters/sarah16/sarah.sk16'),str(bad),str(root/'assets/level.bin'),str(root/'assets/assets/metadata/doors.bin'),str(root/'assets/assets/metadata/door_interactions.bin'),str(fixture)],check=True)
