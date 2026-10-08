#include "DoorManager.h"
#include "Managers/CollisionManager.h"
#include <glm/gtc/matrix_transform.hpp>
#include <psp2/kernel/clib.h>
#include <fstream>
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <unordered_set>

namespace {
class Reader {
    std::ifstream file;
public:
    explicit Reader(const char* path):file(path,std::ios::binary) {
        if (!file) throw std::runtime_error("door file missing");
    }
    template<class T> T Read() {
        T value{};
        if (!file.read(reinterpret_cast<char*>(&value),sizeof(value)))
            throw std::runtime_error("truncated door data");
        return value;
    }
    float Float() {
        const float value=Read<float>();
        if (!std::isfinite(value)) throw std::runtime_error("non-finite door data");
        return value;
    }
    glm::vec3 Point() { float x=Float(),y=Float(),z=Float(); return {x,y,z}; }
    unsigned Count(unsigned limit) {
        unsigned value=Read<uint32_t>();
        if (value>limit) throw std::runtime_error("door count bounds");
        return value;
    }
    std::string Text() {
        std::string value(Count(1024),'\0');
        if (!file.read(value.data(),value.size())) throw std::runtime_error("door string");
        return value;
    }
    bool End() { return file.peek()==std::char_traits<char>::eof(); }
};
uint64_t LevelHash(const char* path) {
    std::ifstream file(path,std::ios::binary);
    if (!file) throw std::runtime_error("door level missing");
    uint64_t hash=14695981039346656037ull;
    char buffer[4096];
    while (file.read(buffer,sizeof(buffer)) || file.gcount())
        for (std::streamsize i=0;i<file.gcount();++i)
            hash=(hash^static_cast<unsigned char>(buffer[i]))*1099511628211ull;
    return hash;
}
bool Overlap(const TriggerManager::Box& a,const TriggerManager::Box& b) {
    for (unsigned i=0;i<3;++i) if (a.max[i]<b.min[i] || a.min[i]>b.max[i]) return false;
    return true;
}
glm::mat4 DoorTransform(const glm::vec3& pivot,float angle) {
    return glm::translate(glm::mat4(1),pivot)*
           glm::rotate(glm::mat4(1),angle,glm::vec3(0,1,0))*
           glm::translate(glm::mat4(1),-pivot);
}
AABB TransformBounds(const AABB& closed,const glm::mat4& transform) {
    AABB result=closed;
    result.minBounds=glm::vec3(1e30f);result.maxBounds=glm::vec3(-1e30f);
    for (unsigned corner=0;corner<8;++corner) {
        glm::vec3 point((corner&1)?closed.maxBounds.x:closed.minBounds.x,
                        (corner&2)?closed.maxBounds.y:closed.minBounds.y,
                        (corner&4)?closed.maxBounds.z:closed.minBounds.z);
        point=glm::vec3(transform*glm::vec4(point,1));
        result.minBounds=glm::min(result.minBounds,point);
        result.maxBounds=glm::max(result.maxBounds,point);
    }
    return result;
}
}

