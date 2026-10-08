#include "DataLoader.h"
#include "JobSystem.h"
#include "Memory/MemoryManager.h"
#include "Managers/CollisionManager.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>
#include <unordered_set>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/cpu.h>
#include <psp2/kernel/threadmgr.h>

namespace {

// Данные level.bin сначала существуют отдельно от игрового мира.
struct LevelObject {
    glm::mat4 transform;
    AABB bounds;
    std::string meshPath;
    std::string texturePath;
};

struct LevelDescription {
    PlayerStartInfo spawn;
    std::vector<RawTriangleData> collision;
    std::vector<LevelObject> objects;
    std::vector<EngineLight> lights;
};

// Проверяем каждое чтение и размер файла до выделения больших массивов.
class LevelReader {
    struct CloseFile {
        void operator()(FILE* file) const { std::fclose(file); }
    };
public:
    explicit LevelReader(const char* path) : file(std::fopen(path, "rb")) {
        if (!file || std::fseek(file.get(), 0, SEEK_END) != 0) return;
        const long length = std::ftell(file.get());
        if (length < 0 || std::fseek(file.get(), 0, SEEK_SET) != 0) return;
        remaining = static_cast<size_t>(length);
        valid = true;
    }

    bool Read(void* destination, size_t bytes) {
        if (!valid || bytes > remaining) return false;
        if (bytes != 0 && std::fread(destination, 1, bytes, file.get()) != bytes) return false;
        remaining -= bytes;
        return true;
    }

    template<class T> bool Read(T& value) { return Read(&value, sizeof(value)); }

    bool ReadPath(std::string& path) {
        uint16_t length = 0;
        if (!Read(length) || length > remaining) return false;
        path.resize(length);
        return Read(path.data(), length) && path.find('\0') == std::string::npos;
    }

