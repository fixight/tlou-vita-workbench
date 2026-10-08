#ifndef ACTOR_HPP
#define ACTOR_HPP

#include "Object.h"
#include "Math3D.h"
#include <vector>
#include <algorithm>
#include <string>

#include "glm/ext/matrix_transform.hpp"

namespace TLOU {

// Предварительные объявления
class Actor;
class Renderer;

// =========================================================================
// 1. БАЗОВЫЙ КЛАСС КОМПОНЕНТА
// =========================================================================
class Component : public Object {
protected:
    Actor* m_owner = nullptr; // Актер-владелец этого компонента

public:
    Component(Actor* owner, const std::string& name = "Component")
        : Object(name), m_owner(owner) {}

    virtual ~Component() = default;

    Actor* GetOwner() const { return m_owner; }

    // Переопределяется у графических компонентов
    virtual void Render(Renderer& renderer) {}
};

// =========================================================================
// 2. КЛАСС АКТЕРА
// =========================================================================
class Actor : public Object {
protected:
    // --- TRANSFORM (Пространственные свойства в 3D-мире) ---
    Vector3 m_position = Vector3::Zero(); // Позиция (X, Y, Z)
    Vector3 m_rotation = Vector3::Zero(); // Поворот в градусах (Pitch, Yaw, Roll)
    Vector3 m_scale    = Vector3::One();  // Масштаб (ScaleX, ScaleY, ScaleZ)

    // --- ФИЗИКА И ДВИЖЕНИЕ --- [ДОБАВЛЕНО]
    Vector3 m_velocity   = Vector3::Zero(); // Линейная скорость актера
    bool    m_isGrounded = false;           // Находится ли актер на земле

    // --- КОМПОНЕНТЫ ---
    std::vector<Component*> m_components;

public:
    Actor(const std::string& name = "Actor")
        : Object(name) {}

    virtual ~Actor() {
        for (auto* comp : m_components) {
            delete comp;
        }
        m_components.clear();
    }

    // =========================================================================
    // ЖИЗНЕННЫЙ ЦИКЛ АКТЕРА
    // =========================================================================

    void OnCreate() override {
        Object::OnCreate();
    }

    void Update(float deltaTime) override {
        if (!IsActive()) return;

        Object::Update(deltaTime);

        // [ДОБАВЛЕНО] Перемещение актера по вектору скорости
        m_position += m_velocity * deltaTime;

        // Вызов Update у всех компонентов
        for (auto* comp : m_components) {
            if (comp && comp->IsActive()) {
                comp->Update(deltaTime);
            }
        }
    }

    virtual void Render(Renderer& renderer) {
        if (!IsActive()) return;

        for (auto* comp : m_components) {
            if (comp && comp->IsActive()) {
                comp->Render(renderer);
            }
        }
    }

    void OnDestroy() override {
        for (auto* comp : m_components) {
            if (comp) {
                comp->OnDestroy();
            }
        }
        Object::OnDestroy();
    }

    // =========================================================================
    // ДВИЖЕНИЕ И МОДИФИКАЦИЯ (TRANSFORM METHODS)
    // =========================================================================

    const Vector3& GetPosition() const { return m_position; }
    void SetPosition(const Vector3& pos) { m_position = pos; }
    void SetPosition(float x, float y, float z) { m_position = Vector3(x, y, z); }

    void Translate(const Vector3& delta) { m_position += delta; }
    void Translate(float dx, float dy, float dz) { m_position += Vector3(dx, dy, dz); }

    const Vector3& GetRotation() const { return m_rotation; }
    void SetRotation(const Vector3& rot) { m_rotation = rot; }
    void SetRotation(float x, float y, float z) { m_rotation = Vector3(x, y, z); }

    void Rotate(const Vector3& deltaRot) { m_rotation += deltaRot; }
    void Rotate(float dx, float dy, float dz) { m_rotation += Vector3(dx, dy, dz); }

    const Vector3& GetScale() const { return m_scale; }
    void SetScale(const Vector3& scale) { m_scale = scale; }
    void SetScale(float uniformScale) { m_scale = Vector3(uniformScale); }

    // --- [ДОБАВЛЕНО] МАТРИЦА МОДЕЛИ (MODEL MATRIX) ---
    glm::mat4 GetModelMatrix() const {
        glm::mat4 model = glm::mat4(1.0f); // Единичная матрица

        // 1. Translation (Смещение)
        model = glm::translate(model, glm::vec3(m_position.x, m_position.y, m_position.z));

        // 2. Rotation (Поворот Yaw -> Pitch -> Roll)
        model = glm::rotate(model, ToRadians(m_rotation.y), glm::vec3(0.0f, 1.0f, 0.0f)); // Y (Yaw)
        model = glm::rotate(model, ToRadians(m_rotation.x), glm::vec3(1.0f, 0.0f, 0.0f)); // X (Pitch)
        model = glm::rotate(model, ToRadians(m_rotation.z), glm::vec3(0.0f, 0.0f, 1.0f)); // Z (Roll)

        // 3. Scale (Масштаб)
        model = glm::scale(model, glm::vec3(m_scale.x, m_scale.y, m_scale.z));

        return model;
    }
    // =========================================================================
    // ФИЗИКА И СКОРОСТЬ [ДОБАВЛЕНО]
    // =========================================================================

    const Vector3& GetVelocity() const { return m_velocity; }
    void SetVelocity(const Vector3& vel) { m_velocity = vel; }
    void SetVelocity(float x, float y, float z) { m_velocity = Vector3(x, y, z); }

    void AddVelocity(const Vector3& deltaVel) { m_velocity += deltaVel; }
    void AddVelocity(float x, float y, float z) { m_velocity += Vector3(x, y, z); }

    bool IsGrounded() const { return m_isGrounded; }
    void SetGrounded(bool grounded) { m_isGrounded = grounded; }

    // =========================================================================
    // ВЕКТОРЫ НАПРАВЛЕНИЯ
    // =========================================================================

    Vector3 GetForwardVector() const {
        float radYaw   = ToRadians(m_rotation.y);
        float radPitch = ToRadians(m_rotation.x);
        return Vector3(
            -sinf(radYaw) * cosf(radPitch),
             sinf(radPitch),
            -cosf(radYaw) * cosf(radPitch)
        ).Normalized();
    }

    Vector3 GetRightVector() const {
        float radYaw = ToRadians(m_rotation.y);
        return Vector3(cosf(radYaw), 0.0f, -sinf(radYaw)).Normalized();
    }

    Vector3 GetUpVector() const {
        return GetRightVector().Cross(GetForwardVector()).Normalized();
    }

    // =========================================================================
    // МЕНЕДЖМЕНТ КОМПОНЕНТОВ
    // =========================================================================

    template<typename T, typename... Args>
    T* AddComponent(Args&&... args) {
        T* newComp = new T(this, std::forward<Args>(args)...);
        m_components.push_back(newComp);
        newComp->OnCreate();
        return newComp;
    }

    template<typename T>
    T* GetComponent() {
        for (auto* comp : m_components) {
            T* target = dynamic_cast<T*>(comp);
            if (target) return target;
        }
        return nullptr;
    }

    template<typename T>
    bool RemoveComponent() {
        for (auto it = m_components.begin(); it != m_components.end(); ++it) {
            T* target = dynamic_cast<T*>(*it);
            if (target) {
                (*it)->OnDestroy();
                delete *it;
                m_components.erase(it);
                return true;
            }
        }
        return false;
    }
};

} // namespace TLOU

#endif // ACTOR_HPP