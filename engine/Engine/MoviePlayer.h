#pragma once

#include <atomic>
#include <thread>
#include <cstdint>
#include <vitaGL.h>
#include <psp2/avplayer.h>

// MP4 / H.264 + optional AAC, prepared offline. All public calls are main-thread only.
// AvPlayer owns decoded frames; the GPU samples YUV without a CPU RGB conversion.
class MoviePlayer {
public:
    ~MoviePlayer();
    bool Open(const char* path);
    bool Update(); // false on EOF, skip or error
    void Draw();   // clears the screen, preserves aspect ratio
    void Close();  // waits for audio and GPU before releasing decoder buffers
    bool IsPlaying() const { return playing; }

private:
    static constexpr unsigned FrameBufferCount = 5;
    struct FrameTexture {
        GLuint name = 0;
        SceGxmTexture* native = nullptr;
        void* placeholder = nullptr;
    };
    void AudioLoop();
    bool CreateRenderer();
    void ReleaseRenderer();

    SceAvPlayerHandle player = 0; // Opaque handle: high-bit addresses are valid.
    bool moduleLoaded = false;
    bool playing = false;
    bool started = false;
    bool haveFrame = false;
    uint64_t openedAt = 0;
    uint32_t previousButtons = 0;
    float aspect = 960.0f / 544.0f;
    unsigned currentFrame = 0;
    FrameTexture frames[FrameBufferCount];
    GLuint program = 0;
    GLuint quadBuffer = 0;
    GLint positionAttribute = -1;
    GLint uvAttribute = -1;
    std::atomic<bool> audioRunning{false};
    std::thread audioThread;
};
