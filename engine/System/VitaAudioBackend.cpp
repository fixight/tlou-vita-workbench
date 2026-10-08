#include "AudioBackend.h"
#ifdef __vita__
#include <psp2/audioout.h>
#include <psp2/audiodec.h>
#include <psp2/kernel/sysmem.h>
#include <psp2/kernel/clib.h>
#include <cstring>

namespace Audio {
namespace {
class Atrac9Decoder final : public Decoder {
public:
    bool Open(const Header& header) {
        channels = header.channels;
        // The decoder accesses these buffers outside the CPU cache.
        SceKernelAllocMemBlockOpt memoryOptions{};
        memoryOptions.size = sizeof(memoryOptions);
        memoryOptions.attr = SCE_KERNEL_ALLOC_MEMBLOCK_ATTR_HAS_ALIGNMENT;
        memoryOptions.alignment = SCE_AUDIODEC_ALIGNMENT_SIZE;
        memoryBlock = sceKernelAllocMemBlock("AudioDecoder", SCE_KERNEL_MEMBLOCK_TYPE_USER_RW_UNCACHE,
                                            12288, &memoryOptions);
        if (memoryBlock < 0 || sceKernelGetMemBlockBase(memoryBlock, &input) < 0) return false;
        pcm = static_cast<uint8_t*>(input) + 1024;
        info.at9.size = sizeof(SceAudiodecInfoAt9);
        memcpy(info.at9.configData, header.atracConfig, 4);
        control.size = sizeof(control);
        control.wordLength = SCE_AUDIODEC_WORD_LENGTH_16BITS;
        control.pEs = static_cast<uint8_t*>(input);
        control.maxEsSize = 1024;
        control.pPcm = pcm;
        control.maxPcmSize = 8192;
        control.pInfo = &info;
        if (sceAudiodecCreateDecoder(&control, SCE_AUDIODEC_TYPE_AT9) < 0) return false;
        created = true;
        framesPerBlock = info.at9.framesInSuperFrame;
        if (info.at9.ch != channels || info.at9.samplingRate != SampleRate ||
            info.at9.superFrameSize != header.blockBytes || !framesPerBlock ||
            framesPerBlock > SCE_AUDIODEC_AT9_MAX_NFRAMES || header.blockFrames != framesPerBlock * 256) return false;
        blockBytes = header.blockBytes;
        return true;
    }
    ~Atrac9Decoder() override {
        if (created) sceAudiodecDeleteDecoder(&control);
        if (memoryBlock >= 0) sceKernelFreeMemBlock(memoryBlock);
    }
    bool Reset() override { return created && sceAudiodecClearContext(&control) >= 0; }
    uint32_t Decode(const uint8_t* data, size_t bytes, int16_t* output, size_t capacity) override {
        if (bytes != blockBytes) return 0;
        memcpy(input, data, bytes);
        control.inputEsSize = unsigned(bytes);
        control.outputPcmSize = 0;
        if (sceAudiodecDecodeNFrames(&control, framesPerBlock) < 0 ||
            !control.outputPcmSize || control.outputPcmSize > capacity * 2 ||
            control.outputPcmSize % (channels * 2)) return 0;
        memcpy(output, pcm, control.outputPcmSize);
        return control.outputPcmSize / (channels * 2);
    }
private:
    SceAudiodecCtrl control{};
    SceAudiodecInfo info{};
    SceUID memoryBlock = -1;
    void* input = nullptr;
    void* pcm = nullptr;
    uint32_t channels = 0, framesPerBlock = 0, blockBytes = 0;
    bool created = false;
};

class VitaBackend final : public Backend {
public:
    bool Open() override {
        port = sceAudioOutOpenPort(SCE_AUDIO_OUT_PORT_TYPE_MAIN, OutputFrames,
                                  SampleRate, SCE_AUDIO_OUT_MODE_STEREO);
        if (port < 0) return false;
        // PCM output still works when the compressed codec pool is unavailable.
        // SceAudiodec is imported directly; libaudiocodec is a separate system module.
        SceAudiodecInitParam init{};
        init.at9.size = sizeof(SceAudiodecInitChParam);
        init.at9.totalCh = SCE_AUDIODEC_AT9_MAX_CH_IN_LIBRARY;
        atracReady = sceAudiodecInitLibrary(SCE_AUDIODEC_TYPE_AT9, &init) >= 0;
        sceClibPrintf("[Audio] 48 kHz stereo, ATRAC9 pool %s\n", atracReady ? "ready" : "unavailable");
        return true;
    }
    bool Submit(const int16_t* stereo, uint32_t frames) override {
        return port >= 0 && frames == OutputFrames && sceAudioOutOutput(port, stereo) >= 0;
    }
    std::unique_ptr<Decoder> CreateAtrac9(const Header& header) override {
        if (!atracReady) return nullptr;
        auto decoder = std::make_unique<Atrac9Decoder>();
        if (!decoder->Open(header)) return nullptr;
        return decoder;
    }
    void Close() override {
        if (port >= 0) {
            sceAudioOutOutput(port, nullptr);
            sceAudioOutReleasePort(port); port = -1;
        }
        if (atracReady) sceAudiodecTermLibrary(SCE_AUDIODEC_TYPE_AT9);
        atracReady = false;
    }
private:
    int port = -1;
    bool atracReady = false;
};
}
std::unique_ptr<Backend> CreateVitaBackend() { return std::make_unique<VitaBackend>(); }
}
#else
namespace Audio {
std::unique_ptr<Backend> CreateVitaBackend() { return nullptr; }
}
#endif
