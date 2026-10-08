#include "AudioBank.h"
#include <climits>
#include <cmath>
#include <cstring>
#include <set>

namespace {
struct FileCloser { void operator()(FILE* file) const { if (file) fclose(file); } };
bool Bytes(FILE* file, void* output, size_t size) { return fread(output, 1, size, file) == size; }
bool U32(FILE* file, uint32_t& output) {
    uint8_t b[4]; if (!Bytes(file, b, 4)) return false;
    output = uint32_t(b[0]) | (uint32_t(b[1]) << 8) | (uint32_t(b[2]) << 16) | (uint32_t(b[3]) << 24);
    return true;
}
bool U64(FILE* file, uint64_t& output) {
    uint32_t low, high; if (!U32(file, low) || !U32(file, high)) return false;
    output = low | (uint64_t(high) << 32); return true;
}
bool Text(FILE* file, std::string& text) {
    uint8_t b[2]; if (!Bytes(file, b, 2)) return false;
    unsigned count = unsigned(b[0]) | unsigned(b[1]) << 8;
    if (!count || count > 1024) return false;
    text.resize(count);
    return Bytes(file, &text[0], count) && text.find('\0') == std::string::npos;
}
}

bool ReadAudioHeader(FILE* file, Audio::Header& header, std::string& error) {
    Audio::Header result;
    char magic[4]; uint32_t version, codec, rate; uint8_t reserved[12];
    if (!Bytes(file, magic, 4) || memcmp(magic, "VAS1", 4) ||
        !U32(file, version) || version != 1 || !U32(file, codec) ||
        !U32(file, rate) || rate != Audio::SampleRate || !U32(file, result.channels) ||
        (result.channels != 1 && result.channels != 2) || !U64(file, result.frames) || !result.frames ||
        !U32(file, result.blockBytes) || !U32(file, result.blockFrames) ||
        !U32(file, result.primingFrames) || !Bytes(file, result.atracConfig, 4) ||
        !U64(file, result.dataBytes) || !Bytes(file, reserved, 12) ||
        !result.dataBytes || result.dataBytes > uint64_t(LONG_MAX) - 64) {
        error = "Invalid VAS1 audio header"; return false;
    }
    for (auto value : reserved) if (value) { error = "Unsupported VAS1 reserved flags"; return false; }
    result.codec = static_cast<Audio::Codec>(codec);
    if (result.codec == Audio::Codec::Pcm16) {
        if (result.frames > result.dataBytes / (result.channels * 2) ||
            result.dataBytes != result.frames * result.channels * 2 ||
            result.blockBytes || result.blockFrames || result.primingFrames) {
            error = "Invalid PCM audio size"; return false;
        }
    } else if (result.codec == Audio::Codec::Atrac9) {
        if (!result.blockBytes || result.blockBytes > 1024 || !result.blockFrames ||
            result.blockFrames > 2048 || result.dataBytes % result.blockBytes ||
            result.frames + result.primingFrames < result.frames ||
            result.frames + result.primingFrames > result.dataBytes / result.blockBytes * result.blockFrames) {
            error = "Invalid ATRAC9 audio blocks"; return false;
        }
    } else { error = "Unsupported audio codec"; return false; }
    if (fseek(file, 0, SEEK_END) || ftell(file) != long(64 + result.dataBytes) || fseek(file, 64, SEEK_SET)) {
        error = "Audio file length does not match header"; return false;
    }
    header = result; return true;
}

bool ReadAudioBank(const char* path, std::vector<AudioDefinition>& entries, std::string& error) {
    std::unique_ptr<FILE, FileCloser> file(fopen(path, "rb"));
    if (!file) { error = "Audio bank not found"; return false; }
    char magic[4]; uint32_t version, count;
    if (!Bytes(file.get(), magic, 4) || memcmp(magic, "VAB1", 4) || !U32(file.get(), version) ||
        version != 1 || !U32(file.get(), count) || count > 4096) {
        error = "Invalid VAB1 bank header"; return false;
    }
    std::vector<AudioDefinition> result; std::set<SoundId> ids;
    for (uint32_t index = 0; index < count; ++index) {
        AudioDefinition item; uint8_t flags[4]; uint32_t volumeBits;
        if (!Text(file.get(), item.name) || !Text(file.get(), item.path) ||
            !Bytes(file.get(), flags, 4) || flags[0] > 1 || flags[1] > 2 || flags[2] > 1 || flags[3] ||
            !U32(file.get(), volumeBits) || !ids.insert(AudioSoundId(item.name.c_str())).second) {
            error = "Invalid or duplicate audio bank entry"; return false;
        }
        memcpy(&item.volume, &volumeBits, 4);
        if (!std::isfinite(item.volume) || item.volume < 0.f || item.volume > 4.f) {
            error = "Invalid sound volume"; return false;
        }
        item.storage = static_cast<AudioStorage>(flags[0]); item.bus = static_cast<AudioBus>(flags[1]);
        item.loop = flags[2] != 0; result.push_back(std::move(item));
    }
    if (fgetc(file.get()) != EOF) { error = "Trailing audio bank bytes"; return false; }
    entries = std::move(result); return true;
}
