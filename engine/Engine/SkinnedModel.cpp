#include "SkinnedModel.h"
#include "Memory/MemoryManager.h"
#include "Objects/CameraActor.h"

#include <glm/gtc/matrix_transform.hpp>
#include <glm/gtc/type_ptr.hpp>
#include <psp2/kernel/clib.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <stdexcept>

// SK16 v1/v2 — little-endian; Vita читает его поля в том же порядке,
// в котором export_vita_character.py их записывает.
class SkinnedBinaryReader {
public:
    explicit SkinnedBinaryReader(const char* path) {
        m_file = fopen(path, "rb");
        if (!m_file) {
            throw std::runtime_error("file missing");
        }

        fseek(m_file, 0, SEEK_END);
        const long fileSize = ftell(m_file);
        rewind(m_file);

        constexpr long MinimumFileSize = 20;
        constexpr long MaximumFileSize = 32 * 1024 * 1024;
        if (fileSize < MinimumFileSize || fileSize > MaximumFileSize) {
            fclose(m_file);
            m_file = nullptr;
            throw std::runtime_error("file size");
        }
        m_remainingBytes = fileSize;
    }

    ~SkinnedBinaryReader() {
        if (m_file) {
            fclose(m_file);
        }
    }

    void ReadBytes(void* destination, size_t byteCount) {
        if (byteCount > m_remainingBytes ||
            fread(destination, 1, byteCount, m_file) != byteCount) {
            throw std::runtime_error("truncated SK16");
        }
        m_remainingBytes -= byteCount;
    }

    template<class T>
    T Read() {
        T value;
        ReadBytes(&value, sizeof(value));
        return value;
    }

    std::string ReadString(unsigned byteCount) {
        if (byteCount > 1024) {
            throw std::runtime_error("string length");
        }
        std::string result(byteCount, '\0');
        ReadBytes(result.data(), byteCount);
        return result;
    }

    size_t RemainingBytes() const { return m_remainingBytes; }

private:
    FILE* m_file = nullptr;
    size_t m_remainingBytes = 0;
};

