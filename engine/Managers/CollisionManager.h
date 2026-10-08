#pragma once

#include <glm/glm.hpp>
#include <vector>
#include <utility>

// Forward declaration вашего класса Actor
namespace TLOU {
    class Actor;
    class Vector3;
}

struct CollisionTriangle {
    glm::vec3 a, b, c;
    glm::vec3 normal;
    glm::vec3 minBounds; // Локальный AABB треугольника для быстрого отсева
    glm::vec3 maxBounds;
};

class CollisionManager {
public:
    void computeCollision(TLOU::Actor *actor);

    // Метод для загрузки меша коллизии из файла/блендера
    void addTriangle(const glm::vec3& a, const glm::vec3& b, const glm::vec3& c);
    void clear();
    // Принимаем уже рассчитанные треугольники без повторного расчёта нормалей.
    void SetPreparedTriangles(std::vector<CollisionTriangle>&& prepared) {
        triangles = std::move(prepared);
    }
    void RemoveTriangles(const std::vector<unsigned>& indices);
    void SetTriangle(unsigned index, const glm::vec3& a, const glm::vec3& b, const glm::vec3& c);
    size_t GetTriangleCount() const { return triangles.size(); }

private:
    std::vector<CollisionTriangle> triangles;

    // Математика поиска ближайшей точки на треугольнике
    glm::vec3 closestPointOnTriangle(const glm::vec3& p, const glm::vec3& a, const glm::vec3& b, const glm::vec3& c);
};