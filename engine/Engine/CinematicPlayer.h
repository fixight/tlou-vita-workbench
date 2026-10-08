#pragma once
#include "CinematicClock.h"
#include "CinematicLens.h"
#include "SkinnedModel.h"
#include "PlayerControl.h"
#include "Managers/AudioManager.h"
#include <memory>

class Character;
class CameraActor;

// Owns cinematic models and a single clock for every actor and camera.
// The resource supplies control changes and sound cues on the same clock.
class CinematicPlayer {
public:
    bool Load(const char* path, MemoryManager& memory);
    bool LoadWorldMask(const char* path, const char* levelPath, std::vector<Instance>& world, MemoryManager& memory);
    void ApplyWorldMask(std::vector<Instance>& world, bool enabled);
    bool PrepareAudio(AudioManager& manager);
    const PlayerControl& GetControl() const { return currentControl; }
    bool Play();
    void Update(double deltaSeconds);
    void Draw(CameraActor* camera, const std::vector<EngineLight>& lights,
              GLuint shader, RenderStats& stats);
    void ApplyCamera(CameraActor& camera) const;
    void ApplyPlayerAnchor(Character& character) const;
    void ApplyGameplayHandoff(Character& character) const;
    void Cancel();
    double GetPlaybackTime() const { return clock.Time(); }
    bool IsPlaying() const { return clock.IsPlaying(); }
    bool ConsumeFinished() { return clock.ConsumeFinished(); }
    CinematicClock::State GetState() const { return clock.GetState(); }
    const std::string& GetName() const { return name; }
    const std::string& GetLastError() const { return error; }
private:
    struct WorldPatch { unsigned index; Mesh* original; Mesh* replacement; };
    std::vector<WorldPatch> worldPatches;
    struct Pose { glm::vec3 position; glm::quat rotation; };
    struct Track { float fps = 30; std::vector<Pose> samples; };
    struct LensTrack {
        float fps = 30;
        std::vector<CinematicLens> samples;
    };
    struct Actor {
        std::unique_ptr<SkinnedModel> model;
        unsigned clip = 0;
        Track motion;
        glm::mat4 world{1};
    };
    struct Stage {
        float duration = 0, fov = 60;
        std::vector<Actor> actors;
        Track camera, player;
        LensTrack lens;
    };
    static Pose Sample(const Track& track, float time, bool cameraCuts = false);
    static CinematicLens SampleLens(const Stage& stage, float time);
    void SampleStage(float time);
    struct ControlCue { float time; PlayerControl policy; };
    struct AudioCue { float time; std::string sound; SoundOptions options; };
    std::vector<ControlCue> controlCues;
    std::vector<AudioCue> audioCues;
    std::vector<std::string> audioBanks;
    std::vector<SoundHandle> sceneVoices;
    AudioManager* audio = nullptr;
    size_t nextAudioCue = 0;
    PlayerControl currentControl = PlayerControl::FullCinematic();
    void DispatchEvents();
    void StopAudio();
    CinematicClock clock;
    std::string name, error;
    std::vector<Stage> stages;
    unsigned currentStage = 0;
    glm::vec3 handoffPosition{};
    float handoffYaw = 0;
    float currentFov = 60;
    CinematicLens currentLens{};
    bool hasLens = false;
    Pose cameraPose{}, playerPose{};
};
