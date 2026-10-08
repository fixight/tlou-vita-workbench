#include "MoviePlayer.h"
#include "Render.h"

#include <cstdlib>
#include <malloc.h>
#include <cstdio>
#include <psp2/ctrl.h>
#include <psp2/audioout.h>
#include <psp2/sysmodule.h>
#include <psp2/kernel/sysmem.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/kernel/clib.h>
#include <psp2/kernel/processmgr.h>

namespace {
void* AllocateCpu(void*, uint32_t alignment, uint32_t size) {
    return memalign(alignment, size);
}
void FreeCpu(void*, void* address) { free(address); }

// SceAvPlayer requires physically contiguous, uncached, GPU-visible output.
// Allocation strategy follows the official vitaGL video_playback sample:
// https://github.com/Rinnegatamante/vitaGL/tree/master/samples/video_playback
void* AllocateFrame(void*, uint32_t, uint32_t size) {
    constexpr uint32_t megabyte = 1024 * 1024;
    size = (size + megabyte - 1) & ~(megabyte - 1);
    const SceUID block = sceKernelAllocMemBlock("movie-frame",
        SCE_KERNEL_MEMBLOCK_TYPE_USER_MAIN_PHYCONT_NC_RW, size, nullptr);
    if (block < 0) return nullptr;
    void* address = nullptr;
    if (sceKernelGetMemBlockBase(block, &address) < 0 ||
        sceGxmMapMemory(address, size, SCE_GXM_MEMORY_ATTRIB_RW) < 0) {
        sceKernelFreeMemBlock(block);
        return nullptr;
    }
    return address;
}
void FreeFrame(void*, void* address) {
    // Close() already waited for the GPU. Never call GL from a decoder callback.
    const SceUID block = sceKernelFindMemBlockByAddr(address, 0);
    sceGxmUnmapMemory(address);
    if (block >= 0) sceKernelFreeMemBlock(block);
}
const char* vertexShader = R"(
attribute vec2 aPosition;
attribute vec2 aUV;
uniform vec2 uScale;
varying vec2 vUV;
void main() {
    gl_Position = vec4(aPosition * uScale, 0.0, 1.0);
    vUV = aUV;
})";
const char* fragmentShader = R"(
precision mediump float;
uniform sampler2D uMovie;
varying vec2 vUV;
void main() { gl_FragColor = vec4(texture2D(uMovie, vUV).rgb, 1.0); }
)";
}

MoviePlayer::~MoviePlayer() { Close(); }

bool MoviePlayer::CreateRenderer() {
    program = Render::CompileShader(vertexShader, fragmentShader);
    if (!program) return false;
    positionAttribute = glGetAttribLocation(program, "aPosition");
    uvAttribute = glGetAttribLocation(program, "aUV");
    const float vertices[] = {
        -1,  1, 0, 0,   -1, -1, 0, 1,
         1,  1, 1, 0,    1, -1, 1, 1
    };
    glGenBuffers(1, &quadBuffer);
    glBindBuffer(GL_ARRAY_BUFFER, quadBuffer);
    glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices, GL_STATIC_DRAW);
    glBindBuffer(GL_ARRAY_BUFFER, 0);
    for (auto& frame : frames) {
        glGenTextures(1, &frame.name);
        glBindTexture(GL_TEXTURE_2D, frame.name);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 8, 8, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        frame.native = vglGetGxmTexture(GL_TEXTURE_2D);
        frame.placeholder = vglGetTexDataPointer(GL_TEXTURE_2D);
    }
    return true;
}

void MoviePlayer::ReleaseRenderer() {
    for (auto& frame : frames) {
        if (!frame.name) continue;
        // The GL texture must not free a frame owned by AvPlayer.
        sceGxmTextureInitLinear(frame.native, frame.placeholder,
            SCE_GXM_TEXTURE_FORMAT_U8U8U8U8_ABGR, 8, 8, 0);
        glDeleteTextures(1, &frame.name);
        frame = {};
    }
    if (quadBuffer) glDeleteBuffers(1, &quadBuffer);
    if (program) glDeleteProgram(program);
    quadBuffer = program = 0;
}

bool MoviePlayer::Open(const char* path) {
    Close();
    FILE* file = fopen(path, "rb");
    if (!file) return false; // An installation without movies can still play the level.
    fclose(file);
    if (sceSysmoduleLoadModule(SCE_SYSMODULE_AVPLAYER) < 0) return false;
    moduleLoaded = true;
    if (!CreateRenderer()) { Close(); return false; }

    SceAvPlayerInitData init{};
    init.memoryReplacement.allocate = AllocateCpu;
    init.memoryReplacement.deallocate = FreeCpu;
    init.memoryReplacement.allocateTexture = AllocateFrame;
    init.memoryReplacement.deallocateTexture = FreeFrame;
    init.basePriority = 0xA0;
    init.numOutputVideoFrameBuffers = FrameBufferCount;
    init.autoStart = SCE_FALSE;
    init.defaultLanguage = "eng";
    player = sceAvPlayerInit(&init);
    if (player == 0) {
        sceClibPrintf("[Movie] Decoder initialization failed\n");
        Close();
        return false;
    }
    const int sourceResult = sceAvPlayerAddSource(player, path);
    if (sourceResult < 0) {
        sceClibPrintf("[Movie] Cannot open %s (error 0x%08X)\n", path, unsigned(sourceResult));
        Close();
        return false;
    }
    playing = true;
    openedAt = sceKernelGetProcessTimeWide();
    SceCtrlData pad{};
    sceCtrlPeekBufferPositive(0, &pad, 1);
    previousButtons = pad.buttons;
    sceClibPrintf("[Movie] Playing %s; START skips\n", path);
    return true;
}

