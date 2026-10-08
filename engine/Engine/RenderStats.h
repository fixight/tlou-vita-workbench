#pragma once
#include <cstdint>
#include <algorithm>

// Scene submission counters; HUD geometry is deliberately excluded.
struct RenderStats {
    uint32_t drawCalls=0, objectsTested=0, objectsDrawn=0;
    uint32_t culledDistance=0, culledFrustum=0, invalidObjects=0;
    uint32_t textureBinds=0, vboBinds=0;
    uint64_t vertices=0, triangles=0, textureUploadBytes=0, visibleTextureBytes=0;
};

struct VitaFpsRange { float low, high; };

// Explicit assumptions, NOT measurements of Vita hardware. Calibrate on a real device.
// Model: max(CPU submission budget, vertex processing budget). Excludes fill rate,
// overdraw, physics, streaming, shader complexity and HUD. Suitable only for this
// simple static one-texture shader. Never extrapolate the emulator's FPS.
inline VitaFpsRange EstimateVitaFps(const RenderStats& stats) {
    const double optimisticMs=std::max(2.0+stats.drawCalls*0.020,2.0+stats.vertices/20000.0);
    const double conservativeMs=std::max(5.0+stats.drawCalls*0.100,5.0+stats.vertices/5000.0);
    return {static_cast<float>(std::min(60.0,1000.0/conservativeMs)),
            static_cast<float>(std::min(60.0,1000.0/optimisticMs))};
}
