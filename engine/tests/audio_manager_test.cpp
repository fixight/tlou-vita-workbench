#include "../Managers/AudioManager.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <mutex>
#include <thread>

class TestDecoder final : public Audio::Decoder {
public:
    bool Reset() override { return true; }
    uint32_t Decode(const uint8_t* data, size_t bytes, int16_t* output, size_t capacity) override {
        if (bytes != 8 || capacity < 4) return 0;
        memcpy(output, data, bytes); return 4;
    }
};
class TestBackend final : public Audio::Backend {
public:
    bool Open() override { return openWorks; }
    bool Submit(const int16_t* data, uint32_t frames) override {
        std::unique_lock<std::mutex> lock(mutex);
        std::copy(data, data + frames * 2, block.begin());
        ++submitted; ready.notify_all();
        ready.wait_for(lock, std::chrono::milliseconds(200), [&] { return permits || releasing; });
        if (permits) --permits;
        return true;
    }
    std::unique_ptr<Audio::Decoder> CreateAtrac9(const Audio::Header& header) override {
        return header.atracConfig[0] == 0xfe ? std::make_unique<TestDecoder>() : nullptr;
    }
    void Close() override {}
    std::array<int16_t, 1024> Step() {
        std::unique_lock<std::mutex> lock(mutex);
        const auto before = submitted;
        ++permits; ready.notify_all();
        assert(ready.wait_for(lock, std::chrono::seconds(2), [&] { return submitted > before; }));
        return block;
    }
    void WaitFirst() {
        std::unique_lock<std::mutex> lock(mutex);
        assert(ready.wait_for(lock, std::chrono::seconds(2), [&] { return submitted > 0; }));
    }
    void Release() { std::lock_guard<std::mutex> lock(mutex); releasing = true; ready.notify_all(); }
    bool openWorks = true;
private:
    std::mutex mutex;
    std::condition_variable ready;
    unsigned submitted = 0, permits = 0;
    bool releasing = false;
    std::array<int16_t, 1024> block{};
};
void U32(std::ofstream& out, uint32_t value) {
    for (unsigned i=0;i<4;++i) out.put(char(value >> (i*8)));
}
void U64(std::ofstream& out, uint64_t value) { U32(out, unsigned(value)); U32(out, unsigned(value>>32)); }
void Text(std::ofstream& out, const std::string& text) {
    out.put(char(text.size())); out.put(char(text.size()>>8)); out.write(text.data(), text.size());
}
void Sound(const std::filesystem::path& path, const std::vector<int16_t>& pcm, bool encoded = false) {
    std::ofstream out(path, std::ios::binary);
    out.write("VAS1",4); U32(out,1); U32(out,encoded ? 2 : 1); U32(out,48000); U32(out,1);
    U64(out,encoded ? pcm.size()-2 : pcm.size());
    U32(out,encoded ? 8 : 0); U32(out,encoded ? 4 : 0); U32(out,encoded ? 2 : 0);
    const char config[] = {char(0xfe),0,0,0}; out.write(config,4);
    U64(out,pcm.size()*2); const char padding[12]{};out.write(padding,12);
    out.write(reinterpret_cast<const char*>(pcm.data()), pcm.size()*2);
}
void Bank(const std::filesystem::path& path, const char* name, const std::filesystem::path& sound, bool streamed = false) {
    std::ofstream out(path, std::ios::binary);out.write("VAB1",4);U32(out,1);U32(out,1);
    Text(out,name);Text(out,sound.string());out.put(streamed ? 1 : 0);out.put(0);out.put(0);out.put(0);
    float volume=1;uint32_t bits;memcpy(&bits,&volume,4);U32(out,bits);
}
int main() {
    auto dir = std::filesystem::temp_directory_path()/"tlou-audio-manager-test";
    std::filesystem::create_directories(dir);
    Sound(dir/"short.vas",std::vector<int16_t>(64,10000));
    Bank(dir/"a.vabk","door",dir/"short.vas"); Bank(dir/"b.vabk","door",dir/"short.vas");
    Bank(dir/"stream.vabk","stream",dir/"short.vas",true);
    Sound(dir/"encoded.vas",{100,200,300,400,500,600,700,800},true);
    Bank(dir/"encoded.vabk","encoded",dir/"encoded.vas",true);
    auto sink = std::make_unique<TestBackend>(); auto* output=sink.get();
    AudioManager audio(std::move(sink));
    assert(audio.init({128,2})); output->WaitFirst();
    assert(audio.loadBank((dir/"a.vabk").c_str()));
    assert(audio.loadBank((dir/"b.vabk").c_str()));
    assert(audio.loadBank((dir/"stream.vabk").c_str()));
    assert(audio.loadBank((dir/"encoded.vabk").c_str()));
    assert(audio.getStats().residentBytes==128); // shared bank does not duplicate RAM
    auto voice=audio.playSound("door",{.5f,-1,SoundLoop::Once});
    assert(voice && audio.isPlaying(voice));
    auto block=output->Step(); assert(block[0]==5000 && block[1]==0 && block[128]==0);
    assert(audio.getState(voice)==SoundState::Finished);
    auto looping=audio.playSound("door",{1,0,SoundLoop::Loop});
    block=output->Step(); assert(block[0]==10000 && block[1022]==10000);
    assert(audio.unloadBank((dir/"a.vabk").c_str()));
    output->Step(); assert(audio.isPlaying(looping)); // bank B still owns it
    assert(audio.setPaused(true)); block=output->Step();
    assert(block[0]==0 && audio.getState(looping)==SoundState::Paused);
    assert(audio.setPaused(false)); output->Step();
    assert(audio.stopSound(looping,.001f));block=output->Step();
    assert(block[0]==10000 && block[100]==0 && !audio.isPlaying(looping));
    auto streamed=audio.playSound("stream"); block=output->Step();
    assert(block[0]==10000 && audio.getState(streamed)==SoundState::Finished);
    assert(!audio.setVolume(looping,1)); // old handle cannot control a reused slot
    auto encoded=audio.playSound("encoded",{1,0,SoundLoop::Loop});block=output->Step();
    assert(encoded && audio.isPlaying(encoded));
    assert(block[0]==300 && block[2]==400 && block[10]==800 && block[12]==300);
    assert(audio.stopAll());output->Step();
    auto first=audio.playSound("door",{1,0,SoundLoop::Loop});
    auto second=audio.playSound("door",{1,0,SoundLoop::Loop});
    assert(first && second && !audio.playSound("door"));
    assert(audio.setMasterVolume(4));block=output->Step();assert(block[0]==32767);
    assert(audio.unloadBank((dir/"b.vabk").c_str()));output->Step();
    assert(!audio.isPlaying(first) && !audio.isPlaying(second));
    assert(!audio.playSound("door"));assert(audio.getStats().residentBytes==0);
    assert(!audio.playSound("unknown"));assert(!audio.setPan({},2));
    // A failed bank load publishes nothing and keeps the old catalog usable.
    Sound(dir/"large.vas",std::vector<int16_t>(100,200));
    Bank(dir/"large.vabk","large",dir/"large.vas");
    assert(!audio.loadBank((dir/"large.vabk").c_str()));assert(!audio.getLastError().empty());
    assert(!audio.playSound("large"));assert(audio.playSound("stream"));output->Step();
    auto queueVoice=audio.playSound("stream",{1,0,SoundLoop::Loop});output->Step();
    for (unsigned i=0;i<128;++i) assert(audio.setMasterVolume(1));
    assert(!audio.setMasterVolume(1));
    assert(!audio.unloadBank((dir/"stream.vabk").c_str())); // queue-full rollback
    output->Step();assert(audio.isPlaying(queueVoice));
    assert(audio.unloadBank((dir/"stream.vabk").c_str()));output->Step();
    assert(!audio.isPlaying(queueVoice));
    Sound(dir/"invalid-codec.vas",{100,200,300,400,500,600,700,800},true);
    { std::fstream corrupted(dir/"invalid-codec.vas",std::ios::binary|std::ios::in|std::ios::out);
      corrupted.seekp(40);corrupted.put(0); }
    Bank(dir/"invalid-codec.vabk","invalid-codec",dir/"invalid-codec.vas",true);
    assert(audio.loadBank((dir/"invalid-codec.vabk").c_str()));
    auto failed=audio.playSound("invalid-codec");output->Step();
    assert(audio.getState(failed)==SoundState::Failed);
    assert(audio.getStats().playbackErrors==1);
    output->Release();assert(audio.shutdown());assert(audio.shutdown());
    assert(audio.getStats().residentBytes==0);
    // Failure opening the device returns to the caller, without a waiting thread.
    auto failing=std::make_unique<TestBackend>();failing->openWorks=false;
    AudioManager unavailable(std::move(failing));assert(!unavailable.init());assert(unavailable.shutdown());
    std::filesystem::remove_all(dir);
    std::cout<<"Audio mixer, streams, loops, decoder priming, bank lifetime and handles OK\n";
}