namespace {
struct VertexAttributes {
    GLint position;
    GLint texCoord;
    GLint octNormal;
    GLint boneIds;
    GLint weight;
};

void SetAttributesEnabled(const VertexAttributes& attributes, bool enabled) {
    for (GLint location : {attributes.position, attributes.texCoord,
                           attributes.octNormal, attributes.boneIds,
                           attributes.weight}) {
        if (location < 0) {
            continue;
        }
        if (enabled) {
            glEnableVertexAttribArray(location);
        } else {
            glDisableVertexAttribArray(location);
        }
    }
}

void BindVertexLayout(const VertexAttributes& attributes) {
    constexpr GLsizei stride = sizeof(SkinnedVertex);
    if (attributes.position >= 0) {
        glVertexAttribPointer(attributes.position, 3, GL_SHORT, GL_FALSE,
                              stride, (void*)offsetof(SkinnedVertex, x));
    }
    if (attributes.texCoord >= 0) {
        glVertexAttribPointer(attributes.texCoord, 2, GL_HALF_FLOAT, GL_FALSE,
                              stride, (void*)offsetof(SkinnedVertex, u));
    }
    if (attributes.octNormal >= 0) {
        glVertexAttribPointer(attributes.octNormal, 2, GL_BYTE, GL_TRUE,
                              stride, (void*)offsetof(SkinnedVertex, oct_nx));
    }
    if (attributes.boneIds >= 0) {
        glVertexAttribPointer(attributes.boneIds, 2, GL_UNSIGNED_BYTE, GL_FALSE,
                              stride, (void*)offsetof(SkinnedVertex, bone_ids));
    }
    if (attributes.weight >= 0) {
        glVertexAttribPointer(attributes.weight, 1, GL_UNSIGNED_BYTE, GL_TRUE,
                              stride, (void*)offsetof(SkinnedVertex, weight));
    }
}

GLint FindBonePaletteUniform(GLuint shader) {
    // vitaGL без STRICT_UNIFORMS_COMPLIANCE ищет массив по базовому имени.
    // Корректные location могут быть отрицательными: отсутствующий — только -1.
    GLint location = glGetUniformLocation(shader, "uBones");
    if (location == -1) {
        location = glGetUniformLocation(shader, "uBones[0]");
    }
    return location;
}

void UploadCharacterLights(GLuint shader, const glm::vec3& actorPosition,
                           const std::vector<EngineLight>& lights) {
    const EngineLight* selectedLights[2] = {nullptr, nullptr};
    float selectedInfluence[2] = {0, 0};

    // Выбираем два наиболее влиятельных источника в точке персонажа.
    for (const EngineLight& light : lights) {
        const float radiusSquared = light.radius * light.radius;
        if (radiusSquared <= 0.001f) {
            continue;
        }
        const glm::vec3 offset = light.position - actorPosition;
        const float influence = 1 - glm::dot(offset, offset) / radiusSquared;
        if (influence <= 0) {
            continue;
        }

        if (influence > selectedInfluence[0]) {
            selectedInfluence[1] = selectedInfluence[0];
            selectedLights[1] = selectedLights[0];
            selectedInfluence[0] = influence;
            selectedLights[0] = &light;
        } else if (influence > selectedInfluence[1]) {
            selectedInfluence[1] = influence;
            selectedLights[1] = &light;
        }
    }

    for (int lightIndex = 0; lightIndex < 2; ++lightIndex) {
        const char* positionName = lightIndex ? "uLightPos1" : "uLightPos0";
        const char* colorName = lightIndex ? "uLightColor1" : "uLightColor0";
        const char* radiusName = lightIndex ? "uLightRadius1" : "uLightRadius0";

        glm::vec3 position(0);
        glm::vec3 color(0);
        float radius = 0;
        if (selectedLights[lightIndex]) {
            const EngineLight& light = *selectedLights[lightIndex];
            position = light.position;
            color = light.color;
            if (std::max({color.x, color.y, color.z}) > 1) {
                color /= 255.f;
            }
            radius = light.radius;
        }

        glUniform3fv(glGetUniformLocation(shader, positionName), 1,
                     glm::value_ptr(position));
        glUniform3fv(glGetUniformLocation(shader, colorName), 1,
                     glm::value_ptr(color));
        glUniform1f(glGetUniformLocation(shader, radiusName), radius);
    }
}

void BindCharacterTexture(Texture& texture, GLuint& lastTexture,
                          RenderStats& stats) {
    if (!texture.textureID) {
        glGenTextures(1, &texture.textureID);
        glBindTexture(GL_TEXTURE_2D, texture.textureID);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, texture.size_x, texture.size_y,
                     0, GL_RGBA, GL_UNSIGNED_BYTE, texture.dataPointer);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
        stats.textureUploadBytes += uint64_t(texture.size_x) * texture.size_y * 4;
        lastTexture = 0;
    }
    if (texture.textureID != lastTexture) {
        glBindTexture(GL_TEXTURE_2D, texture.textureID);
        lastTexture = texture.textureID;
        ++stats.textureBinds;
    }
}
}  // namespace

SkinnedModel::~SkinnedModel() {
    ReleaseGpuBuffers();
}

void SkinnedModel::ReleaseGpuBuffers() {
    for (Batch& batch : m_batches) {
        if (batch.vertexBuffer) {
            glDeleteBuffers(1, &batch.vertexBuffer);
        }
        if (batch.indexBuffer) {
            glDeleteBuffers(1, &batch.indexBuffer);
        }
    }
}

