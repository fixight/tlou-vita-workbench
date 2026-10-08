//
// Created by egors on 30.07.2026.
//

#include "MemoryManager.h"

#include <psp2/kernel/clib.h>
#include <cstdio>
#include <cmath>
#include <cstring>

#include "../System/DataLoader.h"
#include "../System/Types.h"

MemoryManager::MemoryManager() {
    meshPool = new PoolAllocator(5200, sizeof(Mesh));
    texturePool = new PoolAllocator(1300, sizeof(Texture));
    collisionPool = new PoolAllocator(50, sizeof(Instance));
    m_mesh_arenaAllocator = new ArenaAllocator(1024 * 1024 * 120);
    m_texture_arenaAllocator = new ArenaAllocator(1024 * 1024 * 25);

}

MemoryManager::~MemoryManager() {
}

Mesh* MemoryManager::getMesh(const std::string &path) {
    uint64_t assetID = hashString(normalizePath(path));

    // 1. Поиск в словаре: если найден — увеличиваем refCount и возвра
    if (auto it = m_loadedMeshes.find(assetID); it != m_loadedMeshes.end()) {
        it->second->refCount++; // ИСПРАВЛЕНО: Увеличиваем счетчик ссыл
        return it->second;
    }

    // 2. Выделяем карточку Asset из PoolAllocat
    size_t blockID = 0;
    Mesh* newAsset = meshPool->Allocate<Mesh>(blockID);



    if (!newAsset) {
        sceClibPrintf("no card in pool\n");
        return nullptr;
    }

    new (newAsset) Mesh();

    uint32_t modelSize = 0;

    // 3. ИСПРАВЛЕНО: Передаем getRemainingMemory() вместо getCapacity()
    if (!DataLoader::loadMesh(path, m_mesh_arenaAllocator->getPointer(), m_mesh_arenaAllocator->getRemainingMemory(), modelSize)) {
        // ИСПРАВЛЕНО: При ошибке загрузки возвращаем карточку обратно в пул!
        sceClibPrintf("loading error\n");
        meshPool->Clear(blockID);
        return nullptr;
    }

    // 4. Запоминаем адрес начала вершин (до сдвига арены)
    newAsset->dataPointer = m_mesh_arenaAllocator->getPointer();

    // 5. ОФИЦИАЛЬНО сдвигаем указатель арены на размер прочитанных вершин
    m_mesh_arenaAllocator->allocateBytes(modelSize * sizeof(Vertex));

    // 6. Заполняем метаданные
    newAsset->blockID = blockID;
    newAsset->refCount = 1;
    newAsset->isLoaded = true;
    newAsset->path = path;
    newAsset->name = getFileNameWithoutExtension(normalizePath(path));
    newAsset->type = AssetType::Mesh;
    newAsset->isShared = false;
    newAsset->vertexCount = modelSize;

    // 7. ИСПРАВЛЕНО: Сохраняем указатель на ассет в словарь!
    m_loadedMeshes[assetID] = newAsset;

    // ПРАВИЛЬНО: Передаем размер в БАЙТАХ (Количество вершин * 32 байта)
    LoadMeshToVBO(newAsset, newAsset->dataPointer, newAsset->vertexCount * sizeof(Vertex));

    sceClibPrintf("return valid asset\n");

    return newAsset;
}

