#pragma once
#include <cstddef>
#include <cstdint>

enum class AlphaMode : uint8_t { Opaque = 0, Mask = 1, Blend = 2 };

struct MaterialSettings {
    AlphaMode alphaMode = AlphaMode::Opaque;
    float alphaCutoff = 0.5f;
    bool doubleSided = false;
};

// Старые BIN не содержат режима материала. Это только приближение:
// бинарная маска / много нулевых и непрозрачных пикселей -> вырезаемая поверхность;
// преимущественно промежуточная альфа -> полупрозрачная поверхность.
// Явные данные экспортёра всегда имеют приоритет.
inline MaterialSettings GuessMaterialSettings(const void* rgba, size_t bytes) {
    MaterialSettings result;
    if (!rgba || bytes == 0 || bytes % 4 != 0) return result;
    const auto* pixels = static_cast<const uint8_t*>(rgba);
    const size_t count = bytes / 4;
    size_t transparent = 0, opaque = 0;
    for (size_t i = 3; i < bytes; i += 4) {
        transparent += pixels[i] <= 5;
        opaque += pixels[i] >= 250;
    }
    if (opaque == count) return result;
    const size_t intermediate = count - transparent - opaque;
    const bool looksLikeMask = intermediate <= count / 20
        || (transparent >= (count + 9) / 10 && opaque >= (count + 9) / 10);
    result.alphaMode = looksLikeMask ? AlphaMode::Mask : AlphaMode::Blend;
    result.doubleSided = true;
    return result;
}