bool SkinnedModel::Load(const char* path, MemoryManager& memory) {
    if (!m_batches.empty() || !m_clips.empty()) {
        return false;
    }

    try {
        SkinnedBinaryReader reader(path);
        char magic[4];
        reader.ReadBytes(magic, sizeof(magic));
        const unsigned version = reader.Read<uint32_t>();
        const unsigned batchCount = reader.Read<uint32_t>();
        m_jointCount = reader.Read<uint32_t>();
        const unsigned clipCount = reader.Read<uint32_t>();

        if (memcmp(magic, "SK16", 4) || (version != 1 && version != 2) ||
            !batchCount || batchCount > 512 ||
            !m_jointCount || m_jointCount > 1024 ||
            !clipCount || clipCount > 64) {
            throw std::runtime_error("SK16 header");
        }

        // v2 adds bind-space joint centres; vertices and animation matrices are unchanged.
        m_bindPivots.resize(m_jointCount, glm::vec3(0.f));
        if (version == 2) {
            for (glm::vec3& pivot : m_bindPivots) {
                reader.ReadBytes(&pivot[0], 3 * sizeof(float));
                if (!std::isfinite(pivot.x) || !std::isfinite(pivot.y) || !std::isfinite(pivot.z))
                    throw std::runtime_error("non-finite bind pivot");
            }
        }
        LoadBatches(reader, batchCount, memory);
        LoadClips(reader, clipCount);
        if (reader.RemainingBytes()) {
            throw std::runtime_error("SK16 trailing bytes");
        }

        m_textureBytes = CalculateTextureBytes();
        m_currentPoseMatrices.resize(m_jointCount * MatrixFloatCount);
        m_transitionSource.resize(m_jointCount);
        Update(0, 0);  // Сразу создаём первую позу, даже до первого игрового кадра.
        glBindBuffer(GL_ARRAY_BUFFER, 0);
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);
        sceClibPrintf("SK16 loaded: %u batches, %u skin matrices, %u clips, vertex=16 bytes\n",
                      batchCount, m_jointCount, clipCount);
        return true;
    } catch (const std::exception& error) {
        sceClibPrintf("SK16 load failed: %s\n", error.what());
        ReleaseGpuBuffers();
        m_batches.clear();
        m_clips.clear();
        m_currentPoseMatrices.clear();
        m_transitionSource.clear();
        m_bindPivots.clear();
        m_hasPose = m_transitionActive = false;
        glBindBuffer(GL_ARRAY_BUFFER, 0);
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);
        return false;
    }
}

void SkinnedModel::LoadBatches(SkinnedBinaryReader& reader, unsigned batchCount,
                              MemoryManager& memory) {
    m_batches.reserve(batchCount);
    for (unsigned batchIndex = 0; batchIndex < batchCount; ++batchIndex) {
        // Добавляем сразу: если чтение прервётся, Load() освободит его GPU-буферы.
        m_batches.emplace_back();
        Batch& batch = m_batches.back();
        batch.vertexCount = reader.Read<uint32_t>();
        batch.indexCount = reader.Read<uint32_t>();
        const unsigned paletteSize = reader.Read<uint32_t>();
        const unsigned texturePathSize = reader.Read<uint32_t>();
        reader.ReadBytes(&batch.positionOrigin[0], 3 * sizeof(float));
        batch.positionStep = reader.Read<float>();

        if (!batch.vertexCount || batch.vertexCount > 65535 ||
            !batch.indexCount || batch.indexCount > 300000 || batch.indexCount % 3 ||
            !paletteSize || paletteSize > PaletteLimit ||
            !std::isfinite(batch.positionStep) || batch.positionStep <= 0) {
            throw std::runtime_error("SK16 batch bounds");
        }

        const std::string texturePath = reader.ReadString(texturePathSize);
        if (texturePath.find("app0:/") != 0 ||
            texturePath.find("..") != std::string::npos) {
            throw std::runtime_error("texture path");
        }
        batch.bonePalette.resize(paletteSize);
        reader.ReadBytes(batch.bonePalette.data(), paletteSize * sizeof(uint16_t));
        for (uint16_t jointIndex : batch.bonePalette) {
            if (jointIndex >= m_jointCount) {
                throw std::runtime_error("palette index");
            }
        }

        std::vector<SkinnedVertex> vertices(batch.vertexCount);
        std::vector<uint16_t> indices(batch.indexCount);
        reader.ReadBytes(vertices.data(), vertices.size() * sizeof(SkinnedVertex));
        reader.ReadBytes(indices.data(), indices.size() * sizeof(uint16_t));
        for (const SkinnedVertex& vertex : vertices) {
            if (vertex.bone_ids[0] >= paletteSize ||
                vertex.bone_ids[1] >= paletteSize || vertex.reserved) {
                throw std::runtime_error("vertex palette index");
            }
        }
        for (uint16_t vertexIndex : indices) {
            if (vertexIndex >= batch.vertexCount) {
                throw std::runtime_error("mesh index");
            }
        }
        batch.texture = memory.getTexture(texturePath);
        if (!batch.texture) {
            throw std::runtime_error("texture load");
        }

        glGenBuffers(1, &batch.vertexBuffer);
        glBindBuffer(GL_ARRAY_BUFFER, batch.vertexBuffer);
        glBufferData(GL_ARRAY_BUFFER, vertices.size() * sizeof(SkinnedVertex),
                     vertices.data(), GL_STATIC_DRAW);
        glGenBuffers(1, &batch.indexBuffer);
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, batch.indexBuffer);
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.size() * sizeof(uint16_t),
                     indices.data(), GL_STATIC_DRAW);
        // CPU-копии vertices/indices больше не нужны после загрузки в GPU.
    }
}

