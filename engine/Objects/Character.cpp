#include "Character.h"
#include <psp2/ctrl.h>
#include <psp2common/ctrl.h>
#include <cmath>

void Character::StartDoorInteraction(const glm::vec3& target) {
    const float dx = target.x - m_position.x, dz = target.z - m_position.z;
    if (dx*dx + dz*dz > 0.0001f)
        m_rotation.y = TLOU::ToDegrees(std::atan2(-dx, -dz));
    m_velocity.x = m_velocity.z = 0.f;
    const float clipDuration = m_skinnedModel ? m_skinnedModel->GetClipDuration(3) : 0.f;
    m_interactionRemaining = clipDuration > 0.f ? clipDuration : 1.45f;
}

void Character::SetPlayerControl(const PlayerControl& policy) {
    if (policy.characterPose == PoseOwner::Cinematic && m_control.characterPose != policy.characterPose) {
        m_interaction.Cancel();
        m_interactionRemaining = 0.f;
    }
    m_control = policy;
    if (!m_control.CanMove()) m_velocity = TLOU::Vector3::Zero();
}

bool Character::SampleCinematicPose(unsigned clipIndex, float timeSeconds,
    const TLOU::Vector3& position, float visualYaw, float deltaTime) {
    if (m_control.characterPose != PoseOwner::Cinematic || !m_skinnedModel) return false;
    const float duration = m_skinnedModel->GetClipDuration(clipIndex);
    if (duration <= 0.f || !std::isfinite(timeSeconds) || !std::isfinite(visualYaw) ||
        !std::isfinite(position.x) || !std::isfinite(position.y) || !std::isfinite(position.z) ||
        !std::isfinite(deltaTime) || deltaTime < 0.f) return false;
    m_position = position;
    m_rotation.y = visualYaw - 180.f;
    m_velocity = TLOU::Vector3::Zero();
    m_skinnedModel->SampleAt(clipIndex, std::clamp(timeSeconds, 0.f, duration), deltaTime);
    initModel();
    return true;
}

void Character::Update(float deltaTime) {
    m_sampledInteraction=false;
    // The cinematic player samples the pose and world transform separately.
    // Do not replace that pose with idle, apply gravity, or cancel it in noclip.
    if (m_control.characterPose == PoseOwner::Cinematic) {
        m_velocity = TLOU::Vector3::Zero();
        initModel();
        return;
    }
    // Spectate is the existing noclip mode: freeze the player, including velocity.
    if (m_camera && m_camera->GetMode() == CameraMode::Spectate) {
        m_interaction.Cancel();m_interactionRemaining=0;
        m_velocity = TLOU::Vector3::Zero();
        initModel();
        return;
    }
    if(m_interaction.Active()) {
        m_velocity=TLOU::Vector3::Zero();
        glm::vec3 position(m_position.x,m_position.y,m_position.z);
        float visualYaw=m_rotation.y+180.f;
        const bool playing=m_interaction.GetState()==InteractionProcess::State::Playing;
        m_interaction.Update(deltaTime,position,visualYaw);
        m_position=TLOU::Vector3(position.x,position.y,position.z);
        m_rotation.y=visualYaw-180.f;
        if(!playing && !m_isGrounded)m_position.y-=.6f*deltaTime;
        if(m_skinnedModel) {
            if(playing) {
                m_skinnedModel->SampleAt(m_interactionClipIndex,m_interaction.PlaybackTime(),deltaTime);
                m_sampledInteraction=true;
            } else m_skinnedModel->Update(deltaTime,
                m_interaction.GetState()==InteractionProcess::State::Approach?1:0, true, .28f);
        }
        initModel();return;
    }
    const bool interacting = IsInteracting();
    const bool hasDoorClip = m_skinnedModel && m_skinnedModel->GetClipDuration(3) > 0.f;
    m_animationClip = interacting && hasDoorClip ? AnimationClip::Door : AnimationClip::Idle;
    Actor::Update(deltaTime);

    // Если камера в режиме от 3-го лица — управляем персонажем
    if (m_camera && m_camera->GetMode() == CameraMode::ThirdPerson && !interacting && m_control.CanMove()) {
        HandleMovement(deltaTime);
    }

    // Поправка по высоте; разрешение коллизий выполняет движок.
    if (!m_isGrounded) {
        m_position.y -= 0.6f * deltaTime;
    }

    initModel();
    // Контроллер выбирает клип, проигрыватель вычисляет текущую позу.
    if (m_skinnedModel) {
        m_skinnedModel->Update(deltaTime, static_cast<unsigned>(m_animationClip), !(interacting && hasDoorClip), interacting ? .18f : .28f);
    }
    m_interactionRemaining = std::max(0.f, m_interactionRemaining - deltaTime);
}

void Character::HandleMovement(float deltaTime) {
    SceCtrlData pad;
    sceCtrlPeekBufferPositive(0, &pad, 1);

    float stickX = (pad.lx - 128.0f) / 128.0f;
    float stickY = (pad.ly - 128.0f) / 128.0f;

    const float deadzone = 0.18f;
    if (std::abs(stickX) < deadzone) {
        stickX = 0.0f;
    }
    if (std::abs(stickY) < deadzone) {
        stickY = 0.0f;
    }

    float inputMagnitude = std::sqrt(stickX * stickX + stickY * stickY);

    if (inputMagnitude > 0.05f) {
        // Угол камеры в радианах на плоскости XZ
        float cameraYawRad = TLOU::ToRadians(m_camera->GetYaw());

        // Базовые векторы камеры в горизонтальной плоскости (без наклона Pitch)
        TLOU::Vector3 cameraForward(-sinf(cameraYawRad), 0.0f, -cosf(cameraYawRad));
        TLOU::Vector3 cameraRight(cosf(cameraYawRad), 0.0f, -sinf(cameraYawRad));

        // Направление перемещения в мировых координатах
        TLOU::Vector3 movementDirection = (cameraRight * stickX) + (cameraForward * (-stickY));
        movementDirection = movementDirection.Normalized();

        // Спринт по L1 / LTRIGGER
        const bool isSprinting = (pad.buttons & SCE_CTRL_LTRIGGER) != 0;
        const float currentSpeed = isSprinting ? m_sprintSpeed : m_walkSpeed;
        m_animationClip = isSprinting ? AnimationClip::Run : AnimationClip::Walk;
        // Перемещение персонажа
        m_position += movementDirection * (currentSpeed * deltaTime);

        // Плавный разворот персонажа в сторону движения
        float targetYaw = TLOU::ToDegrees(atan2f(-movementDirection.x, -movementDirection.z));

        // Кратчайшая интерполяция угла (Lerp Angle)
        float yawDifference = targetYaw - m_rotation.y;
        while (yawDifference < -180.0f) {
            yawDifference += 360.0f;
        }
        while (yawDifference > 180.0f) {
            yawDifference -= 360.0f;
        }

        m_rotation.y += yawDifference * m_turnSpeed * deltaTime;
    }
}
bool Character::StartInteraction(const InteractionProcess::Plan& plan) {
    if(IsInteracting() || !m_skinnedModel)return false;
    const int clip=m_skinnedModel->FindClip(plan.clip);
    if(clip<0 || std::abs(m_skinnedModel->GetClipDuration(unsigned(clip))-plan.duration)>.05f)return false;
    if(!m_interaction.Start(plan))return false;
    m_interactionClipIndex=unsigned(clip);m_velocity=TLOU::Vector3::Zero();return true;
}
bool Character::BeginInteractionPlayback() {
    return m_interaction.BeginPlayback(glm::vec3(m_position.x,m_position.y,m_position.z),m_rotation.y+180.f);
}
