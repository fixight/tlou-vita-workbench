#include "CinematicPlayer.h"
#include "Objects/CameraActor.h"
#include "Objects/Character.h"
#include "Memory/MemoryManager.h"
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <glm/gtc/matrix_transform.hpp>
#include <glm/gtc/quaternion.hpp>

namespace {
// VCN1 is produced offline; no JSON parsing or asset lookup during playback.
class Reader {
public:
    explicit Reader(const char* path) : file(fopen(path, "rb")) {
        if (!file) throw std::runtime_error("Cinematic file not found");
    }
    ~Reader() { fclose(file); }
    void Bytes(void* output, size_t count) {
        if (fread(output, 1, count, file) != count) throw std::runtime_error("Truncated cinematic");
    }
    uint32_t U32() { uint32_t v; Bytes(&v, 4); return v; }
    float Float() {
        float v; Bytes(&v, 4);
        if (!std::isfinite(v)) throw std::runtime_error("Invalid cinematic float");
        return v;
    }
    std::string Text() {
        auto count = U32();
        if (!count || count > 1024) throw std::runtime_error("Invalid cinematic string");
        std::string v(count, ' '); Bytes(&v[0], count);
        if (v.find('\0') != std::string::npos) throw std::runtime_error("Invalid cinematic string");
        return v;
    }
    bool End() { return fgetc(file) == EOF; }
private:
    FILE* file;
};
}

