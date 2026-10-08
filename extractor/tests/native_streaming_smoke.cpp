#include "../tlou_extractor/NativeStreaming.h"
#include <iostream>
using namespace TlouStreaming;
int main(int argc,char** argv){
    if(argc!=3)return 2;
    auto world=World::Load(argv[1]);std::ifstream input(argv[2]);
    unsigned n;input>>n;std::vector<Id> taskIds(n);for(auto& id:taskIds)input>>id;
    int phase;Point point;
    while(input>>phase>>point[0]>>point[1]>>point[2]){
        StoryState state;
        for(Id task:taskIds)state.tasks[{Hash("home"),task}]=phase==1?TaskStatus::Complete:TaskStatus::Pending;
        if(phase>=2)state.tasks[{Hash("home"),Hash("hom-house-daughter-room")}]=TaskStatus::Active;
        state.spawned[0x69c85a6du]=phase==3;
        state.booleans[{0x4f12da44u,0x69c85a6du}]=phase==3;
        auto s=world.Select(point,[&](Id f,const std::vector<Id>& a){return state.Ask(f,a);});
        std::cout<<s.region<<" "<<s.variant;
        for(auto i:s.display)std::cout<<" "<<world.levels[i].name;
        std::cout<<" |";for(auto i:s.resident)std::cout<<" "<<world.levels[i].name;
        std::cout<<"\n";
        if(s.region>=0){Planner planner;auto pending=planner.Update(world,s,{});if(!pending.waiting || !pending.show.empty())return 3;
            auto ready=world.Required(s);auto actions=planner.Update(world,s,ready);if(actions.waiting || actions.show!=s.display)return 4;}
    }
}