void MoviePlayer::AudioLoop() {
    // This thread only feeds PCM to the audio device. Decode is handled by AvPlayer.
    int port = -1;
    while (audioRunning.load()) {
        SceAvPlayerFrameInfo frame{};
        if (!sceAvPlayerIsActive(player) || !sceAvPlayerGetAudioData(player, &frame)) {
            sceKernelDelayThread(1000);
            continue;
        }
        const auto& audio = frame.details.audio;
        if (audio.sampleRate != 48000 || (audio.channelCount != 1 && audio.channelCount != 2)) {
            sceClibPrintf("[Movie] Audio must be prepared as 48 kHz mono/stereo AAC\n");
            break;
        }
        const auto mode = audio.channelCount == 1 ? SCE_AUDIO_OUT_MODE_MONO : SCE_AUDIO_OUT_MODE_STEREO;
        const unsigned samples = audio.size / (audio.channelCount * sizeof(int16_t));
        if (!samples) continue;
        if (port < 0) port = sceAudioOutOpenPort(SCE_AUDIO_OUT_PORT_TYPE_MAIN, samples, 48000, mode);
        if (port < 0 || sceAudioOutSetConfig(port, samples, 48000, mode) < 0 ||
            sceAudioOutOutput(port, frame.pData) < 0) {
            sceClibPrintf("[Movie] Audio output failed\n");
            break;
        }
    }
    if (port >= 0) {
        sceAudioOutOutput(port, nullptr);
        sceAudioOutReleasePort(port);
    }
}

bool MoviePlayer::Update() {
    if (!playing) return false;
    if (!started) {
        if (sceAvPlayerStart(player) < 0) { playing = false; return false; }
        openedAt = sceKernelGetProcessTimeWide();
        audioRunning.store(true);
        try {
            audioThread = std::thread(&MoviePlayer::AudioLoop, this);
        } catch (...) {
            audioRunning.store(false);
            playing = false;
            return false;
        }
        started = true;
    }
    SceCtrlData pad{};
    sceCtrlPeekBufferPositive(0, &pad, 1);
    const bool skip = (pad.buttons & SCE_CTRL_START) && !(previousButtons & SCE_CTRL_START);
    previousButtons = pad.buttons;
    if (skip) {
        Close();
        sceClibPrintf("[Movie] Skipped\n");
        return false;
    }
    if (sceAvPlayerIsActive(player)) {
        SceAvPlayerFrameInfo frame{};
        if (sceAvPlayerGetVideoData(player, &frame) && frame.pData &&
            frame.details.video.width && frame.details.video.height) {
            currentFrame = (currentFrame + 1) % FrameBufferCount;
            const auto& video = frame.details.video;
            const int result = sceGxmTextureInitLinear(frames[currentFrame].native, frame.pData,
                SCE_GXM_TEXTURE_FORMAT_YVU420P2_CSC1, video.width, video.height, 0);
            if (result < 0) { playing = false; return false; }
            sceGxmTextureSetMinFilter(frames[currentFrame].native, SCE_GXM_TEXTURE_FILTER_LINEAR);
            sceGxmTextureSetMagFilter(frames[currentFrame].native, SCE_GXM_TEXTURE_FILTER_LINEAR);
            // Prepared MP4 files have square pixels. Native AvPlayer and HLE do not
            // agree on the meaning of aspectRatio; dimensions give an unambiguous DAR.
            aspect = float(video.width) / video.height;
            if (!haveFrame) {
                char message[160];
                snprintf(message, sizeof(message), "[Movie] First frame %ux%u, decoder aspect %.3f\n",
                    unsigned(video.width), unsigned(video.height), double(video.aspectRatio));
                sceClibPrintf("%s", message);
            }
            haveFrame = true;
        }
    } else if (haveFrame) {
        playing = false;
        sceClibPrintf("[Movie] Finished\n");
    }
    if (!haveFrame && sceKernelGetProcessTimeWide() - openedAt > 15000000) {
        playing = false;
        sceClibPrintf("[Movie] Decoder startup timed out\n");
    }
    return playing;
}

void MoviePlayer::Draw() {
    glViewport(0, 0, 960, 544);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_BLEND);
    glDisable(GL_CULL_FACE);
    glClearColor(0, 0, 0, 1);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    if (!haveFrame) return;
    glUseProgram(program);
    const float screenAspect = 960.0f / 544.0f;
    glUniform2f(glGetUniformLocation(program, "uScale"),
        aspect < screenAspect ? aspect / screenAspect : 1.0f,
        aspect > screenAspect ? screenAspect / aspect : 1.0f);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, frames[currentFrame].name);
    glUniform1i(glGetUniformLocation(program, "uMovie"), 0);
    glBindBuffer(GL_ARRAY_BUFFER, quadBuffer);
    glEnableVertexAttribArray(positionAttribute);
    glEnableVertexAttribArray(uvAttribute);
    glVertexAttribPointer(positionAttribute, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(float), nullptr);
    glVertexAttribPointer(uvAttribute, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(float), (void*)(2 * sizeof(float)));
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    glDisableVertexAttribArray(positionAttribute);
    glDisableVertexAttribArray(uvAttribute);
    glBindBuffer(GL_ARRAY_BUFFER, 0);
    glUseProgram(0);
}

void MoviePlayer::Close() {
    playing = false;
    audioRunning.store(false);
    if (audioThread.joinable()) audioThread.join();
    if (program) glFinish();
    ReleaseRenderer();
    if (player != 0) {
        sceAvPlayerStop(player);
        sceAvPlayerClose(player);
        player = 0;
    }
    if (moduleLoaded) sceSysmoduleUnloadModule(SCE_SYSMODULE_AVPLAYER);
    moduleLoaded = false;
    haveFrame = false;
    started = false;
    currentFrame = 0;
}
