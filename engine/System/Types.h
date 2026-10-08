//
// Created by egors on 02.08.2026.
//

#ifndef TLOU_VITA_TYPES_H
#define TLOU_VITA_TYPES_H
#include <string>
#include <vitaGL.h>
#include "MaterialSettings.h"

enum class AssetType {
    Mesh,
    Texture,
    Audio,
    Shader
};

struct Asset {
    // Идентификация
    std::string path;          // "app0:/models/joel.bin"
    std::string name;          // "joel"
    AssetType type;            // Mesh, Texture и т.д.

    size_t blockID;            //  идентификатор объекта в пуле

    // Управление памятью
    bool isShared = false;      // В Глобальный пул или в Линейную Арену комнаты?
    uint32_t refCount = 0;     // Сколько комнат/объектов прямо сейчас используют этот ассет

    // Состояние и Указатель на данные
    bool isLoaded = false;     // Загружен ли уже в оперативку?
    void* dataPointer = nullptr; // Прямой адрес в памяти (где лежат вершины/текстура)

    bool isDirty = false;

};

struct Mesh {
    std::string path;          // "app0:/models/joel.bin"
    std::string name;
    AssetType type;
    size_t blockID;
    // Управление памятью
    bool isShared = false;
    uint32_t refCount = 0;
    bool isLoaded = false;
    void* dataPointer = nullptr;

    bool isDirty = false;
    uint64_t assetID = 0;

    uint32_t vertexCount = 0; // Специфичное поле

    GLuint vboID = 0;
};

struct Texture {
    std::string path;          // "app0:/models/joel.bin"
    std::string name;
    AssetType type;
    size_t blockID;
    // Управление памятью
    bool isShared = false;
    uint32_t refCount = 0;
    bool isLoaded = false;
    void* dataPointer = nullptr;
    bool isDirty = false;
    uint64_t assetID = 0;
    uint32_t sizeInBytes = 0;
    uint32_t size_x = 0;
    uint32_t size_y = 0;
    GLuint textureID = 0;
    MaterialSettings material;
    bool hasMaterialSettings = false;
};

class Types {
};


#endif //TLOU_VITA_TYPES_H