bool CinematicPlayer::Load(const char* path, MemoryManager& memory) try {
    if (clock.IsPlaying()) { error = "Stop the current scene before loading"; return false; }
    Reader reader(path);
    char magic[4]; reader.Bytes(magic, 4);
    const auto version = reader.U32();
    if (memcmp(magic, "VCN1", 4) || (version < 1 || version > 3))
        throw std::runtime_error("Unsupported cinematic format");
    auto sceneName = reader.Text();
    glm::vec3 exitPosition;
    for (unsigned i = 0; i < 3; ++i) exitPosition[i] = reader.Float();
    const float exitYaw = reader.Float();
    const unsigned stageCount = reader.U32();
    if (!stageCount || stageCount > 64) throw std::runtime_error("Invalid cinematic stages");
    std::vector<Stage> prepared;
    uint64_t sampleBudget = 0;
    auto readTrack = [&]() {
        Track track; track.fps = reader.Float();
        unsigned count = reader.U32();
        sampleBudget += count;
        if (track.fps <= 0 || track.fps > 120 || !count || sampleBudget > 250000)
            throw std::runtime_error("Invalid cinematic samples");
        track.samples.resize(count);
        for (auto& pose : track.samples) {
            for (unsigned i = 0; i < 3; ++i) pose.position[i] = reader.Float();
            float x = reader.Float(), y = reader.Float(), z = reader.Float(), w = reader.Float();
            pose.rotation = glm::quat(w,x,y,z);
            if (glm::length(pose.rotation) < .5f) throw std::runtime_error("Invalid cinematic rotation");
            pose.rotation = glm::normalize(pose.rotation);
        }
        return track;
    };
    for (unsigned i = 0; i < stageCount; ++i) {
        Stage stage; stage.duration = reader.Float(); stage.fov = reader.Float();
        auto actorCount = reader.U32();
        if (stage.duration <= 0 || stage.duration > 3600 || stage.fov < 10 || stage.fov > 150 || !actorCount || actorCount > 16)
            throw std::runtime_error("Invalid cinematic stage");
        for (unsigned j = 0; j < actorCount; ++j) {
            auto modelPath = reader.Text(), clipName = reader.Text();
            Actor actor; actor.motion = readTrack();
            actor.model = std::make_unique<SkinnedModel>();
            if (!actor.model->Load(modelPath.c_str(), memory)) throw std::runtime_error("Cannot load cinematic actor: " + modelPath);
            int clip = actor.model->FindClip(clipName.c_str());
            if (clip < 0) throw std::runtime_error("Missing cinematic clip: " + clipName);
            actor.clip = unsigned(clip); actor.model->SetTransitionDuration(0);
            stage.actors.push_back(std::move(actor));
        }
        stage.camera = readTrack(); stage.player = readTrack();
        if (version >= 2) {
            stage.lens.fps = reader.Float();
            const unsigned count = reader.U32(), flags = reader.U32();
            sampleBudget += count;
            if (stage.lens.fps != stage.camera.fps || count != stage.camera.samples.size()
                || sampleBudget > 250000 || (flags & ~1u))
                throw std::runtime_error("Camera/lens samples disagree");
            stage.lens.samples.resize(count);
            for (auto& lens : stage.lens.samples) {
                lens.horizontalFov = reader.Float(); lens.focalLengthMm = reader.Float();
                lens.defaultFovBlend = reader.Float(); lens.cutMarker = reader.Float();
                lens.blurRadius = reader.Float(); lens.nearStart = reader.Float();
                lens.nearEnd = reader.Float(); lens.farStart = reader.Float();
                lens.farEnd = reader.Float(); lens.overrideDisable = reader.Float();
                lens.hasDepthOfField = (flags & 1) != 0;
                if (lens.horizontalFov <= 0 || lens.horizontalFov >= 180)
                    throw std::runtime_error("Invalid cinematic lens FOV");
            }
        }
        prepared.push_back(std::move(stage));
    }
    std::vector<ControlCue> controls;
    std::vector<AudioCue> sounds;
    std::vector<std::string> banks;
    double duration = 0;
    for (const auto& stage : prepared) duration += stage.duration;
    if (version >= 3) {
        const unsigned count = reader.U32();
        if (!count || count > 1024) throw std::runtime_error("Invalid control cues");
        for (unsigned i = 0; i < count; ++i) {
            const float time = reader.Float();
            const unsigned flags = reader.U32();
            if (time < 0 || time >= duration || (i == 0 && time != 0)
                || (i && time <= controls.back().time) || (flags & ~63u))
                throw std::runtime_error("Invalid control cue");
            PlayerControl policy;
            policy.characterPose = flags & 1 ? PoseOwner::Cinematic : PoseOwner::Gameplay;
            policy.cameraPose = flags & 2 ? PoseOwner::Cinematic : PoseOwner::Gameplay;
            policy.movement = flags & 4; policy.cameraLook = flags & 8;
            policy.interaction = flags & 16; policy.debugCamera = flags & 32;
            controls.push_back({time,policy});
        }
        const unsigned bankCount = reader.U32();
        if (bankCount > 64) throw std::runtime_error("Too many cinematic audio banks");
        for (unsigned i = 0; i < bankCount; ++i) banks.push_back(reader.Text());
        const unsigned soundCount = reader.U32();
        if (soundCount > 4096) throw std::runtime_error("Too many cinematic sound cues");
        for (unsigned i = 0; i < soundCount; ++i) {
            AudioCue cue; cue.time = reader.Float(); cue.sound = reader.Text();
            cue.options.volume = reader.Float(); cue.options.pan = reader.Float();
            const unsigned loop = reader.U32();
            if (cue.time < 0 || cue.time >= duration || (i && cue.time < sounds.back().time)
                || cue.options.volume < 0 || cue.options.volume > 1
                || std::abs(cue.options.pan) > 1 || loop > 1)
                throw std::runtime_error("Invalid cinematic sound cue");
            cue.options.loop = loop ? SoundLoop::Loop : SoundLoop::Once;
            sounds.push_back(std::move(cue));
        }
    } else controls.push_back({0,PlayerControl::FullCinematic()});
    if (!reader.End()) throw std::runtime_error("Trailing cinematic bytes");
    StopAudio(); audio = nullptr;
    controlCues = std::move(controls); audioCues = std::move(sounds); audioBanks = std::move(banks);
    currentControl = controlCues.front().policy;
    stages = std::move(prepared); name = std::move(sceneName);
    handoffPosition = exitPosition; handoffYaw = exitYaw;
    clock = CinematicClock{}; error.clear(); return true;
} catch (const std::exception& exception) { error = exception.what(); return false; }

