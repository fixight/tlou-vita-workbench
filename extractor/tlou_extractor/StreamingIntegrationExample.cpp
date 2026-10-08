// Integration boundary: the engine implements Host using its existing loader,
// per-chunk render/collision ownership and shared-resource reference counts.
#include "NativeStreaming.h"
#include "HomeStory.h"

namespace TlouStreaming {
struct Host {
    virtual ~Host()=default;
    virtual bool Ready(Id resource) const=0;
    virtual void Request(Id resource,const Level& description)=0;
    virtual void Show(Id resource)=0;
    virtual void Hide(Id resource)=0;
    virtual void ReleaseIfUnreferenced(Id resource)=0;
};

struct AustinStreamer {
    World world=World::Load("app0:/assets/metadata/world-home.tltr");
    StoryState story=InitialHomeState();
    Planner planner;

    void Tick(const Point& cameraPosition,Host& host){
        auto target=world.Select(cameraPosition,[&](Id f,const std::vector<Id>& a){return story.Ask(f,a);});
        std::set<Id> ready;
        for(Id i=0;i<world.levels.size();++i)if(host.Ready(i))ready.insert(i);
        auto actions=planner.Update(world,target,ready);
        for(Id i:actions.load)host.Request(i,world.levels[i]);
        // Waiting leaves current visible chunks intact. Commit applies one set.
        for(Id i:actions.hide)host.Hide(i);
        for(Id i:actions.show)host.Show(i);
        for(Id i:actions.release)host.ReleaseIfUnreferenced(i);
    }

    void BeginTask(const std::string& task){story.SetTask("home",task,TaskStatus::Active);}
    void CompleteTask(const std::string& task){story.SetTask("home",task,TaskStatus::Complete);}
    void SarahEnteredCar(){story.SetSarahCarStarted();}
};
} // namespace TlouStreaming
