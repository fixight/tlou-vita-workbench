#pragma once
#include <cmath>
#include <algorithm>

// Native cinematic lens. Depth of field is authored as four distance planes,
// not a single focus point. These values do not automatically enable a blur pass.
struct CinematicLens {
    float horizontalFov = 75;
    float focalLengthMm = 23.458f;
    float defaultFovBlend = 0;
    float cutMarker = 0;
    float blurRadius = 0;
    float nearStart = 0, nearEnd = 0;
    float farStart = 0, farEnd = 0;
    float overrideDisable = 1;
    bool hasDepthOfField = false;

    void UpdateFov() {
        constexpr float degrees = 57.29577951308232f;
        const float denominator = focalLengthMm > 0 ? 2*focalLengthMm : 46.916f;
        const float nativeFov = 2*std::atan2(36.f,denominator)*degrees;
        const float blend = std::clamp(defaultFovBlend,0.f,1.f);
        horizontalFov = nativeFov*(1-blend) + 75.f*blend;
    }
    static float BlendWeight(float before, float after, float fraction) {
        const float marker = before + (after-before)*fraction;
        return std::abs(before-after) > .4f && marker > .00001f && marker < .99999f ? 1.f : fraction;
    }
    float VerticalFov(float aspect) const {
        constexpr float radians = .017453292519943295f;
        return 2 * std::atan(std::tan(horizontalFov * radians / 2) / aspect) / radians;
    }
};
