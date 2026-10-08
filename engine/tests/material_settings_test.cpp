#include "../System/MaterialSettings.h"
#include <cassert>
#include <iostream>
#include <vector>

MaterialSettings Classify(std::initializer_list<uint8_t> alpha) {
    std::vector<uint8_t> rgba;
    for (auto a : alpha) rgba.insert(rgba.end(), {120, 80, 40, a});
    return GuessMaterialSettings(rgba.data(), rgba.size());
}
int main() {
    assert(Classify({255,255,255}).alphaMode == AlphaMode::Opaque);
    assert(!Classify({255,255}).doubleSided);
    assert(Classify({0,255,0,255}).alphaMode == AlphaMode::Mask);
    // Filtered foliage edges must not turn the whole plant into glass.
    assert(Classify({0,255,30,80,160,220}).alphaMode == AlphaMode::Mask);
    assert(Classify({80,80,80,80}).alphaMode == AlphaMode::Blend);
    assert(Classify({0,0,0}).alphaMode == AlphaMode::Mask);
    assert(GuessMaterialSettings(nullptr,0).alphaMode == AlphaMode::Opaque);
    const uint8_t invalid[3] = {};
    assert(GuessMaterialSettings(invalid,3).alphaMode == AlphaMode::Opaque);
    std::cout << "Material alpha classification checks passed\n";
}