Texture * MemoryManager::getTexture(const std::string &path) {
    uint64_t assetID = hashString(normalizePath(path));

    // 1. Поиск в словаре: если найден — увеличиваем refCount и возвращаем!
    if (auto it = m_loadedTextures.find(assetID); it != m_loadedTextures.end()) {
        it->second->refCount++; // ИСПРАВЛЕНО: Увеличиваем счетчик ссылок
        return it->second;
    }

    // 2. Выделяем карточку Asset из PoolAllocator
    size_t blockID = 0;
    Texture* newAsset = texturePool->Allocate<Texture>(blockID);



    if (!newAsset) {
        sceClibPrintf("no card in TexturePool\n");
        return nullptr;
    }

    new (newAsset) Texture();

    uint32_t textureSize = 0;
    uint16_t xSize = 0;
    uint16_t ySize = 0;

    // 3. ИСПРАВЛЕНО: Передаем getRemainingMemory() вместо getCapacity()
    if (!DataLoader::loadTexture(path, m_texture_arenaAllocator->getPointer(), m_texture_arenaAllocator->getRemainingMemory(), textureSize , xSize , ySize)) {
        // ИСПРАВЛЕНО: При ошибке загрузки возвращаем карточку обратно в пул!
        sceClibPrintf("loading error\n");
        texturePool->Clear(blockID);
        return nullptr;
    }

    // 4. Запоминаем адрес начала вершин (до сдвига арены)
    newAsset->dataPointer = m_texture_arenaAllocator->getPointer();

    // 5. ОФИЦИАЛЬНО сдвигаем указатель арены на размер прочитанных вершин
    m_texture_arenaAllocator->allocateBytes(textureSize);

    // 6. Заполняем метаданные
    newAsset->blockID = blockID;
    newAsset->refCount = 1;
    newAsset->isLoaded = true;
    newAsset->path = path;
    newAsset->name = getFileNameWithoutExtension(normalizePath(path));
    newAsset->type = AssetType::Texture;
    newAsset->isShared = false;
    newAsset->sizeInBytes = textureSize;
    newAsset->size_x = xSize;
    newAsset->size_y = ySize;
    ApplyTextureMaterialSettings(newAsset);

    // 7. ИСПРАВЛЕНО: Сохраняем указатель на ассет в словарь!
    m_loadedTextures[assetID] = newAsset;

    sceClibPrintf("return valid asset\n");

    return newAsset;
}


// Здесь нет чтения файлов: резервируем окончательное место ресурса в арене.
// Рабочие потоки не изменяют ни арены, ни словари ресурсов, ни состояние GL.
Mesh* MemoryManager::FindLoadedMesh(const std::string& path) {
    auto found = m_loadedMeshes.find(hashString(normalizePath(path)));
    return found == m_loadedMeshes.end() ? nullptr : found->second;
}

Texture* MemoryManager::FindLoadedTexture(const std::string& path) {
    auto found = m_loadedTextures.find(hashString(normalizePath(path)));
    return found == m_loadedTextures.end() ? nullptr : found->second;
}

Mesh* MemoryManager::ReserveMesh(const std::string& path, uint32_t vertexCount) {
    if (vertexCount == 0 || vertexCount > m_mesh_arenaAllocator->getRemainingMemory() / sizeof(Vertex))
        return nullptr;

    size_t blockID = 0;
    Mesh* mesh = meshPool->Allocate<Mesh>(blockID);
    if (!mesh) return nullptr;
    new (mesh) Mesh();
    mesh->blockID = blockID;
    mesh->path = path;
    mesh->name = getFileNameWithoutExtension(normalizePath(path));
    mesh->type = AssetType::Mesh;
    mesh->vertexCount = vertexCount;
    mesh->dataPointer = m_mesh_arenaAllocator->allocateBytes(size_t(vertexCount) * sizeof(Vertex));
    return mesh;
}

Texture* MemoryManager::ReserveTexture(const std::string& path, const TextureHeader& header) {
    if (header.dataSize == 0 || header.dataSize > m_texture_arenaAllocator->getRemainingMemory())
        return nullptr;

    size_t blockID = 0;
    Texture* texture = texturePool->Allocate<Texture>(blockID);
    if (!texture) return nullptr;
    new (texture) Texture();
    texture->blockID = blockID;
    texture->path = path;
    texture->name = getFileNameWithoutExtension(normalizePath(path));
    texture->type = AssetType::Texture;
    texture->size_x = header.width;
    texture->size_y = header.height;
    texture->sizeInBytes = header.dataSize;
    // Только параметры из sidecar: пиксели ещё не прочитаны.
    auto settings = m_materialSettings.find(hashString(normalizePath(path)));
    if (settings != m_materialSettings.end()) {
        texture->material = settings->second;
        texture->hasMaterialSettings = true;
    }
    texture->dataPointer = m_texture_arenaAllocator->allocateBytes(header.dataSize);
    return texture;
}

