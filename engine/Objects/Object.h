#ifndef OBJECT_HPP
#define OBJECT_HPP

#include <cstdint>
#include <string>

namespace TLOU {

    using ObjectID = uint32_t;

    class Object {
    protected:
        // Глобальный счетчик для генерации уникальных ID
        static inline ObjectID s_nextID = 1;

        ObjectID m_id;              // Уникальный ID
        std::string m_name;         // Имя объекта для отладки/поиска
        bool m_isActive = true;     // Включен ли объект?
        bool m_pendingKill = false; // Помечен ли на удаление в конце кадра?

    public:
        Object(const std::string& name = "Object")
            : m_id(s_nextID++), m_name(name) {}

        virtual ~Object() = default;

        virtual void OnCreate() {}
        virtual void Update(float deltaTime) {}
        virtual void OnDestroy() {}

        void Destroy() {
            m_pendingKill = true;
        }

        bool IsPendingKill() const {
            return m_pendingKill;
        }

        ObjectID GetID() const { return m_id; }

        const std::string& GetName() const { return m_name; }
        void SetName(const std::string& name) { m_name = name; }

        bool IsActive() const { return m_isActive; }
        void SetActive(bool active) { m_isActive = active; }
    };

} // namespace TLOU

#endif // OBJECT_HPP