bool CinematicPlayer::Play() {
    double duration = 0;
    for (const auto& stage : stages) duration += stage.duration;
    if (!clock.Play(duration)) return false;
    StopAudio(); nextAudioCue = 0;
    currentStage = 0; SampleStage(0); DispatchEvents(); return true;
}
CinematicPlayer::Pose CinematicPlayer::Sample(const Track& track, float time, bool cameraCuts) {
    float frame = std::clamp(time * track.fps, 0.f, float(track.samples.size()-1));
    unsigned first = unsigned(frame), second = std::min(first+1, unsigned(track.samples.size()-1));
    const Pose& a = track.samples[first]; const Pose& b = track.samples[second];
    float blend = frame-first;
    // Same discontinuity guard as the extracted preview; never smear a hard cut.
    if (cameraCuts && (glm::length(a.position-b.position) > 1.f || std::abs(glm::dot(a.rotation,b.rotation)) < .9238795f)) blend = 0;
    return {glm::mix(a.position,b.position,blend), glm::slerp(a.rotation,b.rotation,blend)};
}
CinematicLens CinematicPlayer::SampleLens(const Stage& stage, float time) {
    const auto& track = stage.lens;
    float frame = std::clamp(time * track.fps, 0.f, float(track.samples.size()-1));
    unsigned first = unsigned(frame), second = std::min(first+1, unsigned(track.samples.size()-1));
    const auto& a = track.samples[first]; const auto& b = track.samples[second];
    const float blend = CinematicLens::BlendWeight(a.cutMarker,b.cutMarker,frame-first);
    auto mix = [blend](float before, float after) { return before + (after-before)*blend; };
    CinematicLens lens;
    lens.horizontalFov = mix(a.horizontalFov,b.horizontalFov);
    lens.focalLengthMm = mix(a.focalLengthMm,b.focalLengthMm);
    lens.defaultFovBlend = mix(a.defaultFovBlend,b.defaultFovBlend);
    lens.cutMarker = a.cutMarker;
    lens.blurRadius = mix(a.blurRadius,b.blurRadius);
    lens.nearStart = mix(a.nearStart,b.nearStart); lens.nearEnd = mix(a.nearEnd,b.nearEnd);
    lens.farStart = mix(a.farStart,b.farStart); lens.farEnd = mix(a.farEnd,b.farEnd);
    lens.overrideDisable = mix(a.overrideDisable,b.overrideDisable);
    lens.hasDepthOfField = a.hasDepthOfField;
    lens.UpdateFov();
    return lens;
}
void CinematicPlayer::SampleStage(float time) {
    auto& stage = stages[currentStage];
    for (auto& actor : stage.actors) {
        const Pose pose = Sample(actor.motion,time);
        actor.world = glm::translate(glm::mat4(1),pose.position) * glm::mat4_cast(pose.rotation);
        actor.model->SampleAt(actor.clip,time,0);
    }
    playerPose = Sample(stage.player,time);
    hasLens = !stage.lens.samples.empty();
    if (hasLens) {
        currentLens = SampleLens(stage,time);
        float frame = std::clamp(time*stage.camera.fps,0.f,float(stage.camera.samples.size()-1));
        const unsigned first = unsigned(frame), second = std::min(first+1,unsigned(stage.camera.samples.size()-1));
        // Apply one cut decision to pose and lens; never zoom across a cut.
        const float blend = CinematicLens::BlendWeight(stage.lens.samples[first].cutMarker,
            stage.lens.samples[second].cutMarker,frame-first);
        const auto& a = stage.camera.samples[first]; const auto& b = stage.camera.samples[second];
        cameraPose = {glm::mix(a.position,b.position,blend),glm::slerp(a.rotation,b.rotation,blend)};
    } else cameraPose = Sample(stage.camera,time,true);
    currentFov = stage.fov;
}
void CinematicPlayer::Update(double deltaSeconds) {
    if (!clock.IsPlaying()) return;
    clock.Update(deltaSeconds);
    double localTime = clock.Time(); currentStage = 0;
    while (currentStage+1 < stages.size() && localTime >= stages[currentStage].duration)
        localTime -= stages[currentStage++].duration;
    SampleStage(float(localTime));
    DispatchEvents();
    if (!clock.IsPlaying()) StopAudio();
}
void CinematicPlayer::ApplyCamera(CameraActor& camera) const {
    camera.SetCinematicPose(cameraPose.position,cameraPose.rotation,currentFov);
    if (hasLens) camera.SetCinematicLens(currentLens);
}
void CinematicPlayer::ApplyGameplayHandoff(Character& character) const {
    character.SetPosition(TLOU::Vector3(handoffPosition.x,handoffPosition.y,handoffPosition.z));
    character.SetRotation(0,handoffYaw-180.f,0);
    character.SetVelocity(TLOU::Vector3::Zero()); character.initModel();
}
void CinematicPlayer::Draw(CameraActor* camera, const std::vector<EngineLight>& lights, GLuint shader, RenderStats& stats) {
    if (stages.empty()) return;
    for (auto& actor : stages[currentStage].actors) actor.model->Draw(actor.world,camera,lights,shader,stats);
}