bool DoorManager::Load(const char* sidecar,const char* levelPath,
                       std::vector<Instance>& instances,CollisionManager& collision) {
    if (!m_doors.empty()) return false;
    try {
        Reader reader(sidecar);
        if (reader.Read<uint32_t>()!=0x524f4456 || reader.Read<uint32_t>()!=1)
            throw std::runtime_error("VDOR header");
        const unsigned expectedInstances=reader.Read<uint32_t>();
        const unsigned expectedCollision=reader.Read<uint32_t>();
        const uint64_t expectedHash=reader.Read<uint64_t>();
        if (expectedInstances!=instances.size() || expectedCollision!=collision.GetTriangleCount() ||
            expectedHash!=LevelHash(levelPath)) throw std::runtime_error("doors belong to another level");
        const unsigned count=reader.Count(64);
        std::vector<Door> parsed;
        std::vector<unsigned> removed;
        std::unordered_set<unsigned> assignedParts,assignedCollision;
        std::unordered_set<std::string> identifiers;
        for (unsigned i=0;i<count;++i) {
            Door door;door.id=reader.Text();door.name=reader.Text();
            if (door.id.empty() || !identifiers.insert(door.id).second)
                throw std::runtime_error("duplicate door ID");
            door.pivot=reader.Point();door.angle=glm::radians(reader.Float());
            door.duration=reader.Float();door.delay=reader.Float();
            if (std::abs(door.angle)<.01f || std::abs(door.angle)>glm::radians(180.f) ||
                door.duration<=0 || door.duration>30 || door.delay<0 || door.delay>10)
                throw std::runtime_error("door motion bounds");
            const unsigned volumes=reader.Count(32);
            if (!volumes) throw std::runtime_error("door without interaction volume");
            for (unsigned v=0;v<volumes;++v) {
                const glm::vec3 lo=reader.Point(),hi=reader.Point();
                TriggerManager::Box box{{lo.x,lo.y,lo.z},{hi.x,hi.y,hi.z}};
                for (unsigned axis=0;axis<3;++axis) if (box.min[axis]>box.max[axis])
                    throw std::runtime_error("door interaction bounds");
                door.volumes.push_back(box);
            }
            const unsigned parts=reader.Count(128);
            if (!parts) throw std::runtime_error("door without geometry");
            glm::vec3 lo(1e30f),hi(-1e30f);
            for (unsigned p=0;p<parts;++p) {
                const unsigned index=reader.Read<uint32_t>();
                if (index>=instances.size() || !assignedParts.insert(index).second)
                    throw std::runtime_error("door instance index");
                const auto& instance=instances[index];
                door.parts.push_back({index,instance.modelMatrix,instance.boundingBox});
                lo=glm::min(lo,instance.boundingBox.minBounds);hi=glm::max(hi,instance.boundingBox.maxBounds);
            }
            door.center=(lo+hi)*.5f;
            const unsigned staticCount=reader.Count(4096);
            for (unsigned t=0;t<staticCount;++t) {
                const unsigned index=reader.Read<uint32_t>();
                if (index>=expectedCollision || !assignedCollision.insert(index).second)
                    throw std::runtime_error("door static collision index");
                removed.push_back(index);
            }
            const unsigned triangleCount=reader.Count(4096);
            if (!triangleCount) throw std::runtime_error("door without collider");
            for (unsigned t=0;t<triangleCount;++t) {
                Triangle triangle{reader.Point(),reader.Point(),reader.Point()};
                if (glm::length(glm::cross(triangle.b-triangle.a,triangle.c-triangle.a))<1e-8f)
                    throw std::runtime_error("degenerate door collider");
                door.collision.push_back(triangle);
            }
            parsed.push_back(std::move(door));
        }
        if (!reader.End()) throw std::runtime_error("door trailing data");
        // All validation precedes changes to the level's collision ownership.
        collision.RemoveTriangles(removed);
        for (Door& door:parsed) {
            door.firstCollision=collision.GetTriangleCount();
            for (const Triangle& tri:door.collision) collision.addTriangle(tri.a,tri.b,tri.c);
        }
        m_doors.swap(parsed);
        sceClibPrintf("DOORS: %u, transferred native triangles: %u\n",unsigned(m_doors.size()),unsigned(removed.size()));
        return true;
    } catch (const std::exception& error) {
        sceClibPrintf("Door load failed: %s\n",error.what());
        return false;
    }
}

void DoorManager::ApplyPose(Door& door,std::vector<Instance>& instances,CollisionManager& collision) {
    const glm::mat4 transform=DoorTransform(door.pivot,door.angle*door.amount);
    for (const Part& part:door.parts) {
        Instance& instance=instances[part.index];
        instance.modelMatrix=transform*part.closedMatrix;
        instance.boundingBox=TransformBounds(part.closedBounds,transform);
    }
    for (unsigned i=0;i<door.collision.size();++i) {
        const Triangle& tri=door.collision[i];
        collision.SetTriangle(door.firstCollision+i,
            glm::vec3(transform*glm::vec4(tri.a,1)),glm::vec3(transform*glm::vec4(tri.b,1)),
            glm::vec3(transform*glm::vec4(tri.c,1)));
    }
}

