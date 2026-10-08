#pragma once
#include "AudioBackend.h"
#include <cstdio>
#include <string>
#include <vector>

using SoundId = uint64_t;
// Stable across the exporter and engine; collision checks also compare names.
inline SoundId AudioSoundId(const char* name) {
    uint64_t hash = 14695981039346656037ULL;
    while (*name) { hash ^= static_cast<unsigned char>(*name++); hash *= 1099511628211ULL; }
    return hash;
}
enum class AudioBus : uint8_t { Effects = 0, Dialogue = 1, Music = 2 };
enum class AudioStorage : uint8_t { Resident = 0, Stream = 1 };

struct AudioDefinition {
    std::string name, path;
    AudioStorage storage = AudioStorage::Resident;
    AudioBus bus = AudioBus::Effects;
    bool loop = false;
    float volume = 1.f;
};
bool ReadAudioBank(const char* path, std::vector<AudioDefinition>& entries, std::string& error);
bool ReadAudioHeader(FILE* file, Audio::Header& header, std::string& error);
