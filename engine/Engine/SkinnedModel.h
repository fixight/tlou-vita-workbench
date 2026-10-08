#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <glm/glm.hpp>
#include <glm/gtc/quaternion.hpp>

#include "System/DataLoader.h"
#include "Engine/RenderStats.h"

class MemoryManager;
class CameraActor;
class SkinnedBinaryReader;

// Проигрывает экспортированные SK16-клипы. CPU вычисляет позу костей,
// GPU деформирует меш. Иерархия и ключи glTF уже обработаны экспортёром на ПК.
class SkinnedModel {
public:
    static constexpr unsigned PaletteLimit = 24;

    bool Load(const char* path, MemoryManager& memory);
    void Update(float deltaTime, unsigned clipIndex, bool loop = true,
                float transitionSeconds = -1.f);
    float GetClipDuration(unsigned clipIndex) const;
    int FindClip(const char* name) const;
    void SampleAt(unsigned clipIndex, float timeSeconds, float deltaTime = 0.f);
    // Duration of clip changes; zero disables cross-fades.
    void SetTransitionDuration(float seconds);
    void Draw(const glm::mat4& modelMatrix, CameraActor* camera,
              const std::vector<EngineLight>& lights, GLuint shader,
              RenderStats& stats);
    ~SkinnedModel();

private:
    static constexpr size_t MatrixFloatCount = 16;

    struct Batch {
        GLuint vertexBuffer = 0;
        GLuint indexBuffer = 0;
        uint32_t vertexCount = 0;
        uint32_t indexCount = 0;

        // bindPosition = positionOrigin + packedPosition * positionStep.
        glm::vec3 positionOrigin{};
        float positionStep = 0.001f;

        // Индекс в вершине -> индекс матрицы в общей позе персонажа.
        std::vector<uint16_t> bonePalette;
        Texture* texture = nullptr;  // Принадлежит MemoryManager.
    };

    struct Clip {
        std::string name;
        uint32_t frameCount = 0;
        float durationSeconds = 0;

        // [кадр][кость][16 float]. Матрицы column-major, как в OpenGL/GLM.
        std::vector<float> skinMatrices;
    };

    struct FrameSample {
        unsigned firstFrame;
        unsigned secondFrame;
        float blendWeight;
    };

    void LoadBatches(SkinnedBinaryReader& reader, unsigned batchCount,
                     MemoryManager& memory);
    void LoadClips(SkinnedBinaryReader& reader, unsigned clipCount);
    void ReleaseGpuBuffers();
    uint64_t CalculateTextureBytes() const;

    FrameSample FindFrameSamples(const Clip& clip) const;
    void InterpolatePose(const Clip& clip, const FrameSample& sample);
    struct JointPose {
        glm::vec3 translation;
        glm::quat rotation;
        glm::vec3 scale;
    };
    static JointPose DecomposeJoint(const float* matrix, const glm::vec3& bindPivot);
    void SelectClip(unsigned clipIndex, float transitionSeconds = -1.f);
    void EvaluatePose(float deltaTime);
    void BlendTransition(float weight);
    void CopyBonePalette(const Batch& batch, float* destination) const;

    std::vector<Batch> m_batches;
    std::vector<Clip> m_clips;
    std::vector<float> m_currentPoseMatrices;

    // Allocated once on load. Interrupted fades capture the visible pose.
    std::vector<JointPose> m_transitionSource;
    std::vector<glm::vec3> m_bindPivots;
    unsigned m_sourceClipIndex = 0;
    float m_sourceTimeSeconds = 0.f;
    bool m_sourceAdvances = false;
    bool m_sourceLoops = true;
    bool m_activeLoops = true;
    float m_activeTransitionDuration = 0.18f;
    float m_transitionDuration = 0.18f;
    float m_transitionElapsed = 0.f;
    bool m_transitionActive = false;
    bool m_hasPose = false;

    uint64_t m_textureBytes = 0;
    unsigned m_jointCount = 0;
    unsigned m_activeClipIndex = 0;
    float m_playbackTimeSeconds = 0;
};
