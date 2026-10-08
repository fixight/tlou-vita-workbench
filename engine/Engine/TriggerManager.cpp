#include "TriggerManager.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <limits>

namespace {
struct Reader {
    std::ifstream file;
    explicit Reader(const char* path): file(path, std::ios::binary) {}
    bool U32(uint32_t& value) {
        unsigned char b[4];
        if (!file.read(reinterpret_cast<char*>(b), 4)) return false;
        value = uint32_t(b[0]) | (uint32_t(b[1]) << 8) |
                (uint32_t(b[2]) << 16) | (uint32_t(b[3]) << 24);
        return true;
    }
    bool Text(std::string& value) {
        uint32_t length;
        if (!U32(length) || length > 4096) return false;
        value.resize(length);
        return length == 0 || bool(file.read(&value[0], length));
    }
    bool Float(float& value) {
        uint32_t bits;
        if (!U32(bits)) return false;
        static_assert(sizeof(value) == sizeof(bits), "32-bit float required");
        std::memcpy(&value, &bits, sizeof(value));
        return std::isfinite(value);
    }
};
bool Overlap(const TriggerManager::Box& a, const TriggerManager::Box& b) {
    for (unsigned i = 0; i < 3; ++i)
        if (a.max[i] < b.min[i] || a.min[i] > b.max[i]) return false;
    return true;
}
double Volume(const TriggerManager::Trigger& trigger) {
    double result = 0;
    for (const auto& b: trigger.volumes)
        result += double(b.max[0]-b.min[0]) * (b.max[1]-b.min[1]) * (b.max[2]-b.min[2]);
    return result;
}
std::string DisplayName(const std::string& name) {
    // The HUD bitmap font is ASCII. Preserve complete UTF-8 names in the records.
    std::string out;
    for (unsigned char c: name) out += c >= 32 && c < 127 ? char(c) : '?';
    if (out.size() > 74) out = out.substr(0,71) + "...";
    return out;
}
}

bool TriggerManager::Load(const char* path) {
    triggers.clear(); activeCount = 0; lastEntered.clear(); error.clear(); dirty = true;
    Reader input(path);
    if (!input.file) { error = "TRIGGER FILE MISSING"; RebuildHud(false); return false; }
    auto fail = [&]() {
        triggers.clear(); error = "INVALID TRIGGER FILE"; RebuildHud(false); return false;
    };
    char magic[4]; uint32_t version, count;
    if (!input.file.read(magic,4) || std::memcmp(magic,"VTGR",4) ||
        !input.U32(version) || version != 1 || !input.U32(count) || count > 4096) return fail();
    std::vector<Trigger> parsed;
    parsed.reserve(count);
    uint32_t totalBoxes = 0;
    for (uint32_t i=0; i<count; ++i) {
        Trigger trigger; uint32_t boxes;
        if (!input.Text(trigger.id) || trigger.id.empty() || !input.Text(trigger.name) ||
            !input.U32(boxes) || boxes == 0 || boxes > 1024 || totalBoxes > 65536-boxes) return fail();
        totalBoxes += boxes;
        trigger.volumes.resize(boxes);
        for (auto& box: trigger.volumes) {
            for (float& value: box.min) if (!input.Float(value)) return fail();
            for (float& value: box.max) if (!input.Float(value)) return fail();
            for (unsigned axis=0; axis<3; ++axis) if (box.min[axis] > box.max[axis]) return fail();
        }
        if (trigger.name.empty()) trigger.name = trigger.id;
        parsed.push_back(std::move(trigger));
    }
    if (input.file.peek() != std::char_traits<char>::eof()) return fail();
    // Small local areas take priority over large overlapping scene-wide regions in the HUD.
    std::stable_sort(parsed.begin(),parsed.end(),[](const Trigger& a,const Trigger& b){return Volume(a)<Volume(b);});
    triggers.swap(parsed);
    RebuildHud(false);
    return true;
}

void TriggerManager::Update(const Box& probe, bool cameraProbe) {
    for (unsigned axis=0; axis<3; ++axis)
        if (!std::isfinite(probe.min[axis]) || !std::isfinite(probe.max[axis]) ||
            probe.min[axis] > probe.max[axis]) return;
    bool changed = dirty || cameraProbe != lastCameraProbe;
    activeCount = 0;
    bool entered = false;
    for (auto& trigger: triggers) {
        bool inside = false;
        for (const auto& box: trigger.volumes) if (Overlap(probe,box)) { inside = true; break; }
        if (inside != trigger.inside) {
            changed = true;
            if (inside && !entered) { lastEntered = trigger.name; entered = true; }
            trigger.inside = inside;
        }
        if (inside) ++activeCount;
    }
    if (changed) RebuildHud(cameraProbe);
}

void TriggerManager::RebuildHud(bool cameraProbe) {
    hudText = "TRIGGERS " + std::to_string(activeCount) + "/" + std::to_string(triggers.size()) +
              (cameraProbe ? "  PROBE CAMERA" : "  PROBE PLAYER") + "\n";
    if (!error.empty()) hudText += error + "\n";
    else if (activeCount == 0) hudText += "ACTIVE: NONE\n";
    else {
        size_t shown = 0;
        for (const auto& trigger: triggers) if (trigger.inside) {
            hudText += DisplayName(trigger.name) + "\n";
            if (++shown == 4) break;
        }
        if (activeCount > shown) hudText += "+ " + std::to_string(activeCount-shown) + " OTHER ACTIVE\n";
    }
    if (!lastEntered.empty()) hudText += "LAST ENTER: " + DisplayName(lastEntered).substr(0,62) + "\n";
    lastCameraProbe = cameraProbe; dirty = false;
}
