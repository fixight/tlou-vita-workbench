//
// Created by egors on 01.08.2026.
//

#include "DataLoader.h"

#include <fstream>
#include <ios>
#include <vector>
#include <psp2/kernel/clib.h>
#include  "Managers/CollisionManager.h"
#include "Memory/MemoryManager.h"

#include "Types.h"

std::vector<Instance> DataLoader::LoadLevel(
    const char* levelPath,
    std::vector<AABB>& collisionAABBs,
    CollisionManager& collisionManager,
    MemoryManager& memory,
    PlayerStartInfo& outPlayerStart,
    std::vector<EngineLight>& outLights) // <-- Добавлен вектор для ламп
{
    std::vector<Instance> instances;
    outLights.clear();
    memory.LoadMaterialSettings("app0:/assets/metadata/materials.bin");

    FILE* f = fopen(levelPath, "rb");
    if (!f) {
        sceClibPrintf("[DataLoader] ОШИБКА: Не удалось открыть файл: %s\n", levelPath);
        return instances;
    }

    char magic[4];
    uint32_t instanceCount = 0;
    uint32_t triangleCount = 0;
    uint32_t lightCount = 0;

    fread(magic, 1, 4, f);
    fread(&instanceCount, sizeof(uint32_t), 1, f);
    fread(&triangleCount, sizeof(uint32_t), 1, f);

    bool isLVL4 = (magic[0] == 'L' && magic[1] == 'V' && magic[2] == 'L' && magic[3] == '4');
    bool isLVL5 = (magic[0] == 'L' && magic[1] == 'V' && magic[2] == 'L' && magic[3] == '5');

    // 1. Читаем заголовок LVL5 (с количеством ламп)
    if (isLVL5) {
        fread(&lightCount, sizeof(uint32_t), 1, f);
        fread(&outPlayerStart.position, sizeof(glm::vec3), 1, f);
        fread(&outPlayerStart.yaw, sizeof(float), 1, f);
        sceClibPrintf("[DataLoader] LVL5: Ламп: %u | PlayerStart: Pos(%.2f, %.2f, %.2f), Yaw(%.2f)\n",
            lightCount, outPlayerStart.position.x, outPlayerStart.position.y, outPlayerStart.position.z, outPlayerStart.yaw);
    }
    // Заголовок LVL4 (без ламп)
    else if (isLVL4) {
        fread(&outPlayerStart.position, sizeof(glm::vec3), 1, f);
        fread(&outPlayerStart.yaw, sizeof(float), 1, f);
        sceClibPrintf("[DataLoader] LVL4: PlayerStart загружен: Pos(%.2f, %.2f, %.2f), Yaw(%.2f)\n",
            outPlayerStart.position.x, outPlayerStart.position.y, outPlayerStart.position.z, outPlayerStart.yaw);
    }

    // 2. Читаем треугольники коллизии
    if (triangleCount > 0) {
        struct RawTriangle { float v[9]; };
        std::vector<RawTriangle> rawTris(triangleCount);

        size_t totalBytesToRead = (size_t)triangleCount * sizeof(RawTriangle);
        size_t totalBytesRead = 0;
        uint8_t* bufferPtr = reinterpret_cast<uint8_t*>(rawTris.data());

        while (totalBytesRead < totalBytesToRead) {
            size_t bytesRead = fread(bufferPtr + totalBytesRead, 1, totalBytesToRead - totalBytesRead, f);
            if (bytesRead == 0) break;
            totalBytesRead += bytesRead;
        }

        collisionManager.clear();
        for (uint32_t i = 0; i < triangleCount; ++i) {
            glm::vec3 v0(rawTris[i].v[0], rawTris[i].v[1], rawTris[i].v[2]);
            glm::vec3 v1(rawTris[i].v[3], rawTris[i].v[4], rawTris[i].v[5]);
            glm::vec3 v2(rawTris[i].v[6], rawTris[i].v[7], rawTris[i].v[8]);
            collisionManager.addTriangle(v0, v1, v2);
        }
    }

    // 3. Читаем визуальные инстансы моделей
    instances.reserve(instanceCount);
    for (uint32_t i = 0; i < instanceCount; i++) {
        Instance inst;
        fread(&inst.modelMatrix, sizeof(glm::mat4), 1, f);

        fread(&inst.boundingBox.minBounds, sizeof(glm::vec3), 1, f);
        fread(&inst.boundingBox.maxBounds, sizeof(glm::vec3), 1, f);
        inst.boundingBox.ownerIndex = collisionAABBs.size();
        collisionAABBs.push_back(inst.boundingBox);

        uint16_t modelPathLen = 0;
        fread(&modelPathLen, sizeof(uint16_t), 1, f);
        std::string modelPath(modelPathLen, '\0');
        if (modelPathLen > 0) fread(&modelPath[0], 1, modelPathLen, f);

        uint16_t texPathLen = 0;
        fread(&texPathLen, sizeof(uint16_t), 1, f);
        std::string texPath(texPathLen, '\0');
        if (texPathLen > 0) fread(&texPath[0], 1, texPathLen, f);

        if (modelPathLen > 0) {
            inst.mesh = memory.getMesh(modelPath.c_str());
            inst.texture = memory.getTexture(texPath.c_str());
            instances.push_back(inst);
        }
    }

    // 4. Читаем источники света (если формат LVL5)
    if (isLVL5 && lightCount > 0) {
        outLights.resize(lightCount);
        fread(outLights.data(), sizeof(EngineLight), lightCount, f);

        sceClibPrintf("[DataLoader] Успешно загружено %u динамических источников света.\n", lightCount);
        for (uint32_t i = 0; i < lightCount; i++) {
            const auto& lt = outLights[i];
            sceClibPrintf("  -> Лампа [%u]: Pos(%.1f, %.1f, %.1f), Color(%.2f, %.2f, %.2f), Radius: %.1fm\n",
                i, lt.position.x, lt.position.y, lt.position.z, lt.color.r, lt.color.g, lt.color.b, lt.radius);
        }
    }

    fclose(f);
    sceClibPrintf("[DataLoader] Уровень загружен: Инстансов: %u | Коллизий: %u\n", (uint32_t)instances.size(), triangleCount);
    return instances;
}