void DoorManager::Update(float deltaTime,const TriggerManager::Box& player,
                         bool buttonHeld,bool canInteract,std::vector<Instance>& instances,
                         CollisionManager& collision) {
    const bool pressed=buttonHeld&&!m_buttonHeld;m_buttonHeld=buttonHeld;
    const glm::vec3 playerCenter((player.min[0]+player.max[0])*.5f,
        (player.min[1]+player.max[1])*.5f,(player.min[2]+player.max[2])*.5f);
    int focus=-1;float bestDistance=1e30f;
    for (unsigned index=0;index<m_doors.size();++index) {
        Door& door=m_doors[index];
        if (door.moving && !door.nativePlaying) {
            const float nextTime=door.elapsed+std::max(0.f,deltaTime);
            const float phase=std::max(0.f,std::min(1.f,nextTime/door.duration));
            const float smooth=phase*phase*(3-2*phase);
            const float nextAmount=door.from+(door.target-door.from)*smooth;
            door.blocked=false;
            if (door.target<door.from) {
                const glm::mat4 nextTransform=DoorTransform(door.pivot,door.angle*nextAmount);
                const glm::mat4 currentTransform=DoorTransform(door.pivot,door.angle*door.amount);
                for (const Part& part:door.parts) {
                    AABB bounds=TransformBounds(part.closedBounds,nextTransform);
                    const AABB current=TransformBounds(part.closedBounds,currentTransform);
                    bounds.minBounds=glm::min(bounds.minBounds,current.minBounds);
                    bounds.maxBounds=glm::max(bounds.maxBounds,current.maxBounds);
                    if (Overlap(player,{{bounds.minBounds.x,bounds.minBounds.y,bounds.minBounds.z},
                                       {bounds.maxBounds.x,bounds.maxBounds.y,bounds.maxBounds.z}})) {
                        door.blocked=true;break;
                    }
                }
            }
            if (!door.blocked) {
                door.elapsed=nextTime;
                if (nextAmount!=door.amount) {door.amount=nextAmount;ApplyPose(door,instances,collision);}
                if (phase>=1) door.moving=false;
            }
        }
        if (canInteract) for (const auto& volume:door.volumes) if (Overlap(player,volume)) {
            const glm::vec3 offset=door.center-playerCenter;
            const float distance=glm::dot(offset,offset);
            if (distance<bestDistance) {focus=index;bestDistance=distance;}
            break;
        }
    }
    if (pressed && focus>=0 && !m_doors[focus].moving && !m_doors[focus].awaiting) {
        Door& door=m_doors[focus];
        door.from=door.amount;door.target=door.amount<.5f?1.f:0.f;
        if(door.target>door.from && !door.interactionClip.empty()) {
            door.awaiting=true;m_processPending=focus;
        } else {
        if (door.target>door.from) {
            // Swing away from the player; the closed pose itself is unchanged.
            const glm::vec3 tangent=door.center-door.pivot;
            const float toward=glm::dot(glm::cross(glm::vec3(0,1,0),tangent),playerCenter-door.center);
            door.angle=std::abs(door.angle)*(toward>0?-1.f:1.f);
        }
        door.elapsed=-door.delay;door.moving=true;
        // Closing stays a procedural collision-safe action; opening clips
        // are not replayed backwards as invented closing animations.
        if(door.target>door.from) {m_interactionPending=true;m_interactionTarget=door.center;}
        }
        sceClibPrintf("Door use: %s -> %s\n",door.id.c_str(),door.target>0?"OPEN":"CLOSE");
    }
    const int state=focus<0?-1:(m_doors[focus].blocked?3:(m_doors[focus].moving || m_doors[focus].awaiting)?2:m_doors[focus].amount>.5f?1:0);
    if (focus!=m_focus || state!=m_lastHudState) {
        m_hudText.clear();m_focus=focus;m_lastHudState=state;
        if (focus>=0) {
            std::string label=m_doors[focus].name.substr(0,40);
            for(char& c:label) if(static_cast<unsigned char>(c)<32 || static_cast<unsigned char>(c)>126)c='?';
            m_hudText="DOOR: "+label+"\n";
            m_hudText+=state==3?"CLOSING BLOCKED - MOVE AWAY\n":state==2?"DOOR MOVING\n":state==1?"[SQUARE] CLOSE\n":"[SQUARE] OPEN\n";
        }
    }
}

bool DoorManager::ConsumeInteraction(glm::vec3& target) {
    if (!m_interactionPending) return false;
    m_interactionPending=false;target=m_interactionTarget;return true;
}

