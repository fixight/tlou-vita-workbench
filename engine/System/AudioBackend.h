#pragma once
#include <cstddef>
#include <cstdint>
#include <memory>

namespace Audio {
constexpr uint32_t SampleRate = 48000;
constexpr uint32_t OutputFrames = 512;
constexpr unsigned MaxVoices = 32;
enum class Codec : uint32_t { Pcm16 = 1, Atrac9 = 2 };

struct Header {
    Codec codec = Codec::Pcm16;
    uint32_t channels = 0;
    uint64_t frames = 0;
    uint32_t blockBytes = 0;
    uint32_t blockFrames = 0;
    uint32_t primingFrames = 0;
    uint8_t atracConfig[4]{};
    uint64_t dataBytes = 0;
};

class Decoder {
public:
    virtual ~Decoder() = default;
    virtual bool Reset() = 0;
    // Return decoded frames, or zero on failure. Output is signed 16-bit PCM.
    virtual uint32_t Decode(const uint8_t* input, size_t bytes,
                            int16_t* output, size_t capacitySamples) = 0;
};

// One call per audio buffer, not per sample. A fake backend tests the same mixer
// on a PC; the Vita backend owns SceAudioOut and native ATRAC9 decoder contexts.
class Backend {
public:
    virtual ~Backend() = default;
    virtual bool Open() = 0;
    virtual bool Submit(const int16_t* stereo, uint32_t frames) = 0;
    virtual std::unique_ptr<Decoder> CreateAtrac9(const Header& header) = 0;
    virtual void Close() = 0;
};
std::unique_ptr<Backend> CreateVitaBackend();
}