void SkinnedModel::LoadClips(SkinnedBinaryReader& reader, unsigned clipCount) {
    for (unsigned clipIndex = 0; clipIndex < clipCount; ++clipIndex) {
        const unsigned nameSize = reader.Read<uint32_t>();
        Clip clip;
        clip.frameCount = reader.Read<uint32_t>();
        clip.durationSeconds = reader.Read<float>();
        clip.name = reader.ReadString(nameSize);
        if (clip.frameCount < 2 || clip.frameCount > 10000 ||
            !std::isfinite(clip.durationSeconds) || clip.durationSeconds <= 0) {
            throw std::runtime_error("clip bounds");
        }

        const size_t floatCount = size_t(clip.frameCount) * m_jointCount * MatrixFloatCount;
        if (floatCount > reader.RemainingBytes() / sizeof(float)) {
            throw std::runtime_error("clip size");
        }
        clip.skinMatrices.resize(floatCount);
        reader.ReadBytes(clip.skinMatrices.data(), floatCount * sizeof(float));
        for (float component : clip.skinMatrices) {
            if (!std::isfinite(component)) {
                throw std::runtime_error("non-finite pose");
            }
        }
        m_clips.push_back(std::move(clip));
    }
}

uint64_t SkinnedModel::CalculateTextureBytes() const {
    std::vector<Texture*> countedTextures;
    uint64_t totalBytes = 0;
    for (const Batch& batch : m_batches) {
        if (std::find(countedTextures.begin(), countedTextures.end(), batch.texture) ==
            countedTextures.end()) {
            countedTextures.push_back(batch.texture);
            totalBytes += uint64_t(batch.texture->size_x) * batch.texture->size_y * 4;
        }
    }
    return totalBytes;
}

float SkinnedModel::GetClipDuration(unsigned clipIndex) const {
    return clipIndex < m_clips.size() ? m_clips[clipIndex].durationSeconds : 0.f;
}

void SkinnedModel::Update(float deltaTime, unsigned clipIndex, bool loop, float transitionSeconds) {
    if (m_clips.empty()) {
        return;
    }
    clipIndex = std::min(clipIndex, unsigned(m_clips.size() - 1));
    SelectClip(clipIndex, transitionSeconds);
    m_activeLoops = loop;

    const Clip& clip = m_clips[clipIndex];
    const float nextTime = m_playbackTimeSeconds + std::max(0.f, deltaTime);
    m_playbackTimeSeconds = loop ? std::fmod(nextTime, clip.durationSeconds)
                                 : std::min(nextTime, clip.durationSeconds);
    EvaluatePose(deltaTime);
}

SkinnedModel::FrameSample SkinnedModel::FindFrameSamples(const Clip& clip) const {
    const float framePosition = m_playbackTimeSeconds / clip.durationSeconds *
                                (clip.frameCount - 1);
    const unsigned firstFrame = unsigned(framePosition);
    const unsigned secondFrame = std::min(firstFrame + 1, clip.frameCount - 1);
    return {firstFrame, secondFrame, framePosition - firstFrame};
}

