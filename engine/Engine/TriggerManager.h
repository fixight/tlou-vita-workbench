#pragma once
#include <array>
#include <cstdint>
#include <string>
#include <vector>

// Diagnostic overlap only: triggers never resolve physical collisions or run scripts.
class TriggerManager {
public:
    struct Box { std::array<float,3> min, max; };
    struct Trigger {
        std::string id, name;
        std::vector<Box> volumes; // OR: do not fill gaps between disjoint volumes.
        bool inside = false;
    };
    bool Load(const char* path);
    void Update(const Box& probe, bool cameraProbe = false);
    const std::vector<Trigger>& GetTriggers() const { return triggers; }
    const std::string& GetHudText() const { return hudText; }
    size_t GetActiveCount() const { return activeCount; }
    const std::string& GetError() const { return error; }
private:
    std::vector<Trigger> triggers;
    std::string error, hudText, lastEntered;
    size_t activeCount = 0;
    bool lastCameraProbe = false, dirty = true;
    void RebuildHud(bool cameraProbe);
};
