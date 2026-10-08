#include "Engine/InteractionProcess.h"
#include <cassert>
int main(){
 InteractionProcess process;InteractionProcess::MotionKey keys[]={{0,{0,0}},{2,{.4f,0}}};
 InteractionProcess::Plan plan{0,{1,0,0},-179,2,"test",keys,2};glm::vec3 position(0);float yaw=179;
 assert(process.Start(plan));assert(!process.Start(plan));
 process.Update(.05f,position,yaw);assert(position.x<=.061f);assert(yaw>179);assert(!process.BeginPlayback(position,yaw));
 for(int i=0;i<100&&process.GetState()!=InteractionProcess::State::Ready;++i)process.Update(.05f,position,yaw);
 assert(process.GetState()==InteractionProcess::State::Ready);
 position.x-=.5f;assert(!process.BeginPlayback(position,yaw)); // Collision displaced actor after tentative arrival.
 position.x=1;assert(process.BeginPlayback(position,yaw));process.Update(1,position,yaw);assert(process.Active());
 process.Update(2,position,yaw);assert(process.GetState()==InteractionProcess::State::Finished);
 assert(process.Start(plan));position={0,0,0};
 for(int i=0;i<110;++i){process.Update(.05f,position,yaw);position={0,0,0};} // A blocked approach never teleports.
 assert(process.GetState()==InteractionProcess::State::Cancelled);
}