void SkinnedModel::InterpolatePose(const Clip& clip, const FrameSample& sample) {
    const size_t floatsPerPose = m_jointCount * MatrixFloatCount;
    const size_t firstFrameOffset = sample.firstFrame * floatsPerPose;
    const size_t secondFrameOffset = sample.secondFrame * floatsPerPose;

    // Линейно смешиваем готовые матрицы между отсчётами 30 Гц.
    // Переход между клипами отдельно смешивает вращение и перенос в EvaluatePose().
    for (size_t component = 0; component < floatsPerPose; ++component) {
        m_currentPoseMatrices[component] =
            clip.skinMatrices[firstFrameOffset + component] * (1 - sample.blendWeight) +
            clip.skinMatrices[secondFrameOffset + component] * sample.blendWeight;
    }
}

void SkinnedModel::CopyBonePalette(const Batch& batch, float* destination) const {
    for (unsigned paletteIndex = 0; paletteIndex < batch.bonePalette.size(); ++paletteIndex) {
        const unsigned jointIndex = batch.bonePalette[paletteIndex];
        memcpy(destination + paletteIndex * MatrixFloatCount,
               m_currentPoseMatrices.data() + jointIndex * MatrixFloatCount,
               MatrixFloatCount * sizeof(float));
    }
}

void SkinnedModel::Draw(const glm::mat4& modelMatrix, CameraActor* camera,
                        const std::vector<EngineLight>& lights, GLuint shader,
                        RenderStats& stats) {
    if (m_batches.empty() || !camera || !shader) {
        return;
    }

    const auto cameraPosition = camera->GetPosition();
    const auto cameraForward = camera->GetForwardVector();
    const glm::vec3 eye(cameraPosition.x, cameraPosition.y, cameraPosition.z);
    const glm::vec3 forward(cameraForward.x, cameraForward.y, cameraForward.z);
    const glm::mat4 modelViewProjection =
        camera->GetProjectionMatrix() * camera->GetViewMatrix() * modelMatrix;
    const glm::mat3 normalMatrix = glm::transpose(glm::inverse(glm::mat3(modelMatrix)));

    glUseProgram(shader);
    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LEQUAL);
    glDepthMask(GL_TRUE);
    glDisable(GL_BLEND);
    glDisable(GL_CULL_FACE);

    const auto findUniform = [shader](const char* name) {
        return glGetUniformLocation(shader, name);
    };
    glUniformMatrix4fv(findUniform("uMVP"), 1, GL_FALSE, glm::value_ptr(modelViewProjection));
    glUniformMatrix4fv(findUniform("uModel"), 1, GL_FALSE, glm::value_ptr(modelMatrix));
    glUniformMatrix3fv(findUniform("uNormalMatrix"), 1, GL_FALSE, glm::value_ptr(normalMatrix));
    glUniform1i(findUniform("uTexture"), 0);
    glUniform3f(findUniform("uAmbientLight"), 0.35f, 0.35f, 0.38f);
    UploadCharacterLights(shader, glm::vec3(modelMatrix[3]), lights);

    const VertexAttributes attributes{
        glGetAttribLocation(shader, "aPosition"),
        glGetAttribLocation(shader, "aTexCoord"),
        glGetAttribLocation(shader, "aOctNormal"),
        glGetAttribLocation(shader, "aBoneIds"),
        glGetAttribLocation(shader, "aWeight")
    };
    SetAttributesEnabled(attributes, true);
    glActiveTexture(GL_TEXTURE0);

    const GLint bonesLocation = FindBonePaletteUniform(shader);
    if (bonesLocation == -1) {
        static bool reportedMissingPalette = false;
        if (!reportedMissingPalette) {
            sceClibPrintf("SK16 ERROR: bone palette uniform not found\n");
            reportedMissingPalette = true;
        }
        SetAttributesEnabled(attributes, false);
        glUseProgram(0);
        return;
    }
    static bool reportedPalette = false;
    if (!reportedPalette) {
        sceClibPrintf("SK16 bone palette bound: location=%d; %u batches\n",
                      bonesLocation, unsigned(m_batches.size()));
        reportedPalette = true;
    }
    const GLint originLocation = findUniform("uPositionOrigin");
    const GLint stepLocation = findUniform("uPositionStep");

    GLuint lastTexture = 0;
    float paletteMatrices[PaletteLimit * MatrixFloatCount];
    for (Batch& batch : m_batches) {
        BindCharacterTexture(*batch.texture, lastTexture, stats);
        CopyBonePalette(batch, paletteMatrices);
        glUniformMatrix4fv(bonesLocation, batch.bonePalette.size(), GL_FALSE, paletteMatrices);
        glUniform3fv(originLocation, 1, glm::value_ptr(batch.positionOrigin));
        glUniform1f(stepLocation, batch.positionStep);

        glBindBuffer(GL_ARRAY_BUFFER, batch.vertexBuffer);
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, batch.indexBuffer);
        ++stats.vboBinds;
        BindVertexLayout(attributes);
        glDrawElements(GL_TRIANGLES, batch.indexCount, GL_UNSIGNED_SHORT, 0);
        ++stats.drawCalls;
        ++stats.objectsDrawn;
        ++stats.objectsTested;
        stats.vertices += batch.indexCount;
        stats.triangles += batch.indexCount / 3;
    }

    SetAttributesEnabled(attributes, false);
    glBindBuffer(GL_ARRAY_BUFFER, 0);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);
    glBindTexture(GL_TEXTURE_2D, 0);
    glUseProgram(0);
    stats.visibleTextureBytes += m_textureBytes;
}

