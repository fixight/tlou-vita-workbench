#pragma once
#include "System/DataLoader.h"
#include "Memory/MemoryManager.h"
#include <cstdio>
#include <cmath>
#include <cstring>
#include <vector>
#include <algorithm>

// A separate mesh uses the same 16-byte vertex layout, with its own position step.
struct SkyDome {
    Mesh* mesh = nullptr;
    Texture* texture = nullptr;
    float positionStep = 1.0f;
    std::vector<std::string> legacyMeshes;

    bool Load(const char* path, MemoryManager& memory) {
        FILE* file = std::fopen(path, "rb");
        if (!file) return false; // Levels without a sky remain supported.
        char magic[4]; float step = 0;
        auto readPath = [file](std::string& value) {
            uint16_t size = 0;
            if (std::fread(&size, 2, 1, file) != 1 || size == 0 || size > 4096) return false;
            value.resize(size);
            return std::fread(value.data(), 1, size, file) == size
                && value.find('\0') == std::string::npos
                && value.find("app0:/assets/") == 0 && value.find("..") == std::string::npos;
        };
        std::string meshPath, texturePath;
        bool valid = std::fread(magic, 1, 4, file) == 4 && std::memcmp(magic, "SKY1", 4) == 0
            && std::fread(&step, 4, 1, file) == 1 && std::isfinite(step) && step > 0
            && readPath(meshPath) && readPath(texturePath);
        uint32_t count = 0;
        std::vector<std::string> excluded;
        if (valid) {
            valid = std::fread(&count, 4, 1, file) == 1 && count <= 65536;
            for (uint32_t i = 0; valid && i < count; ++i) {
                std::string name; valid = readPath(name);
                if (valid) excluded.push_back(std::move(name));
            }
            valid = valid && std::fgetc(file) == EOF && !std::ferror(file);
        }
        std::fclose(file);
        if (!valid) { sceClibPrintf("[Sky] Invalid descriptor: %s\n", path); return false; }
        Mesh* loadedMesh = memory.getMesh(meshPath);
        Texture* loadedTexture = memory.getTexture(texturePath);
        if (!loadedMesh || !loadedTexture) return false;
        if (!loadedTexture->textureID) memory.PublishTexture(loadedTexture);
        mesh = loadedMesh; texture = loadedTexture; positionStep = step;
        legacyMeshes = std::move(excluded);
        char message[160];
        std::snprintf(message, sizeof(message),
            "[Sky] Ready: %u triangles, vertex=16, one draw, step=%.6f\n",
            mesh->vertexCount / 3, positionStep);
        sceClibPrintf("%s", message);
        return true;
    }
    // Compatibility with an existing LVL5 export. Fresh exports omit sky from LVL5.
    void ExcludeLegacyGeometry(std::vector<Instance>& objects) const {
        size_t removed = 0;
        for (auto& object : objects) {
            if (!object.mesh) continue;
            object.skyGeometry = std::find(legacyMeshes.begin(), legacyMeshes.end(),
                object.mesh->path) != legacyMeshes.end();
            if (object.skyGeometry) ++removed;
        }
        sceClibPrintf("[Sky] Replaced %u legacy world fragments\n", static_cast<unsigned>(removed));
    }
};