bool DataLoader::loadMesh(const std::string& path, void* destinationBuffer, size_t maxCapacityBytes, uint32_t& outModelSize) {
    std::ifstream file(path, std::ios::binary);
    if (!file.is_open()) return false;

    MeshHeader header{};
    file.read(reinterpret_cast<char*>(&header), sizeof(MeshHeader));
    if (!file.good() || !destinationBuffer || header.ModelSize > maxCapacityBytes / sizeof(Vertex)) return false;

    size_t requiredBytes = (size_t)header.ModelSize * sizeof(Vertex); // ровно 16 байт * кол-во вершин
    if (requiredBytes > maxCapacityBytes) {
        sceClibPrintf("[DataLoader] ERROR: Недостаточно памяти под меш!\n");
        return false;
    }

    // Мгновенное чтение всего файла прямо в VBO память!
    file.read(reinterpret_cast<char*>(destinationBuffer), requiredBytes);
    outModelSize = header.ModelSize;

    return file.good();
}

bool DataLoader::loadTexture(const std::string &path, void* destinationBuffer, size_t maxCapacityBytes,
                             uint32_t& outTextureSize, uint16_t& outWidth, uint16_t& outHeight) {

    // 1. КРИТИЧЕСКАЯ ЗАЩИТА: Проверяем, что выделенный буфер памяти не
    if (destinationBuffer == nullptr) {
        sceClibPrintf("[ERROR] destinationBuffer is NULLPTR for texture: %s\n", path.c_str());
        return false;
    }

    std::ifstream file(path, std::ios::binary);
    if (!file.is_open()) {
        sceClibPrintf("[ERROR]Failed to open file: %s\n", path.c_str());
        return false;
    }

    TextureHeader header;
    file.read(reinterpret_cast<char*>(&header), sizeof(TextureHeader));

    // Проверяем, что заголовок успешно прочитался
    if (!file.good()) {
        sceClibPrintf("[ERROR] Corrupted header in file: %s\n", path.c_str());
        return false;
    }

    size_t requiredBytes = header.dataSize;

    if (requiredBytes > maxCapacityBytes) {
        sceClibPrintf("[ERROR] No available memory! Texture size: %u, Max capacity: %u in %s\n",
                      (uint32_t)requiredBytes, (uint32_t)maxCapacityBytes, path.c_str());
        return false;
    }

    // 2. Только когда точно уверены, что буфер валиден — считываем данные
    file.read(reinterpret_cast<char*>(destinationBuffer), requiredBytes);

    if (!file.good()) {
        sceClibPrintf("[ERROR] Failed to read texture body from: %s\n", path.c_str());
        return false;
    }

    outWidth = static_cast<uint16_t>(header.width);
    outHeight = static_cast<uint16_t>(header.height);
    outTextureSize = header.dataSize;

    sceClibPrintf("texture success raw loaded: %s (%dx%d, %u bytes)\n",
                  path.c_str(), header.width, header.height, header.dataSize);

    return true;
}
