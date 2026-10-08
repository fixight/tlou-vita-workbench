#ifndef TLOU_VITA_MEMORYMANAGER_H
#define TLOU_VITA_MEMORYMANAGER_H

#include <cstdint>
#include <filesystem>
#include <string>
#include <unordered_map>

#include "PoolAllocator.h"
#include "Memory/ArenaAllocator.h"
#include "System/DataLoader.h"
#include "System/Types.h"

struct Instance;
struct Asset;

// 1. Выносим вспомогательные функции хеширования за пределы класса
// Или делаем их static constexpr внутри, но оператор ВНЕ класса.
constexpr uint64_t hash_fnv1a(const char* str) {
    uint64_t hash = 14695981039346656037ULL;
    while (*str) {
        hash ^= static_cast<uint64_t>(*str++);
        hash *= 1099511628211ULL;
    }
    return hash;
}

// Оператор литерала ДОЛЖЕН быть вне класса
constexpr uint64_t operator"" _hash(const char* str, size_t) {
    return hash_fnv1a(str);
}

class MemoryManager {
public:
    MemoryManager();
    // Не забудьте деструктор, так как вы используете new для аллокаторов
    ~MemoryManager();

private:
    size_t offset = 0;
    uint8_t* m_buffer = nullptr;

    PoolAllocator*  meshPool;
    PoolAllocator*  texturePool;
    PoolAllocator*  collisionPool;

    ArenaAllocator* m_mesh_arenaAllocator;
    ArenaAllocator* m_texture_arenaAllocator;

    std::unordered_map<uint64_t, Mesh*> m_loadedMeshes;
    std::unordered_map<uint64_t, Texture*> m_loadedTextures;
    std::unordered_map<uint64_t, MaterialSettings> m_materialSettings;

public:
    // Стартовая загрузка: эти методы вызываются ТОЛЬКО главным потоком.
    // Воркеры получают лишь dataPointer и размер своего отдельного буфера.
    bool LoadMaterialSettings(const char* path);
    void ApplyTextureMaterialSettings(Texture* texture);
    Mesh* FindLoadedMesh(const std::string& path);
    Texture* FindLoadedTexture(const std::string& path);
    Mesh* ReserveMesh(const std::string& path, uint32_t vertexCount);
    Texture* ReserveTexture(const std::string& path, const TextureHeader& header);
    void PublishMesh(Mesh* mesh);
    void PublishTexture(Texture* texture);
    void DiscardMesh(Mesh* mesh);
    void DiscardTexture(Texture* texture);
    struct LoadMarker { size_t meshBytes; size_t textureBytes; };
    LoadMarker GetLoadMarker() const;
    void RewindUnpublishedLoads(LoadMarker marker);

    Mesh* getMesh(const std::string& path);
    Texture* getTexture(const std::string& path);

    //void loadCollision(uint16_t lvlID , std::vector<AABB> collision);

    // Внутри класса можно оставить обертку для std::string
    inline uint64_t hashString(const std::string& str) {
        return hash_fnv1a(str.c_str());
    }

    std::string normalizePath(std::string path) {
        for (char& c : path) {
            if (c == '\\') c = '/';
            c = std::tolower(static_cast<unsigned char>(c));
        }
        return path;
    }

    static std::string getFileNameWithoutExtension(const std::string& pathStr) {
        return std::filesystem::path(pathStr).stem().string();
    }


    static void LoadMeshToVBO(Mesh* mesh, const void* vertexData, size_t dataSizeBytes) {
        glGenBuffers(1, &mesh->vboID);

        glBindBuffer(GL_ARRAY_BUFFER, mesh->vboID);


        glBufferData(GL_ARRAY_BUFFER, dataSizeBytes, vertexData, GL_STATIC_DRAW);

        glBindBuffer(GL_ARRAY_BUFFER, 0);
    }
};

#endif //TLOU_VITA_MEMORYMANAGER_H