void MemoryManager::PublishMesh(Mesh* mesh) {
    LoadMeshToVBO(mesh, mesh->dataPointer, size_t(mesh->vertexCount) * sizeof(Vertex));
    mesh->isLoaded = true;
    m_loadedMeshes[hashString(normalizePath(mesh->path))] = mesh;
}

void MemoryManager::PublishTexture(Texture* texture) {
    // Загружаем в GPU на загрузочном экране, чтобы первый игровой кадр
    // не создавал все текстуры через ленивую ветку Render.
    glGenTextures(1, &texture->textureID);
    glBindTexture(GL_TEXTURE_2D, texture->textureID);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, texture->size_x, texture->size_y,
        0, GL_RGBA, GL_UNSIGNED_BYTE, texture->dataPointer);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
    glBindTexture(GL_TEXTURE_2D, 0);
    texture->isLoaded = true;
    m_loadedTextures[hashString(normalizePath(texture->path))] = texture;
}

void MemoryManager::DiscardMesh(Mesh* mesh) {
    const size_t blockID = mesh->blockID;
    mesh->~Mesh();
    meshPool->Clear(blockID);
}

void MemoryManager::DiscardTexture(Texture* texture) {
    const size_t blockID = texture->blockID;
    texture->~Texture();
    texturePool->Clear(blockID);
}

MemoryManager::LoadMarker MemoryManager::GetLoadMarker() const {
    return {m_mesh_arenaAllocator->getUsedMemory(), m_texture_arenaAllocator->getUsedMemory()};
}

void MemoryManager::RewindUnpublishedLoads(LoadMarker marker) {
    m_mesh_arenaAllocator->Rewind(marker.meshBytes);
    m_texture_arenaAllocator->Rewind(marker.textureBytes);
}


bool MemoryManager::LoadMaterialSettings(const char* path) {
    FILE* file = std::fopen(path, "rb");
    if (!file) {
        sceClibPrintf("[Materials] No sidecar; guessing old texture alpha modes\n");
        return false;
    }
    char magic[4];
    uint32_t count = 0;
    bool valid = std::fread(magic, 1, 4, file) == 4 && std::memcmp(magic, "MAT1", 4) == 0
        && std::fread(&count, sizeof(count), 1, file) == 1 && count <= 65536;
    std::unordered_map<uint64_t, MaterialSettings> settings;
    for (uint32_t i = 0; valid && i < count; ++i) {
        uint16_t length = 0;
        uint8_t mode = 0, doubleSided = 0;
        float cutoff = 0;
        valid = std::fread(&length, sizeof(length), 1, file) == 1 && length > 0 && length <= 4096;
        if (!valid) break;
        std::string texturePath(length, '\0');
        valid = std::fread(texturePath.data(), 1, length, file) == length
            && std::fread(&mode, 1, 1, file) == 1
            && std::fread(&doubleSided, 1, 1, file) == 1
            && std::fread(&cutoff, sizeof(cutoff), 1, file) == 1
            && mode <= 2 && doubleSided <= 1 && std::isfinite(cutoff) && cutoff >= 0 && cutoff <= 1
            && texturePath.find('\0') == std::string::npos;
        if (valid) settings[hashString(normalizePath(texturePath))] =
            {static_cast<AlphaMode>(mode), cutoff, doubleSided != 0};
    }
    std::fclose(file);
    if (!valid) {
        sceClibPrintf("[Materials] Invalid sidecar: %s\n", path);
        return false;
    }
    m_materialSettings = std::move(settings);
    sceClibPrintf("[Materials] Loaded %u explicit material settings\n", count);
    return true;
}

void MemoryManager::ApplyTextureMaterialSettings(Texture* texture) {
    auto settings = m_materialSettings.find(hashString(normalizePath(texture->path)));
    if (settings != m_materialSettings.end()) {
        texture->material = settings->second;
        texture->hasMaterialSettings = true;
    } else {
        texture->material = GuessMaterialSettings(texture->dataPointer, texture->sizeInBytes);
    }
}
