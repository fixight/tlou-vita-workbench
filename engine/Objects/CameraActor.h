#ifndef TLOU_VITA_CAMERAACTOR_H
#define TLOU_VITA_CAMERAACTOR_H

#include "Objects/Actor.h"
#include "Engine/PlayerControl.h"
#include "Engine/CinematicLens.h"
#include <glm/gtc/quaternion.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <cmath>

enum class CameraMode {
    ThirdPerson, // Режим TLoU: из-за плеча персонажа
    Spectate     // Спектатор: свободный полет по комнате
};

class CameraActor : public TLOU::Actor {
private:
    PlayerControl m_control{};
    glm::quat m_cinematicRotation{1,0,0,0};
    float m_cinematicFov = 60;
    CinematicLens m_cinematicLens{};
    bool m_hasCinematicLens = false;
    bool m_selectWasPressed = false;
    CameraMode m_savedMode = CameraMode::ThirdPerson;
    CameraMode m_mode = CameraMode::ThirdPerson;
    TLOU::Actor* m_target = nullptr; // Персонаж, за которым следим

    // Углы обзора
    float m_pitch = 0.0f; // Вверх / вниз
    float m_yaw   = 0.0f; // Влево / вправо

    // Настройки TLoU камеры (вид из-за правого плеча)
    float m_distance        = 1.2f;                     // Дистанция назад
    TLOU::Vector3 m_shoulderOffset = TLOU::Vector3(0.35f, 0.2f, 0.0f); // Смещение вправо/вверх (плечо)
    float m_targetHeight    = 1.f;                     // Точка прицеливания (высота торса/головы)
    float m_followSpeed     = 10.0f;                    // Плавность следования

public:
    CameraActor(const std::string& name = "CameraActor")
        : TLOU::Actor(name) {}

    void SetPlayerControl(const PlayerControl& policy) {
        // Resume the orbit from the cinematic's last view, without stale angles.
        if (m_control.cameraPose == PoseOwner::Cinematic && policy.cameraPose == PoseOwner::Gameplay) {
            m_pitch = m_rotation.x;
            m_yaw = m_rotation.y;
        }
        if (m_control.debugCamera && !policy.debugCamera) m_savedMode = m_mode;
        if (!m_control.debugCamera && policy.debugCamera) m_mode = m_savedMode;
        if (!policy.debugCamera) m_mode = CameraMode::ThirdPerson;
        m_control = policy;
    }
    void SetCinematicPose(const glm::vec3& position, const glm::quat& rotation, float fov) {
        m_hasCinematicLens = false;
        m_cinematicLens = CinematicLens{};
        m_position = TLOU::Vector3(position.x,position.y,position.z);
        m_cinematicRotation = glm::normalize(rotation); m_cinematicFov = fov;
        const glm::vec3 forward = m_cinematicRotation * glm::vec3(0,0,-1);
        // Preserve the outgoing viewing direction for the gameplay orbit.
        m_rotation.x = glm::degrees(std::asin(std::clamp(forward.y,-1.f,1.f)));
        m_rotation.y = glm::degrees(std::atan2(-forward.x,-forward.z));
        m_rotation.z = 0;
    }
    void SetCinematicLens(const CinematicLens& lens) {
        m_hasCinematicLens = true;
        m_cinematicLens = lens;
        m_cinematicFov = lens.VerticalFov(960.f/544.f);
    }
    bool HasCinematicLens() const { return m_hasCinematicLens; }
    const CinematicLens& GetCinematicLens() const { return m_cinematicLens; }
    TLOU::Vector3 GetForwardVector() const {
        if (m_control.cameraPose != PoseOwner::Cinematic) return Actor::GetForwardVector();
        const auto v = m_cinematicRotation * glm::vec3(0,0,-1);
        return TLOU::Vector3(v.x,v.y,v.z);
    }
    glm::mat4 GetViewMatrix() const {
        const auto v = GetForwardVector();
        const glm::vec3 eye(m_position.x,m_position.y,m_position.z);
        const glm::vec3 up = m_control.cameraPose == PoseOwner::Cinematic
            ? m_cinematicRotation * glm::vec3(0,1,0) : glm::vec3(0,1,0);
        return glm::lookAt(eye,eye+glm::vec3(v.x,v.y,v.z),up);
    }
    glm::mat4 GetProjectionMatrix() const {
        const bool cinematic = m_control.cameraPose == PoseOwner::Cinematic;
        return glm::perspective(glm::radians(cinematic ? m_cinematicFov : 45.f),
                                960.f/544.f, cinematic ? .03f : .5f, 150.f);
    }
    void SetTarget(TLOU::Actor* target) { m_target = target; }
    void SetMode(CameraMode mode) { m_mode = mode; }
    CameraMode GetMode() const { return m_mode; }

    float GetYaw() const { return m_yaw; }
    float GetPitch() const { return m_pitch; }

    void Update(float deltaTime) override;

private:
    void UpdateSpectate(float deltaTime, float lx, float ly, float rx, float ry, unsigned int buttons);
    void UpdateThirdPerson(float deltaTime, float rx, float ry);
};

#endif // TLOU_VITA_CAMERAACTOR_H