int SkinnedModel::FindClip(const char* name) const {
    if(!name)return -1;
    for(unsigned i=0;i<m_clips.size();++i)if(m_clips[i].name==name)return int(i);
    return -1;
}
void SkinnedModel::SampleAt(unsigned clipIndex, float timeSeconds, float deltaTime) {
    if (clipIndex >= m_clips.size()) return;
    SelectClip(clipIndex);
    m_activeLoops = false;
    // External clock remains exact: cross-fading must not delay door/root motion.
    m_playbackTimeSeconds = std::max(0.f, std::min(timeSeconds, m_clips[clipIndex].durationSeconds));
    EvaluatePose(deltaTime);
}

void SkinnedModel::SetTransitionDuration(float seconds) {
    if (!std::isfinite(seconds)) return;
    m_transitionDuration = std::max(0.f, seconds);
    if (m_transitionDuration == 0.f) m_transitionActive = false;
}

SkinnedModel::JointPose SkinnedModel::DecomposeJoint(const float* values, const glm::vec3& bindPivot) {
    const glm::mat4 matrix = glm::make_mat4(values);
    glm::vec3 x(matrix[0]), y(matrix[1]), z(matrix[2]);
    glm::vec3 scale(glm::length(x), glm::length(y), glm::length(z));
    if (glm::dot(glm::cross(x, y), z) < 0.f) scale.x = -scale.x;
    // Clips contain affine skin transforms. Guard degenerate basis vectors.
    x = std::abs(scale.x) > 1e-8f ? x / scale.x : glm::vec3(1, 0, 0);
    y = scale.y > 1e-8f ? y / scale.y : glm::vec3(0, 1, 0);
    z = scale.z > 1e-8f ? z / scale.z : glm::vec3(0, 0, 1);
    return {glm::vec3(matrix * glm::vec4(bindPivot, 1.f)), glm::normalize(glm::quat_cast(glm::mat3(x, y, z))), scale};
}

