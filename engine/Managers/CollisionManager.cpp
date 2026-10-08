#include "CollisionManager.h"
#include <cmath>
#include <algorithm>

#include "Objects/Actor.h"

// Вспомогательная функция: ближайшая точка треугольника к сфер
glm::vec3 CollisionManager::closestPointOnTriangle(const glm::vec3& p, const glm::vec3& a, const glm::vec3& b, const glm::vec3& c) {
    glm::vec3 ab = b - a;
    glm::vec3 ac = c - a;
    glm::vec3 ap = p - a;

    float d1 = glm::dot(ab, ap);
    float d2 = glm::dot(ac, ap);
    if (d1 <= 0.0f && d2 <= 0.0f) return a;

    glm::vec3 bp = p - b;
    float d3 = glm::dot(ab, bp);
    float d4 = glm::dot(ac, bp);
    if (d3 >= 0.0f && d4 <= d3) return b;

    float vc = d1 * d4 - d3 * d2;
    if (vc <= 0.0f && d1 >= 0.0f && d3 <= 0.0f) {
        float v = d1 / (d1 - d3);
        return a + v * ab;
    }

    glm::vec3 cp = p - c;
    float d5 = glm::dot(ab, cp);
    float d6 = glm::dot(ac, cp);
    if (d6 >= 0.0f && d5 <= d6) return c;

    float vb = d5 * d2 - d1 * d6;
    if (vb <= 0.0f && d2 >= 0.0f && d6 <= 0.0f) {
        float w = d2 / (d2 - d6);
        return a + w * ac;
    }

    float va = d3 * d6 - d5 * d4;
    if (va <= 0.0f && (d4 - d3) >= 0.0f && (d5 - d6) >= 0.0f) {
        float w = (d4 - d3) / ((d4 - d3) + (d5 - d6));
        return b + w * (c - b);
    }

    float denom = 1.0f / (va + vb + vc);
    float v = vb * denom;
    float w = vc * denom;
    return a + ab * v + ac * w;
}

void CollisionManager::addTriangle(const glm::vec3& a, const glm::vec3& b, const glm::vec3& c) {
    CollisionTriangle tri;
    tri.a = a;
    tri.b = b;
    tri.c = c;
    tri.normal = glm::normalize(glm::cross(b - a, c - a));

    // Предрасчет AABB для моментального отсева на PS Vita
    tri.minBounds = glm::min(a, glm::min(b, c));
    tri.maxBounds = glm::max(a, glm::max(b, c));

    triangles.push_back(tri);
}

void CollisionManager::computeCollision(TLOU::Actor *actor) {
    auto tlouPos = actor->GetPosition();
    auto tlouVel = actor->GetVelocity();

    glm::vec3 actorPos(tlouPos.x, tlouPos.y, tlouPos.z);
    glm::vec3 actorVel(tlouVel.x, tlouVel.y, tlouVel.z);

    // Параметры коллайдера игрока
    const float playerRadius = 0.35f; // Радиус тела (35 см)
    const float playerHeight = 1.6f;  // Рост игрока

    actor->SetGrounded(false);

    // AABB игрока (для быстрого Broadphase-теста)
    glm::vec3 playerMin = actorPos - glm::vec3(playerRadius, 0.0f, playerRadius);
    glm::vec3 playerMax = actorPos + glm::vec3(playerRadius, playerHeight, playerRadius);

    // Центр сферы коллизии тела (находится на уровне груди)
    glm::vec3 sphereCenter = actorPos + glm::vec3(0.0f, playerRadius + 0.1f, 0.0f);

    // Делаем до 3 итераций (для идеальной обработки углов комнат)
    for (int iter = 0; iter < 3; ++iter) {
        for (const auto& tri : triangles) {

            // 1. БЫСТРЫЙ ОТСЕВ: если AABB игрока не пересекается с треугольником — пропускаем
            if (playerMax.x < tri.minBounds.x || playerMin.x > tri.maxBounds.x ||
                playerMax.y < tri.minBounds.y || playerMin.y > tri.maxBounds.y ||
                playerMax.z < tri.minBounds.z || playerMin.z > tri.maxBounds.z)
            {
                continue;
            }

            // 2. Точная проверка: Сфера против Треугольника
            glm::vec3 closest = closestPointOnTriangle(sphereCenter, tri.a, tri.b, tri.c);
            glm::vec3 diff = sphereCenter - closest;
            float distSq = glm::dot(diff, diff);

            // Если произошло проникновение
            if (distSq < (playerRadius * playerRadius) && distSq > 0.000001f) {
                float dist = std::sqrt(distSq);
                float penetration = playerRadius - dist;
                glm::vec3 normal = diff / dist;

                // Выталкиваем игрока
                actorPos += normal * penetration;
                sphereCenter += normal * penetration;

                // Обновляем AABB
                playerMin = actorPos - glm::vec3(playerRadius, 0.0f, playerRadius);
                playerMax = actorPos + glm::vec3(playerRadius, playerHeight, playerRadius);

                // Если поверхность горизонтальная (пол или склон до 45 градусов)
                if (normal.y > 0.7f) {
                    actor->SetGrounded(true);
                    if (actorVel.y < 0.0f) actorVel.y = 0.0f; // Гасим только падение вниз
                } else {
                    // Это СТЕНА: делаем плавное скольжение вдоль плоскости стены!
                    float dotVel = glm::dot(actorVel, normal);
                    if (dotVel < 0.0f) {
                        actorVel -= normal * dotVel; // Проекция вектора скорости
                    }
                }
            }
        }
    }

    // Применяем новые координаты и скорость
    actor->SetPosition(actorPos.x, actorPos.y, actorPos.z);
    actor->SetVelocity({actorVel.x, actorVel.y, actorVel.z});
}

void CollisionManager::clear() {
    // 1. Очищаем массив треугольников
    triangles.clear();

    // 2. Если у вас были старые AABB боксы — очищаем и и
    //collisions.clear();
}
void CollisionManager::RemoveTriangles(const std::vector<unsigned>& indices) {
    std::vector<bool> removed(triangles.size(),false);
    for (unsigned index:indices) if (index<removed.size()) removed[index]=true;
    size_t index=0;
    triangles.erase(std::remove_if(triangles.begin(),triangles.end(),
        [&](const CollisionTriangle&) { return removed[index++]; }),triangles.end());
}

void CollisionManager::SetTriangle(unsigned index,const glm::vec3& a,const glm::vec3& b,const glm::vec3& c) {
    CollisionTriangle& triangle=triangles.at(index);
    triangle.a=a;triangle.b=b;triangle.c=c;
    triangle.normal=glm::normalize(glm::cross(b-a,c-a));
    triangle.minBounds=glm::min(a,glm::min(b,c));
    triangle.maxBounds=glm::max(a,glm::max(b,c));
}