    size_t Remaining() const { return remaining; }

private:
    std::unique_ptr<FILE, CloseFile> file;
    size_t remaining = 0;
    bool valid = false;
};

bool ReadLevelDescription(const char* path, LevelDescription& level) {
    LevelReader reader(path);
    char magic[4];
    uint32_t objectCount = 0, triangleCount = 0, lightCount = 0;
    if (!reader.Read(magic, sizeof(magic)) || !reader.Read(objectCount) || !reader.Read(triangleCount))
        return false;

    const bool hasLights = std::memcmp(magic, "LVL5", 4) == 0;
    if (!hasLights && std::memcmp(magic, "LVL4", 4) != 0) return false;
    if (hasLights && !reader.Read(lightCount)) return false;
    if (!reader.Read(level.spawn.position) || !reader.Read(level.spawn.yaw)) return false;

    if (triangleCount > reader.Remaining() / sizeof(RawTriangleData)) return false;
    level.collision.resize(triangleCount);
    if (!reader.Read(level.collision.data(), size_t(triangleCount) * sizeof(RawTriangleData))) return false;

    constexpr size_t minimumObjectBytes = sizeof(glm::mat4) + 2 * sizeof(glm::vec3) + 2 * sizeof(uint16_t);
    if (objectCount > reader.Remaining() / minimumObjectBytes) return false;
    level.objects.resize(objectCount);
    for (auto& object : level.objects) {
        if (!reader.Read(object.transform) || !reader.Read(object.bounds.minBounds)
            || !reader.Read(object.bounds.maxBounds) || !reader.ReadPath(object.meshPath)
            || !reader.ReadPath(object.texturePath)) return false;
    }

    if (lightCount > reader.Remaining() / sizeof(EngineLight)) return false;
    level.lights.resize(lightCount);
    // Дополнительные секции после источников света не меняем и не интерпретируем.
    return reader.Read(level.lights.data(), size_t(lightCount) * sizeof(EngineLight));
}

// Одно задание владеет отдельным участком арены. Общий MemoryManager оно не трогает.
struct AssetReadJob {
    Mesh* mesh = nullptr;
    Texture* texture = nullptr;
    std::mutex* fileMutex = nullptr;
    bool succeeded = false;
    int cpu = -1;
};

void ReadAsset(void* data) {
    auto& job = *static_cast<AssetReadJob*>(data);
    job.cpu = sceKernelGetCpuId();
    // One storage reader: Vita3K's file descriptor table is not synchronised.
    // Keep CPU preparation parallel, but never overlap file open/read/close.
    std::unique_lock<std::mutex> fileLock(*job.fileMutex);
    if (job.mesh) {
        uint32_t vertexCount = 0;
        job.succeeded = DataLoader::loadMesh(job.mesh->path, job.mesh->dataPointer,
            size_t(job.mesh->vertexCount) * sizeof(Vertex), vertexCount)
            && vertexCount == job.mesh->vertexCount;
    } else {
        uint32_t bytes = 0;
        uint16_t width = 0, height = 0;
        job.succeeded = DataLoader::loadTexture(job.texture->path, job.texture->dataPointer,
            job.texture->sizeInBytes, bytes, width, height)
            && bytes == job.texture->sizeInBytes && width == job.texture->size_x && height == job.texture->size_y;
        fileLock.unlock();
        if (job.succeeded && !job.texture->hasMaterialSettings)
            job.texture->material = GuessMaterialSettings(job.texture->dataPointer, bytes);
    }
}

// Делим реальный предрасчёт коллизии на независимые диапазоны.
struct CollisionPrepareJob {
    const RawTriangleData* source;
    CollisionTriangle* destination;
    size_t count;
    int cpu = -1;
};

void PrepareCollision(void* data) {
    auto& job = *static_cast<CollisionPrepareJob*>(data);
    job.cpu = sceKernelGetCpuId();
    for (size_t i = 0; i < job.count; ++i) {
        const auto& raw = job.source[i];
        auto& triangle = job.destination[i];
        triangle.a = glm::vec3(raw.v0[0], raw.v0[1], raw.v0[2]);
        triangle.b = glm::vec3(raw.v1[0], raw.v1[1], raw.v1[2]);
        triangle.c = glm::vec3(raw.v2[0], raw.v2[1], raw.v2[2]);
        const glm::vec3 cross = glm::cross(triangle.b - triangle.a, triangle.c - triangle.a);
        const float lengthSquared = glm::dot(cross, cross);
        triangle.normal = lengthSquared > 0.0f ? cross / std::sqrt(lengthSquared) : glm::vec3(0.0f);
        triangle.minBounds = glm::min(triangle.a, glm::min(triangle.b, triangle.c));
        triangle.maxBounds = glm::max(triangle.a, glm::max(triangle.b, triangle.c));
    }
}

// При ошибке чтения возвращаем карточки в пулы и откатываем только свои резервы.
// Этот объект должен пережить JobSystem: сначала закончить записи, потом освобождать.
struct AssetReservations {
    MemoryManager& memory;
    MemoryManager::LoadMarker marker;
    std::mutex fileMutex;
    std::vector<AssetReadJob> reads;
    bool published = false;

    explicit AssetReservations(MemoryManager& owner) : memory(owner), marker(owner.GetLoadMarker()) {}

