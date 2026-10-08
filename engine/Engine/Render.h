//
// Created by egors on 30.07.2026.
//

#ifndef TLOU_VITA_RENDER_H
#define TLOU_VITA_RENDER_H
#include <vitaGL.h>
#include <vector>
#include "RenderStats.h"

#include "../Objects/CameraActor.h"
#include "../System/DataLoader.h"
#include "glm/fwd.hpp"
#include "System/Types.h"

struct AABB;
class Instance;
struct SkyDome;
class CinematicPlayer;

struct Plane {
    float a, b, c, d;

    // Нормализация плоскости (чтобы расстояние измерялось в метрах)
    void normalize() {
        float length = sqrtf(a * a + b * b + c * c);
        a /= length;
        b /= length;
        c /= length;
        d /= length;
    }
};

struct Frustum {
    Plane planes[6];

    // Извлечение из View-Projection матрицы (glm::mat4 VP)
    void extractFromMatrix(const float* m) {
        // Левая плоскость
        planes[0] = { m[3] + m[0], m[7] + m[4], m[11] + m[8],  m[15] + m[12] };
        // Правая плоскость
        planes[1] = { m[3] - m[0], m[7] - m[4], m[11] - m[8],  m[15] - m[12] };
        // Нижняя плоскость
        planes[2] = { m[3] + m[1], m[7] + m[5], m[11] + m[9],  m[15] + m[13] };
        // Верхняя плоскость
        planes[3] = { m[3] - m[1], m[7] - m[5], m[11] - m[9],  m[15] - m[13] };
        // Ближняя (Near)
        planes[4] = { m[3] + m[2], m[7] + m[6], m[11] + m[10], m[15] + m[14] };
        // Дальняя (Far)
        planes[5] = { m[3] - m[2], m[7] - m[6], m[11] - m[10], m[15] - m[14] };

        for (int i = 0; i < 6; i++) {
            planes[i].normalize();
        }
    }
};
class Render {
public:
    Render() {

    }
public:

    static GLuint CompileShader(const char* vertexShader , const char* fragmentShader);

    void render(std::vector<Instance>& objects , CameraActor* camera , const std::vector<EngineLight>& lights ,  GLuint shader , bool isPlayerPass = false, AlphaMode materialPass = AlphaMode::Opaque);

    void RenderCinematic(CinematicPlayer& scene, CameraActor* camera, const std::vector<EngineLight>& lights, GLuint shader);
    void RenderSky(const SkyDome& sky, CameraActor* camera, GLuint shader);

    void BeginFrame() {
        stats = RenderStats{};
        visibleTextures.clear();
        lastBoundTexture = lastBoundVBO = 0;
    }
    const RenderStats& GetStats() const { return stats; }

    void renderCollision(std::vector<AABB>& collisions , CameraActor* camera , GLuint shader);

private:
    struct VisibleWorldObject {
        const Instance* instance;
        float viewDepth;
    };
    // Повторно используем память списка между проходами и кадрами.
    std::vector<VisibleWorldObject> visibleWorld;
    RenderStats stats;
    std::vector<const Texture*> visibleTextures;
    inline static GLuint TempShader;

    GLuint lastBoundTexture = 0;
    GLuint lastBoundVBO = 0;

    inline static bool g_debugIsolateHeavyObjects = true; // <-- ПОСТАВЬТЕ true ДЛЯ ПРОВЕРКИ!

    // Порог аномальности: если объект готовился/рисовался дольше 300 мкс (0.3 мс)
    // ИЛИ содержит больше 15 000 вершин — считаем его "тяжелым монстром"
    uint64_t HEAVY_TIME_THRESHOLD_US = 300; // 300 микросекунд
    uint32_t HEAVY_VERTEX_THRESHOLD  = 15000;

    bool isBoxInFrustum(const Frustum& frustum, glm::vec3 min, glm::vec3 max) {
        for (int i = 0; i < 6; i++) {
            const Plane& p = frustum.planes[i];

            // Ищем самую выступающую точку куба в сторону плоскости
            glm::vec3 pVertex;
            pVertex.x = (p.a > 0.0f) ? max.x : min.x;
            pVertex.y = (p.b > 0.0f) ? max.y : min.y;
            pVertex.z = (p.c > 0.0f) ? max.z : min.z;

            // Если даже самая крайняя точка находится ЗА плоскостью — куб целиком снаружи!
            if ((p.a * pVertex.x + p.b * pVertex.y + p.c * pVertex.z + p.d) < 0.0f) {
                return false; // Объект НЕ виден, отбрасываем!
            }
        }
        return true; // Объект хотя бы частично виден в кадре
    }





};


#endif //TLOU_VITA_RENDER_H
