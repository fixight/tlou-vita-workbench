#ifndef TLOU_VITA_CHARACTER_H
#define TLOU_VITA_CHARACTER_H

#include "../System/DataLoader.h"
#include "Objects/Actor.h"
#include "CameraActor.h"
#include "Engine/SkinnedModel.h"
#include "Engine/InteractionProcess.h"
#include "Engine/PlayerControl.h"

class Character : public TLOU::Actor {
private:
    PlayerControl m_control{};
    Instance renderData{};
    CameraActor* m_camera = nullptr;

    // SK16: idle, walk, run; slot 3 is an optional validated interaction clip.
    enum class AnimationClip : unsigned { Idle = 0, Walk = 1, Run = 2, Door = 3 };
    SkinnedModel* m_skinnedModel = nullptr;
    AnimationClip m_animationClip = AnimationClip::Idle;
    float m_interactionRemaining = 0.f;
    InteractionProcess m_interaction;
    unsigned m_interactionClipIndex=0;
    bool m_sampledInteraction=false;
    float m_walkSpeed = 0.8f;
    float m_sprintSpeed = 4.5f;
    float m_turnSpeed = 8.0f;

public:
    Character(const std::string& name = "Player") : TLOU::Actor(name) {}

    void setSkinnedModel(SkinnedModel* model) {
        m_skinnedModel = model;
        renderData.skinned = model;
    }
    void setMesh(Mesh* mesh) { renderData.mesh = mesh; }
    void setMeshTexture(Texture* texture) { renderData.texture = texture; }

    void initModel() {
        glm::mat4 model = GetModelMatrix();

        // Ориентация экспортированного меша относительно контроллера.
        model = glm::rotate(model, glm::radians(180.0f), glm::vec3(0.0f, 1.0f, 0.0f));

        renderData.modelMatrix = model;
    }

    Instance GetRenderData() { return renderData; }

    void SetCamera(CameraActor* camera) {
        m_camera = camera;
        if (m_camera) {
            m_camera->SetTarget(this);
        }
    }

    void SetPlayerControl(const PlayerControl& policy);
    int FindAnimationClip(const char* name) const {
        return m_skinnedModel ? m_skinnedModel->FindClip(name) : -1;
    }
    // Resolve the clip index once when loading the scene. visualYaw is the
    // mesh's world yaw, before the controller's existing 180-degree correction.
    bool SampleCinematicPose(unsigned clipIndex, float timeSeconds,
        const TLOU::Vector3& position, float visualYaw, float deltaTime = 0.f);
    void Update(float deltaTime) override;
    void StartDoorInteraction(const glm::vec3& target);
    bool IsInteracting() const { return m_interactionRemaining > 0.f || m_interaction.Active(); }
    bool StartInteraction(const InteractionProcess::Plan& plan);
    bool BeginInteractionPlayback();
    const InteractionProcess& GetInteraction() const { return m_interaction; }
    bool SampledInteractionThisFrame() const { return m_sampledInteraction; }

private:
    void HandleMovement(float deltaTime);
};

#endif // TLOU_VITA_CHARACTER_H