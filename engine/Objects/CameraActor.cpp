#include "CameraActor.h"
#include <psp2/ctrl.h>
#include <psp2common/ctrl.h>
#include <cmath>
#include <algorithm>

void CameraActor::Update(float deltaTime) {
    // A native cinematic camera is set by its track, never by orbit follow.
    if (m_control.cameraPose == PoseOwner::Gameplay) Actor::Update(deltaTime);

    SceCtrlData pad;
    sceCtrlPeekBufferPositive(0, &pad, 1);

    // Нормализация стиков (-1.0f ... 1.0f)
    float lx = (pad.lx - 128.0f) / 128.0f;
    float ly = (pad.ly - 128.0f) / 128.0f;
    float rx = (pad.rx - 128.0f) / 128.0f;
    float ry = (pad.ry - 128.0f) / 128.0f;

    // Мертвая зона стиков
    const float deadzone = 0.18f;
    if (std::abs(lx) < deadzone) lx = 0.0f;
    if (std::abs(ly) < deadzone) ly = 0.0f;
    if (std::abs(rx) < deadzone) rx = 0.0f;
    if (std::abs(ry) < deadzone) ry = 0.0f;

    // Переключение режимов по кнопке SELECT (Toggle)
    if (!m_control.cameraLook) rx = ry = 0.f;
    if (!m_control.movement) lx = ly = 0.f;
    const bool selectPressed = (pad.buttons & SCE_CTRL_SELECT) != 0;
    if (m_control.cameraPose == PoseOwner::Cinematic) {
        m_selectWasPressed = selectPressed;
        return;
    }
    if (selectPressed && !m_selectWasPressed && m_control.debugCamera) {
        m_mode = (m_mode == CameraMode::ThirdPerson) ? CameraMode::Spectate : CameraMode::ThirdPerson;
    }
    m_selectWasPressed = selectPressed;

    if (m_mode == CameraMode::Spectate) {
        UpdateSpectate(deltaTime, lx, ly, rx, ry, m_control.movement ? pad.buttons : 0);
    } else {
        UpdateThirdPerson(deltaTime, rx, ry);
    }
}

void CameraActor::UpdateSpectate(float deltaTime, float lx, float ly, float rx, float ry, unsigned int buttons) {
    // Вращение камеры спектатора
    m_yaw   -= rx * deltaTime * 85.0f;
    m_pitch -= ry * deltaTime * 85.0f;
    m_pitch = std::clamp(m_pitch, -85.0f, 85.0f);

    m_rotation = TLOU::Vector3(m_pitch, m_yaw, 0.0f);

    // Перемещение спектатора
    float speed = 6.0f;
    if (buttons & SCE_CTRL_SQUARE) speed *= 2.0f; // Ускорение при зажатии Квадрата

    m_position += GetRightVector() * (lx * speed * deltaTime);
    m_position += GetForwardVector() * (-ly * speed * deltaTime);

    // Подъем/спуск на L/R
    if (buttons & SCE_CTRL_RTRIGGER) m_position.y += speed * deltaTime;
    if (buttons & SCE_CTRL_LTRIGGER) m_position.y -= speed * deltaTime;
}

void CameraActor::UpdateThirdPerson(float deltaTime, float rx, float ry) {
    if (!m_target) return;

    // Обновление углов обзора с правого стика
    m_yaw   -= rx * deltaTime * 80.0f;
    m_pitch -= ry * deltaTime * 70.0f;

    // Ограничение угла наклона вверх/вниз как в TLoU
    m_pitch = std::clamp(m_pitch, -45.0f, 60.0f);

    m_rotation = TLOU::Vector3(m_pitch, m_yaw, 0.0f);

    // Расчет точки поворота (голова/плечи персонажа)
    TLOU::Vector3 targetPivot = m_target->GetPosition() + TLOU::Vector3(0.0f, m_targetHeight, 0.0f);

    // Векторы ориентации камеры
    TLOU::Vector3 forward = GetForwardVector();
    TLOU::Vector3 right   = GetRightVector();
    TLOU::Vector3 up      = TLOU::Vector3(0.0f, 1.0f, 0.0f);

    // Позиция из-за правого плеча
    TLOU::Vector3 desiredPosition = targetPivot
        - (forward * m_distance)
        + (right * m_shoulderOffset.x)
        + (up * m_shoulderOffset.y);

    // Плавное следование камеры
    m_position = m_position + (desiredPosition - m_position) * (m_followSpeed * deltaTime);
}