void SkinnedModel::SelectClip(unsigned clipIndex, float transitionSeconds) {
    if (clipIndex == m_activeClipIndex) return;
    // Only an unblended source has a clip clock. Interrupted fades retain the visible pose.
    m_sourceAdvances = m_hasPose && !m_transitionActive;
    m_sourceClipIndex = m_activeClipIndex;
    m_sourceTimeSeconds = m_playbackTimeSeconds;
    m_sourceLoops = m_activeLoops;
    m_activeTransitionDuration = std::isfinite(transitionSeconds) && transitionSeconds >= 0.f
        ? transitionSeconds : m_transitionDuration;
    m_transitionActive = m_hasPose && m_activeTransitionDuration > 0.f;
    m_transitionElapsed = 0.f;
    if (m_transitionActive) {
        // Capture what is currently rendered, including a partially completed fade.
        for (unsigned joint = 0; joint < m_jointCount; ++joint)
            m_transitionSource[joint] = DecomposeJoint(m_currentPoseMatrices.data() + joint * MatrixFloatCount, m_bindPivots[joint]);
    }
    m_activeClipIndex = clipIndex;
    m_playbackTimeSeconds = 0.f;
}

void SkinnedModel::EvaluatePose(float deltaTime) {
    if (m_transitionActive) {
        m_transitionElapsed += std::max(0.f, deltaTime);
        if (m_transitionElapsed == 0.f) return; // Exact visible pose on a zero-time switch.
        if (m_transitionElapsed >= m_activeTransitionDuration) m_transitionActive = false;
        if (m_transitionActive && m_sourceAdvances) {
            // Keep the outgoing motion alive instead of fading from a frozen shoulder pose.
            const Clip& source = m_clips[m_sourceClipIndex];
            const float next = m_sourceTimeSeconds + std::max(0.f, deltaTime);
            m_sourceTimeSeconds = m_sourceLoops ? std::fmod(next, source.durationSeconds)
                                               : std::min(next, source.durationSeconds);
            const float frame = m_sourceTimeSeconds / source.durationSeconds * (source.frameCount - 1);
            const unsigned first = unsigned(frame), second = std::min(first + 1, source.frameCount - 1);
            const float weight = frame - first;
            const size_t stride = m_jointCount * MatrixFloatCount;
            for (unsigned joint = 0; joint < m_jointCount; ++joint) {
                float matrix[MatrixFloatCount];
                for (size_t component = 0; component < MatrixFloatCount; ++component) {
                    const size_t offset = joint * MatrixFloatCount + component;
                    matrix[component] = source.skinMatrices[first * stride + offset] * (1.f - weight)
                                      + source.skinMatrices[second * stride + offset] * weight;
                }
                m_transitionSource[joint] = DecomposeJoint(matrix, m_bindPivots[joint]);
            }
        }
    }
    const Clip& clip = m_clips[m_activeClipIndex];
    InterpolatePose(clip, FindFrameSamples(clip));
    m_hasPose = true;
    if (m_transitionActive) {
        const float t = m_transitionElapsed / m_activeTransitionDuration;
        BlendTransition(t * t * (3.f - 2.f * t)); // Smooth start and finish.
    }
}

void SkinnedModel::BlendTransition(float weight) {
    for (unsigned joint = 0; joint < m_jointCount; ++joint) {
        float* output = m_currentPoseMatrices.data() + joint * MatrixFloatCount;
        const JointPose target = DecomposeJoint(output, m_bindPivots[joint]);
        const JointPose& source = m_transitionSource[joint];
        glm::quat rotation = target.rotation;
        if (glm::dot(source.rotation, rotation) < 0.f) rotation = -rotation;
        // Shortest-path normalized lerp avoids collapsing rotating limbs.
        rotation = glm::normalize(source.rotation * (1.f - weight) + rotation * weight);
        const glm::vec3 translation = source.translation * (1.f - weight) + target.translation * weight;
        const glm::vec3 scale = source.scale * (1.f - weight) + target.scale * weight;
        glm::mat4 matrix = glm::mat4_cast(rotation);
        matrix[0] *= scale.x;
        matrix[1] *= scale.y;
        matrix[2] *= scale.z;
        // Skin transforms include inverse bind. Interpolate the actual joint centre,
        // then reconstruct skin translation around its bind-space pivot.
        matrix[3] = glm::vec4(translation - glm::mat3(matrix) * m_bindPivots[joint], 1.f);
        std::memcpy(output, glm::value_ptr(matrix), MatrixFloatCount * sizeof(float));
    }
}
