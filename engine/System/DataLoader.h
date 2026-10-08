//
// Created by egors on 01.08.2026.
//

#ifndef TLOU_VITA_DATALOADER_H
#define TLOU_VITA_DATALOADER_H

#include <iostream>
#include <string>
#include <vector>       // <-- ДОБАВЛЕНО: необходим для std::vector
#include <filesystem>
#include <cstdint>      // <-- ДОБАВЛЕНО: для uint32_t, int16_t

#include <glm/glm.hpp>
#include <glm/mat4x4.hpp>

#include "System/Types.h"

class CollisionManager;
// =========================================================================
// FORWARD DECLARATIONS (Убирает циклический include и ошибку компиляции)
// =========================================================================
class MemoryManager;
class Mesh;
class Texture;
struct Asset;
class ArenaAllocator;

struct MeshHeader {
    uint32_t ModelSize;
};

struct TextureHeader {
    uint32_t width;
    uint32_t height;
    uint32_t dataSize;
};

struct EngineLight {
    glm::vec3 position;
    glm::vec3 direction;
    glm::vec3 color;
    float intensity;
    float radius;
    uint32_t type; // 0=Point, 1=Spot, 2=Sun, 3=Area
};

struct LevelHeaderLVL5 {
    char magic[4];          // "LVL5"
    uint32_t instanceCount;
    uint32_t collisionCount;
    uint32_t lightCount;    // Количество ламп!
    float spawnX, spawnY, spawnZ;
    float spawnYaw;
};


struct AABB {
    glm::vec3 minBounds;
    glm::vec3 maxBounds;

    bool ContainsPoint(const glm::vec3& point) const {
        return (point.x >= minBounds.x && point.x <= maxBounds.x) &&
               (point.y >= minBounds.y && point.y <= maxBounds.y) &&
               (point.z >= minBounds.z && point.z <= maxBounds.z);
    }

    size_t ownerIndex = 0;
};

class SkinnedModel;
struct Instance {
    glm::mat4 modelMatrix;
    Mesh* mesh;
    AABB boundingBox;
    Texture* texture;
    SkinnedModel* skinned = nullptr;
    bool skyGeometry = false; // Old exports: skip sky fragments without changing door indices.
};

struct PlayerStartInfo {
    glm::vec3 position = glm::vec3(0.0f, 1.0f, 0.0f);
    float yaw = 0.0f; // Угол поворота в градусах
};

struct Collision {
    glm::vec3 min;
    glm::vec3 max;
};

#pragma pack(push, 1)
struct Vertex {
    uint32_t color;         // 4 байта [0..3]  (выровнено по 4 байтам)
    int16_t x, y, z;        // 6 байт  [4..9]  (выровнено по 2 байтам)
    uint16_t u, v;          // 4 байта [10..13](выровнено по 2 байтам)
    int8_t oct_nx, oct_ny;  // 2 байта [14..15](выровнено по 1 байту)
};
#pragma pack(pop)

static_assert(sizeof(Vertex) == 16, "StaticVertex must be 16 bytes!");

#pragma pack(push, 1)
struct SkinnedVertex {
    int16_t x,y,z;
    uint16_t u,v;
    int8_t oct_nx,oct_ny;
    uint8_t bone_ids[2];
    uint8_t weight,reserved;
};
#pragma pack(pop)
static_assert(sizeof(SkinnedVertex)==16,"SkinnedVertex ABI");
static_assert(offsetof(SkinnedVertex,u)==6 && offsetof(SkinnedVertex,bone_ids)==12 && offsetof(SkinnedVertex,weight)==14,"SkinnedVertex offsets");


#pragma pack(push, 1)
struct RawTriangleData {
    float v0[3];
    float v1[3];
    float v2[3];
};
#pragma pack(pop)

class DataLoader {
public:
    DataLoader() {}

private:
    inline static std::vector<Instance> g_LevelInstances;

public:
    static std::vector<Instance> LoadLevel(const char* levelPath, std::vector<AABB>& collision , CollisionManager& collisionManager,
        MemoryManager& memory , PlayerStartInfo& outPlayerStart , std::vector<EngineLight>& outLights);

    // With a frame pump, workers load while the main thread plays a movie.
    using LoadingFramePump = void (*)(void* context);
    // Without a pump, the main thread helps the two workers as before.
    static bool LoadStartupLevel(const char* levelPath, MemoryManager& memory,
        CollisionManager& collisionManager, std::vector<Instance>& outInstances,
        std::vector<AABB>& outBounds, PlayerStartInfo& outSpawn,
        std::vector<EngineLight>& outLights, LoadingFramePump framePump = nullptr,
        void* frameContext = nullptr);

    static bool initAsyncLoader();

    //static bool LoadCollision(const char* collisionPath, CollisionManager& collisionManager);

    static bool loadMesh(const std::string& path, void* destinationBuffer, size_t maxCapacityBytes, uint32_t& outModelSize);

    static bool loadTexture(const std::string& path, void* destinationBuffer, size_t maxCapacityBytes, uint32_t& outTextureSize, uint16_t& outWidth, uint16_t& outHeight);

private:
    static std::string getFileNameWithoutExtension(const std::string& pathStr) {
        return std::filesystem::path(pathStr).stem().string();
    }
};

#endif //TLOU_VITA_DATALOADER_H