#pragma once
#include "System/AudioBank.h"
#include <memory>
#include <string>

struct SoundHandle {
    uint64_t value = 0;
    explicit operator bool() const { return value != 0; }
};
enum class SoundState { Stopped, Pending, Playing, Paused, Finished, Failed };
enum class SoundLoop { AssetDefault, Once, Loop };
struct SoundOptions {
    float volume = 1.f;
    float pan = 0.f; // -1 left, 0 centre, +1 right
    SoundLoop loop = SoundLoop::AssetDefault;
};
struct AudioConfig {
    size_t residentBudgetBytes = 8 * 1024 * 1024;
    unsigned maxVoices = 24;
};
struct AudioStats {
    size_t residentBytes = 0;
    unsigned activeVoices = 0;
    unsigned rejectedCommands = 0;
    unsigned playbackErrors = 0;
};

class AudioManager {
public:
    explicit AudioManager(std::unique_ptr<Audio::Backend> backend = nullptr);
    ~AudioManager();
    AudioManager(const AudioManager&) = delete;
    AudioManager& operator=(const AudioManager&) = delete;

    bool init(const AudioConfig& config = {});
    bool shutdown();
    // Loading is a loading-screen operation. Stream payloads are not read here.
    // Banks can overlap: an identical sound shared by two banks is loaded once.
    bool loadBank(const char* path);
    bool unloadBank(const char* path);

    SoundHandle playSound(SoundId sound, const SoundOptions& options = {});
    SoundHandle playSound(const char* name, const SoundOptions& options = {}) {
        return name ? playSound(AudioSoundId(name), options) : SoundHandle{};
    }
    bool stopSound(SoundHandle voice, float fadeSeconds = 0.f);
    bool stopAll(float fadeSeconds = 0.f);
    bool setVolume(SoundHandle voice, float volume);
    bool setPan(SoundHandle voice, float pan);
    bool setBusVolume(AudioBus bus, float volume);
    bool setMasterVolume(float volume);
    bool setPaused(bool paused);
    SoundState getState(SoundHandle voice) const;
    bool isPlaying(SoundHandle voice) const;
    AudioStats getStats() const;
    std::string getLastError() const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl;
};
