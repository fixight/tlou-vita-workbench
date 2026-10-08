#pragma once
#include <string>
#include <vector>
#include <glm/glm.hpp>
#include "System/DataLoader.h"
#include "Engine/TriggerManager.h"
#include "Engine/InteractionProcess.h"

class CollisionManager;

// Port interaction controller: overlap enables use; button starts a one-shot action.
// Door poses and colliders are driven together. Native script VM is not executed.
class DoorManager {
public:
    bool Load(const char* sidecar, const char* levelPath,
              std::vector<Instance>& instances, CollisionManager& collision);
    void Update(float deltaTime, const TriggerManager::Box& player,
                bool buttonHeld, bool canInteract, std::vector<Instance>& instances,
                CollisionManager& collision);
    bool LoadInteractions(const char* sidecar,const char* levelPath);
    bool ConsumeProcess(InteractionProcess::Plan& plan);
    bool BeginProcess(unsigned object);
    void CancelProcess(unsigned object);
    void SampleProcess(unsigned object,float time,std::vector<Instance>& instances,CollisionManager& collision);
    const std::string& GetHudText() const { return m_hudText; }
    bool ConsumeInteraction(glm::vec3& target);
    size_t GetDoorCount() const { return m_doors.size(); }
private:
    struct Triangle { glm::vec3 a,b,c; };
    struct Part { unsigned index; glm::mat4 closedMatrix; AABB closedBounds; };
    struct Door {
        std::string id,name;
        glm::vec3 pivot{},center{};
        float angle=0, duration=1, delay=0;
        std::vector<TriggerManager::Box> volumes;
        std::vector<Part> parts;
        std::vector<Triangle> collision;
        unsigned firstCollision=0;
        float amount=0, from=0, target=0, elapsed=0;
        bool moving=false, blocked=false, awaiting=false, nativePlaying=false;
        std::string interactionClip;
        glm::vec3 entry{};
        float entryYaw=0, clipDuration=0;
        std::vector<InteractionProcess::MotionKey> motion;
        std::vector<float> angles;
    };
    std::vector<Door> m_doors;
    std::string m_hudText;
    bool m_buttonHeld=false, m_interactionPending=false;
    glm::vec3 m_interactionTarget{};
    int m_focus=-1, m_lastHudState=-1, m_processPending=-1;
    void ApplyPose(Door& door, std::vector<Instance>& instances, CollisionManager& collision);
};
