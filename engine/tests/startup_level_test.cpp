// Test actual parser and collision jobs without executing GL or Vita calls.
// Build with -ffunction-sections and --gc-sections: unused platform integration is discarded.
#include "../System/StartupLevelLoader.cpp"
#include <cassert>
#include <fstream>
#include <iostream>

// The host test does not simulate Vita affinity or measure console performance.
int sceKernelGetCpuId() { return 0; }

template<class T> void Write(std::ofstream& file, const T& value) {
    file.write(reinterpret_cast<const char*>(&value), sizeof(value));
}
void WritePath(std::ofstream& file, const std::string& path) {
    Write(file, static_cast<uint16_t>(path.size()));
    file.write(path.data(), path.size());
}

void WriteFixture(const char* path, bool lvl5) {
    std::ofstream file(path, std::ios::binary);
    file.write(lvl5 ? "LVL5" : "LVL4", 4);
    Write(file, uint32_t(1));
    Write(file, uint32_t(2));
    if (lvl5) Write(file, uint32_t(1));
    Write(file, glm::vec3(4, 5, 6));
    Write(file, 90.0f);
    RawTriangleData floor{{0, 0, 0}, {0, 0, 1}, {1, 0, 0}};
    RawTriangleData degenerate{};
    Write(file, floor);
    Write(file, degenerate);
    Write(file, glm::mat4(1.0f));
    Write(file, glm::vec3(-1));
    Write(file, glm::vec3(1));
    WritePath(file, "app0:/assets/models/test.bin");
    WritePath(file, "app0:/assets/textures/test.bin");
    if (lvl5) {
        EngineLight light{};
        light.position = glm::vec3(10, 20, 30);
        light.radius = 8;
        Write(file, light);
    }
}

void CheckCollisionJobs(const LevelDescription& level) {
    std::vector<CollisionTriangle> result(level.collision.size());
    std::vector<CollisionPrepareJob> tasks;
    for (size_t begin = 0; begin < result.size(); begin += 512) {
        tasks.push_back({level.collision.data() + begin, result.data() + begin,
            std::min(size_t(512), result.size() - begin)});
    }
    JobSystem jobs;
    assert(jobs.Init());
    for (auto& task : tasks) assert(jobs.Execute(PrepareCollision, &task));
    assert(jobs.Wait());
    for (size_t i = 0; i < result.size(); ++i) {
        const auto& raw = level.collision[i];
        const glm::vec3 a(raw.v0[0], raw.v0[1], raw.v0[2]);
        const glm::vec3 b(raw.v1[0], raw.v1[1], raw.v1[2]);
        const glm::vec3 c(raw.v2[0], raw.v2[1], raw.v2[2]);
        assert(result[i].a == a && result[i].b == b && result[i].c == c);
        assert(result[i].minBounds == glm::min(a, glm::min(b, c)));
        assert(result[i].maxBounds == glm::max(a, glm::max(b, c)));
        const auto cross = glm::cross(b - a, c - a);
        const auto lengthSquared = glm::dot(cross, cross);
        const auto expected = lengthSquared > 0 ? cross / std::sqrt(lengthSquared) : glm::vec3(0);
        assert(glm::length(result[i].normal - expected) < 0.00001f);
    }
}

int main(int argc, char** argv) {
    for (bool lvl5 : {false, true}) {
        const char* path = lvl5 ? "/tmp/tlou-startup-lvl5.bin" : "/tmp/tlou-startup-lvl4.bin";
        WriteFixture(path, lvl5);
        LevelDescription level;
        assert(ReadLevelDescription(path, level));
        assert(level.spawn.position == glm::vec3(4, 5, 6) && level.spawn.yaw == 90);
        assert(level.objects.size() == 1 && level.collision.size() == 2);
        assert(level.lights.size() == (lvl5 ? 1 : 0));
        if (lvl5) assert(level.lights[0].radius == 8);
        assert(level.objects[0].meshPath == "app0:/assets/models/test.bin");
        CheckCollisionJobs(level);
        // Every truncated prefix of this valid fixture must be rejected.
        std::ifstream input(path, std::ios::binary);
        std::string bytes((std::istreambuf_iterator<char>(input)), {});
        for (size_t count = 0; count < bytes.size(); ++count) {
            {
                std::ofstream shortFile("/tmp/tlou-startup-short.bin", std::ios::binary);
                shortFile.write(bytes.data(), count);
            }
            LevelDescription truncated;
            assert(!ReadLevelDescription("/tmp/tlou-startup-short.bin", truncated));
        }
    }
    { // Impossible count must fail before allocating a huge triangle array.
        std::ofstream bad("/tmp/tlou-startup-bad.bin", std::ios::binary);
        bad.write("LVL4", 4);
        Write(bad, uint32_t(0)); Write(bad, uint32_t(0xffffffff));
        Write(bad, glm::vec3(0)); Write(bad, 0.0f);
    }
    LevelDescription bad;
    assert(!ReadLevelDescription("/tmp/tlou-startup-bad.bin", bad));
    assert(bad.collision.empty());
    if (argc > 1) {
        LevelDescription actual;
        assert(ReadLevelDescription(argv[1], actual));
        CheckCollisionJobs(actual);
        std::cout << "Real level checked: " << actual.objects.size() << " objects, "
                  << actual.collision.size() << " triangles\n";
    }
    std::cout << "Startup parser/collision regression checks passed\n";
}