bool DoorManager::LoadInteractions(const char* sidecar,const char* levelPath) {
    try {
        Reader reader(sidecar);
        if(reader.Read<uint32_t>()!=0x50494456 || reader.Read<uint32_t>()!=1 ||
           reader.Read<uint64_t>()!=LevelHash(levelPath))throw std::runtime_error("VDIP header/level");
        const unsigned count=reader.Count(64);
        struct Profile {unsigned index;std::string clip;glm::vec3 entry;float yaw,duration;
            std::vector<InteractionProcess::MotionKey> motion;std::vector<float> angles;};
        std::vector<Profile> parsed;std::unordered_set<unsigned> seen;
        for(unsigned i=0;i<count;++i) {
            const std::string id=reader.Text();Profile profile{};
            auto found=std::find_if(m_doors.begin(),m_doors.end(),[&](const Door& d){return d.id==id;});
            if(found==m_doors.end())throw std::runtime_error("interaction door missing");
            profile.index=unsigned(found-m_doors.begin());
            if(!seen.insert(profile.index).second)throw std::runtime_error("duplicate interaction door");
            profile.clip=reader.Text();profile.entry=reader.Point();profile.yaw=reader.Float();profile.duration=reader.Float();
            const unsigned keys=reader.Count(10000);
            if(profile.clip.empty() || keys<2 || profile.duration<=0 || profile.duration>30)
                throw std::runtime_error("interaction profile bounds");
            for(unsigned k=0;k<keys;++k) {
                const float time=reader.Float(),angle=reader.Float(),x=reader.Float(),z=reader.Float();
                if((k==0 && std::abs(time)>.001f) || (k && time<=profile.motion.back().time) ||
                   time>profile.duration+.001f || std::abs(angle)>glm::radians(180.f) || std::abs(x)>10 || std::abs(z)>10)
                    throw std::runtime_error("interaction key bounds");
                profile.motion.push_back({time,{x,z}});profile.angles.push_back(angle);
            }
            if(std::abs(profile.motion.back().time-profile.duration)>.001f ||
               std::abs(profile.angles.front())>.001f)throw std::runtime_error("interaction endpoints");
            parsed.push_back(std::move(profile));
        }
        if(!reader.End())throw std::runtime_error("interaction trailing data");
        for(auto& p:parsed) {
            Door& door=m_doors[p.index];door.interactionClip=std::move(p.clip);
            door.entry=p.entry;door.entryYaw=p.yaw;door.clipDuration=p.duration;
            door.motion=std::move(p.motion);door.angles=std::move(p.angles);
        }
        sceClibPrintf("Door interaction profiles: %u\n",count);return true;
    } catch(const std::exception& error) {
        sceClibPrintf("Door interaction load failed: %s\n",error.what());return false;
    }
}

bool DoorManager::ConsumeProcess(InteractionProcess::Plan& plan) {
    if(m_processPending<0)return false;
    const unsigned index=unsigned(m_processPending);m_processPending=-1;
    const Door& door=m_doors[index];
    plan={index,door.entry,door.entryYaw,door.clipDuration,door.interactionClip.c_str(),door.motion.data(),unsigned(door.motion.size())};
    return true;
}
bool DoorManager::BeginProcess(unsigned object) {
    if(object>=m_doors.size() || !m_doors[object].awaiting)return false;
    Door& door=m_doors[object];door.awaiting=false;door.nativePlaying=true;door.moving=true;
    door.amount=0;door.elapsed=0;m_lastHudState=-1;return true;
}
void DoorManager::CancelProcess(unsigned object) {
    if(object>=m_doors.size())return;
    Door& door=m_doors[object];if(!door.awaiting && !door.nativePlaying)return;
    door.awaiting=false;door.nativePlaying=false;door.moving=false;
    m_lastHudState=-1;
}
void DoorManager::SampleProcess(unsigned object,float time,std::vector<Instance>& instances,CollisionManager& collision) {
    if(object>=m_doors.size())return;
    Door& door=m_doors[object];if(!door.nativePlaying || door.motion.empty())return;
    time=std::max(0.f,std::min(time,door.clipDuration));
    unsigned next=1;while(next<door.motion.size() && door.motion[next].time<time)++next;
    const unsigned a=std::min(next-1,unsigned(door.motion.size()-1)),b=std::min(next,unsigned(door.motion.size()-1));
    const float span=door.motion[b].time-door.motion[a].time;
    const float weight=span>0?(time-door.motion[a].time)/span:0;
    const float angle=door.angles[a]*(1-weight)+door.angles[b]*weight;
    // ApplyPose uses angle * amount. Retain the final signed native swing for closing.
    door.angle=door.angles.back();door.amount=std::abs(door.angle)>1e-6f?angle/door.angle:0;
    ApplyPose(door,instances,collision);door.elapsed=time;
    if(time>=door.clipDuration) {door.moving=false;door.nativePlaying=false;door.amount=1;}
}