bool CinematicPlayer::LoadWorldMask(const char* path, const char* levelPath,
    std::vector<Instance>& world, MemoryManager& memory) try {
    Reader reader(path); char magic[4]; reader.Bytes(magic,4);
    if (memcmp(magic,"VCM1",4) || reader.U32()!=1) throw std::runtime_error("Invalid world mask");
    uint64_t expectedHash; reader.Bytes(&expectedHash,8);
    if (reader.U32()!=world.size()) throw std::runtime_error("World mask instance count mismatch");
    uint64_t hash=14695981039346656037ULL;
    // Hash the exact level before trusting instance indices from the PC exporter.
    FILE* file=fopen(levelPath,"rb");
    if (!file) throw std::runtime_error("Missing world mask level");
    unsigned char buffer[4096]; size_t n;
    while ((n=fread(buffer,1,sizeof(buffer),file)))
        for (size_t i=0;i<n;++i) hash=(hash^buffer[i])*1099511628211ULL;
    const bool badRead=ferror(file); fclose(file);
    if (badRead || hash!=expectedHash) throw std::runtime_error("World mask belongs to a different level; rebuild it");
    const auto count=reader.U32();
    if (count>world.size()) throw std::runtime_error("Invalid world mask patches");
    std::vector<WorldPatch> prepared;
    for (unsigned i=0;i<count;++i) {
        const auto index=reader.U32(), length=reader.U32();
        if (index>=world.size() || length>1024) throw std::runtime_error("Invalid world mask entry");
        std::string model(length,' '); reader.Bytes(model.data(),length);
        Mesh* replacement=length ? memory.getMesh(model) : nullptr;
        if (length && !replacement) throw std::runtime_error("Missing world mask mesh");
        prepared.push_back({index,world[index].mesh,replacement});
    }
    if (!reader.End()) throw std::runtime_error("Trailing world mask data");
    worldPatches=std::move(prepared); return true;
} catch (const std::exception& exception) { error=exception.what(); return false; }

void CinematicPlayer::ApplyWorldMask(std::vector<Instance>& world, bool enabled) {
    for (const auto& patch : worldPatches)
        if (patch.index<world.size()) world[patch.index].mesh=enabled ? patch.replacement : patch.original;
}

void CinematicPlayer::ApplyPlayerAnchor(Character& character) const {
    const auto& p=playerPose.position;
    const auto forward=playerPose.rotation*glm::vec3(0,0,-1);
    character.SetPosition(TLOU::Vector3(p.x,p.y,p.z));
    character.SetRotation(0,glm::degrees(std::atan2(-forward.x,-forward.z))-180.f,0);
    character.SetVelocity(TLOU::Vector3::Zero()); character.initModel();
}

// Load catalogues before playback; the timeline only submits audio commands.
bool CinematicPlayer::PrepareAudio(AudioManager& manager) {
    if (IsPlaying()) { error = "Stop the scene before preparing audio"; return false; }
    StopAudio(); audio = nullptr;
    for (const auto& bank : audioBanks) {
        if (!manager.loadBank(bank.c_str())) {
            error = "Cinematic audio bank: " + manager.getLastError();
            return false;
        }
    }
    audio = &manager; return true;
}
void CinematicPlayer::DispatchEvents() {
    for (const auto& cue : controlCues) {
        if (cue.time > clock.Time()) break;
        currentControl = cue.policy;
    }
    while (nextAudioCue < audioCues.size() && audioCues[nextAudioCue].time <= clock.Time()) {
        const auto& cue = audioCues[nextAudioCue++];
        if (audio) {
            auto voice = audio->playSound(cue.sound.c_str(),cue.options);
            if (voice) sceneVoices.push_back(voice);
            else sceClibPrintf("[Cinematic] Sound rejected: %s\n",cue.sound.c_str());
        }
    }
}
void CinematicPlayer::StopAudio() {
    if (audio) for (const auto voice : sceneVoices) audio->stopSound(voice);
    sceneVoices.clear();
}
void CinematicPlayer::Cancel() { clock.Cancel(); StopAudio(); }
