#include "Engine/DoorManager.h"
#include "Managers/CollisionManager.h"
#include "Objects/Actor.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <cstring>
int main(int argc,char** argv) {
 if (argc==3 || argc==4) {
  std::ifstream f(argv[2],std::ios::binary);char magic[4];f.read(magic,4);assert(!std::memcmp(magic,"LVL5",4));
  unsigned ni,nc,nl;f.read((char*)&ni,4);f.read((char*)&nc,4);f.read((char*)&nl,4);f.seekg(16,std::ios::cur);
  auto point=[&](){float p[3];f.read((char*)p,12);return glm::vec3(p[0],p[1],p[2]);};
  CollisionManager collision;
  for(unsigned i=0;i<nc;++i){auto a=point(),b=point(),c=point();collision.addTriangle(a,b,c);}
  std::vector<Instance> instances(ni);
  for(auto& instance:instances){f.read((char*)&instance.modelMatrix,64);instance.boundingBox.minBounds=point();instance.boundingBox.maxBounds=point();
    for(int p=0;p<2;++p){uint16_t length;f.read((char*)&length,2);f.seekg(length,std::ios::cur);}}
  assert(f);DoorManager doors;assert(doors.Load(argv[1],argv[2],instances,collision));assert(doors.GetDoorCount()==4);
  if(argc==4)assert(doors.LoadInteractions(argv[3],argv[2]));
  assert(collision.GetTriangleCount()==nc+36); // 12 native replaced; three authored leaf boxes added
  std::vector<glm::mat4> closed;for(auto& instance:instances)closed.push_back(instance.modelMatrix);
  glm::vec3 positions[]={{14.8f,31.43f,-27.5f},{7.8f,31.43f,-28.1f},{10.8f,31.43f,-38.f},{12.5f,28.43f,-25.4f}};
  for(auto p:positions){TriggerManager::Box box{{p.x-.35f,p.y,p.z-.35f},{p.x+.35f,p.y+1.6f,p.z+.35f}};
    doors.Update(0,box,false,true,instances,collision);assert(doors.GetHudText().find("OPEN")!=std::string::npos);
    doors.Update(0,box,true,true,instances,collision);
    InteractionProcess::Plan plan;glm::vec3 target;
    if(doors.ConsumeProcess(plan)) {
      assert(plan.clip&&plan.motionCount>2&&plan.duration>3);
      auto before=instances;doors.Update(1,box,false,false,instances,collision);
      for(unsigned i=0;i<ni;++i)assert(before[i].modelMatrix==instances[i].modelMatrix);
      assert(doors.BeginProcess(plan.object));doors.SampleProcess(plan.object,plan.duration,instances,collision);
      doors.Update(0,box,false,true,instances,collision);
    } else {assert(doors.ConsumeInteraction(target));doors.Update(2,box,false,true,instances,collision);}assert(doors.GetHudText().find("CLOSE")!=std::string::npos);}
  unsigned changed=0;for(unsigned i=0;i<ni;++i)if(closed[i]!=instances[i].modelMatrix)++changed;assert(changed==11);
  puts("PASS actual Austin LVL5: four doors load/open, all 11 visual parts move, 12 native triangles transferred, 36 authored triangles added");return 0;
 }
 assert(argc==5);
 std::vector<Instance> instances(1);instances[0].modelMatrix=glm::mat4(1);
 instances[0].boundingBox={{0,0,-.01f},{1,2,.01f}};
 CollisionManager collision;collision.addTriangle({0,0,0},{1,0,0},{1,2,0});
 DoorManager corrupt;assert(!corrupt.Load(argv[3],argv[2],instances,collision));assert(collision.GetTriangleCount()==1);
 DoorManager stale;assert(!stale.Load(argv[1],argv[4],instances,collision));assert(collision.GetTriangleCount()==1);
 DoorManager doors;assert(doors.Load(argv[1],argv[2],instances,collision));assert(doors.GetDoorCount()==1&&collision.GetTriangleCount()==1);
 TriggerManager::Box near{{.3f,0,.4f},{.7f,1.6f,.8f}}, far{{10,0,10},{11,2,11}};
 glm::vec3 target;
 doors.Update(1,near,false,true,instances,collision);assert(doors.GetHudText().find("OPEN")!=std::string::npos);
 assert(instances[0].modelMatrix==glm::mat4(1)); // overlap is permission, not an action
 doors.Update(0,far,true,true,instances,collision);assert(!doors.ConsumeInteraction(target));
 doors.Update(0,near,false,true,instances,collision);
 doors.Update(0,near,true,false,instances,collision);assert(!doors.ConsumeInteraction(target)); // noclip disables use
 doors.Update(0,near,false,true,instances,collision);
 doors.Update(0,near,true,true,instances,collision);assert(doors.ConsumeInteraction(target));assert(!doors.ConsumeInteraction(target));
 doors.Update(.1f,near,true,true,instances,collision);assert(instances[0].modelMatrix==glm::mat4(1)); // delayed motion
 doors.Update(2,near,true,true,instances,collision);
 auto open=instances[0].modelMatrix;assert(std::abs(open[0][2])>.99f);
 assert(instances[0].boundingBox.maxBounds.x<.02f);
 assert(doors.GetHudText().find("CLOSE")!=std::string::npos);
 // Actual collision follows the same transform: the former closed leaf is clear.
 TLOU::Actor player;player.SetPosition(.5f,0,.1f);collision.computeCollision(&player);
 assert(std::abs(player.GetPosition().z-.1f)<1e-6f);
 doors.Update(1,near,true,true,instances,collision);assert(instances[0].modelMatrix==open); // held square doesn't repeat
 doors.Update(0,near,false,true,instances,collision);doors.Update(0,near,true,true,instances,collision);
 TriggerManager::Box obstruct{{-.05f,0,-.8f},{.1f,1.6f,-.1f}};
 doors.Update(1,obstruct,false,true,instances,collision);assert(instances[0].modelMatrix==open);
 assert(doors.GetHudText().find("BLOCKED")!=std::string::npos);
 doors.Update(2,far,false,true,instances,collision);auto closed=instances[0].modelMatrix;
 assert(std::abs(closed[0][0]-1)<1e-6f&&std::abs(closed[0][2])<1e-6f);
 player.SetPosition(.5f,0,.1f);collision.computeCollision(&player);assert(std::abs(player.GetPosition().z-.1f)>.05f);
 puts("PASS doors: malformed/stale rejection, permission/button edge, delay, hinge/bounds, moving collision, blocked closing, noclip");
}