    ~AssetReservations() {
        if (published) return;
        for (auto& read : reads) {
            if (read.mesh) memory.DiscardMesh(read.mesh);
            else memory.DiscardTexture(read.texture);
        }
        memory.RewindUnpublishedLoads(marker);
    }
};

bool ReserveAssets(const LevelDescription& level, AssetReservations& assets,
    DataLoader::LoadingFramePump framePump, void* frameContext) {
    std::unordered_set<std::string> meshes, textures;
    assets.reads.reserve(level.objects.size() * 2);
    uint64_t lastFrame = sceKernelGetProcessTimeWide();
    for (const auto& object : level.objects) {
        if (framePump && sceKernelGetProcessTimeWide() - lastFrame >= 4000) {
            framePump(frameContext);
            lastFrame = sceKernelGetProcessTimeWide();
        }
        if (object.meshPath.empty()) continue;
        const auto meshKey = assets.memory.normalizePath(object.meshPath);
        if (meshes.insert(meshKey).second && !assets.memory.FindLoadedMesh(object.meshPath)) {
            LevelReader file(object.meshPath.c_str());
            MeshHeader header{};
            if (!file.Read(header) || header.ModelSize == 0
                || header.ModelSize > file.Remaining() / sizeof(Vertex)) return false;
            Mesh* mesh = assets.memory.ReserveMesh(object.meshPath, header.ModelSize);
            if (!mesh) return false;
            assets.reads.push_back({mesh, nullptr, &assets.fileMutex});
        }
        // Текущий Render ожидает RGBA-текстуру у каждого визуального объекта.
        if (object.texturePath.empty()) return false;
        const auto textureKey = assets.memory.normalizePath(object.texturePath);
        if (textures.insert(textureKey).second && !assets.memory.FindLoadedTexture(object.texturePath)) {
            LevelReader file(object.texturePath.c_str());
            TextureHeader header{};
            if (!file.Read(header) || header.dataSize == 0 || header.dataSize > file.Remaining()
                || header.width == 0 || header.height == 0 || header.width > 65535 || header.height > 65535
                || uint64_t(header.width) * header.height * 4 != header.dataSize)
                return false;
            Texture* texture = assets.memory.ReserveTexture(object.texturePath, header);
            if (!texture) return false;
            assets.reads.push_back({nullptr, texture, &assets.fileMutex});
        }
    }
    return true;
}

// Только на время стартовой загрузки: главный поток помогает на пользовательском ядре 0.
class StartupCpuAffinity {
public:
    StartupCpuAffinity() : thread(sceKernelGetThreadId()), previous(sceKernelGetThreadCpuAffinityMask(thread)) {
        changed = previous >= 0
            && sceKernelChangeThreadCpuAffinityMask(thread, SCE_KERNEL_CPU_MASK_USER_0) >= 0;
    }
    ~StartupCpuAffinity() {
        if (changed) sceKernelChangeThreadCpuAffinityMask(thread, previous);
    }
private:
    SceUID thread;
    int previous;
    bool changed = false;
};

} // namespace

bool DataLoader::LoadStartupLevel(const char* levelPath, MemoryManager& memory,
    CollisionManager& collisionManager, std::vector<Instance>& outInstances,
    std::vector<AABB>& outBounds, PlayerStartInfo& outSpawn, std::vector<EngineLight>& outLights,
    LoadingFramePump framePump, void* frameContext)
{
    const uint64_t started = sceKernelGetProcessTimeWide();
    StartupCpuAffinity mainCpu;

    // 1. Главный поток: прочитать описание уровня, собрать уникальные ресурсы,
    //    выделить окончательные буферы. Пока игровой мир не изменяется.
    if (framePump) framePump(frameContext);
    memory.LoadMaterialSettings("app0:/assets/metadata/materials.bin");
    LevelDescription level;
    if (!ReadLevelDescription(levelPath, level)) {
        sceClibPrintf("[Startup] Invalid or unreadable level: %s\n", levelPath);
        return false;
    }
    sceClibPrintf("[Startup] Description: %u objects, %u collision triangles\n",
        unsigned(level.objects.size()), unsigned(level.collision.size()));
    AssetReservations assets(memory);
    if (!ReserveAssets(level, assets, framePump, frameContext)) {
        sceClibPrintf("[Startup] Cannot reserve resources: missing file, invalid header or arena full\n");
        return false;
    }

    sceClibPrintf("[Startup] Read/prepare: %u unique resources; frame pump=%u\n",
        unsigned(assets.reads.size()), unsigned(framePump != nullptr));
    std::vector<CollisionTriangle> preparedCollision(level.collision.size());
    std::vector<CollisionPrepareJob> collisionJobs;
    constexpr size_t trianglesPerJob = 512;
    for (size_t begin = 0; begin < level.collision.size(); begin += trianglesPerJob) {
        collisionJobs.push_back({level.collision.data() + begin, preparedCollision.data() + begin,
            std::min(trianglesPerJob, level.collision.size() - begin)});
    }

    // 2. Два воркера на ядрах 1/2. Все адреса job data уже стабильны:
    //    после постановки заданий векторы больше не расширяем.
    // JobSystem объявлен последним, чтобы при выходе он завершился раньше буферов.
    JobSystem jobs;
    if (!jobs.Init()) return false;
    bool accepted = true;
    for (auto& job : collisionJobs) {
        if (!jobs.Execute(PrepareCollision, &job)) { accepted = false; break; }
    }
    if (accepted) {
        for (auto& job : assets.reads) {
            if (!jobs.Execute(ReadAsset, &job)) { accepted = false; break; }
        }
    }

    // 3. Главный поток тоже забирает задания из очереди: до трёх ядер в работе.
    // With a movie pump, only workers consume jobs; the render thread keeps drawing.
    // Do not steal long I/O jobs on the movie/render thread. Workers finish them.
    if (framePump) {
        while (jobs.GetPendingCount() != 0) {
            framePump(frameContext);
            sceKernelDelayThread(1000);
        }
    }
    const bool completed = jobs.Wait();
    if (!accepted || !completed) return false;
    // CPU preparation is complete; release workers before GPU publication.
    if (!jobs.Shutdown()) return false;
    for (const auto& job : assets.reads) {
        if (!job.succeeded) {
            sceClibPrintf("[Startup] Resource read failed: %s\n",
                job.mesh ? job.mesh->path.c_str() : job.texture->path.c_str());
            return false;
        }
    }

    unsigned tasksPerCpu[4] = {};
    for (const auto& job : assets.reads) if (job.cpu >= 0 && job.cpu < 4) ++tasksPerCpu[job.cpu];
    for (const auto& job : collisionJobs) if (job.cpu >= 0 && job.cpu < 4) ++tasksPerCpu[job.cpu];
    sceClibPrintf("[Startup] Completed tasks: CPU0=%u CPU1=%u CPU2=%u CPU3=%u\n",
        tasksPerCpu[0], tasksPerCpu[1], tasksPerCpu[2], tasksPerCpu[3]);

    // 4. Главный поток: зарегистрировать ресурсы и создать VBO в текущем GL-контексте.
    // После начала публикации откат резервов уже нельзя делать: ресурсы видны кешу.
    sceClibPrintf("[Startup] Publish resources and VBOs on the main thread\n");
    assets.published = true;
    uint64_t lastFrame = sceKernelGetProcessTimeWide();
    for (auto& job : assets.reads) {
        if (job.mesh) memory.PublishMesh(job.mesh);
        else memory.PublishTexture(job.texture);
        // GL publication stays here. Yield between resources, never inside a GL call.
        if (framePump && sceKernelGetProcessTimeWide() - lastFrame >= 4000) {
            framePump(frameContext);
            lastFrame = sceKernelGetProcessTimeWide();
        }
    }

    std::vector<Instance> instances;
    std::vector<AABB> bounds;
    instances.reserve(level.objects.size());
    bounds.reserve(level.objects.size());
    for (const auto& object : level.objects) {
        if (object.meshPath.empty()) continue;
        Instance instance{};
        instance.modelMatrix = object.transform;
        instance.boundingBox = object.bounds;
        instance.boundingBox.ownerIndex = bounds.size();
        // getMesh/getTexture здесь только находят уже опубликованные ресурсы
        // и увеличивают refCount. Чтения файлов больше нет.
        instance.mesh = memory.getMesh(object.meshPath);
        instance.texture = object.texturePath.empty() ? nullptr : memory.getTexture(object.texturePath);
        bounds.push_back(instance.boundingBox);
        instances.push_back(instance);
    }

    // 5. Передать полностью готовый уровень игровому миру.
    collisionManager.SetPreparedTriangles(std::move(preparedCollision));
    outInstances = std::move(instances);
    outBounds = std::move(bounds);
    outSpawn = level.spawn;
    outLights = std::move(level.lights);
    const uint64_t elapsed = sceKernelGetProcessTimeWide() - started;
    sceClibPrintf("[Startup] Ready: %u objects, %u assets, %u triangles, %.2f ms\n",
        unsigned(outInstances.size()), unsigned(assets.reads.size()),
        unsigned(collisionManager.GetTriangleCount()), double(elapsed) / 1000.0);
    return true;
}
