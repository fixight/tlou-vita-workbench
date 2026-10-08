#include "AudioManager.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <condition_variable>
#include <cstring>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <vector>

namespace {
constexpr unsigned CommandCapacity = 128;
struct FileCloser { void operator()(FILE* file) const { if (file) fclose(file); } };
struct ResidentBudget { std::atomic<size_t> bytes{0}; size_t limit = 0; };
struct SoundAsset {
    AudioDefinition definition;
    Audio::Header header;
    std::vector<uint8_t> resident;
    std::shared_ptr<ResidentBudget> budget;
    size_t reservedBytes = 0;
    ~SoundAsset() { if (reservedBytes) budget->bytes.fetch_sub(reservedBytes); }
};

// All file reads and decoder calls happen on the audio thread. Resident sounds
// use the same reader, but fetch blocks from immutable RAM instead of a file.
class SoundReader {
public:
    bool Open(std::shared_ptr<SoundAsset> sound, Audio::Backend& backend) {
        asset = std::move(sound);
        if (asset->definition.storage == AudioStorage::Stream) {
            file = fopen(asset->definition.path.c_str(), "rb");
            if (!file || setvbuf(file, fileBuffer.data(), _IOFBF, fileBuffer.size()) || fseek(file, 64, SEEK_SET)) return false;
        }
        if (asset->header.codec == Audio::Codec::Atrac9) {
            decoder = backend.CreateAtrac9(asset->header);
            if (!decoder) return false;
        }
        return Rewind();
    }
    ~SoundReader() { if (file) fclose(file); }
    bool Rewind() {
        bytesRead = framesRead = 0;
        decodedFrames = decodedOffset = 0;
        skipFrames = asset->header.primingFrames;
        failed = false;
        return (!decoder || decoder->Reset()) && (!file || fseek(file, 64, SEEK_SET) == 0);
    }
    bool Failed() const { return failed; }
    uint32_t Read(int16_t* output, uint32_t frames) {
        const auto& header = asset->header;
        frames = uint32_t(std::min<uint64_t>(frames, header.frames - framesRead));
        if (header.codec == Audio::Codec::Pcm16) {
            const size_t bytes = size_t(frames) * header.channels * 2;
            if (!Bytes(reinterpret_cast<uint8_t*>(output), bytes)) return 0;
            framesRead += frames; return frames;
        }
        uint32_t written = 0;
        while (written < frames) {
            if (decodedOffset == decodedFrames) {
                if (!Bytes(encoded.data(), header.blockBytes)) break;
                decodedFrames = decoder->Decode(encoded.data(), header.blockBytes, decoded.data(), decoded.size());
                decodedOffset = 0;
                if (decodedFrames != header.blockFrames) { failed = true; break; }
            }
            const uint32_t skip = std::min(skipFrames, decodedFrames - decodedOffset);
            decodedOffset += skip; skipFrames -= skip;
            const uint32_t count = std::min(frames - written, decodedFrames - decodedOffset);
            memcpy(output + written * header.channels, decoded.data() + decodedOffset * header.channels,
                   size_t(count) * header.channels * 2);
            decodedOffset += count; written += count;
        }
        framesRead += written; return written;
    }
private:
    bool Bytes(uint8_t* output, size_t count) {
        if (count > asset->header.dataBytes - bytesRead) { failed = true; return false; }
        if (file) {
            if (fread(output, 1, count, file) != count) { failed = true; return false; }
        } else memcpy(output, asset->resident.data() + size_t(bytesRead), count);
        bytesRead += count; return true;
    }
    std::shared_ptr<SoundAsset> asset;
    FILE* file = nullptr;
    std::array<char, 16384> fileBuffer{};
    std::unique_ptr<Audio::Decoder> decoder;
    std::array<uint8_t, 1024> encoded{};
    std::array<int16_t, 4096> decoded{};
    uint64_t bytesRead = 0, framesRead = 0;
    uint32_t decodedFrames = 0, decodedOffset = 0, skipFrames = 0;
    bool failed = false;
};

bool Gain(float value) { return std::isfinite(value) && value >= 0.f && value <= 4.f; }
bool Fade(float seconds) { return std::isfinite(seconds) && seconds >= 0.f && seconds <= 60.f; }
bool Pan(float value) { return std::isfinite(value) && value >= -1.f && value <= 1.f; }
bool SameDefinition(const AudioDefinition& a, const AudioDefinition& b) {
    return a.name == b.name && a.path == b.path && a.storage == b.storage &&
           a.bus == b.bus && a.loop == b.loop && a.volume == b.volume;
}
}

struct AudioManager::Impl {
    enum class Operation { Play, Stop, StopAll, Volume, Pan, BusVolume, MasterVolume, Pause, Unload };
    struct Command {
        Operation operation = Operation::StopAll;
        SoundHandle handle;
        std::shared_ptr<SoundAsset> asset;
        SoundOptions options;
        float value = 0;
        unsigned bus = 0;
        std::shared_ptr<std::vector<SoundId>> retiredSounds;
    };
    struct Voice {
        SoundHandle handle;
        std::shared_ptr<SoundAsset> asset;
        std::unique_ptr<SoundReader> reader;
        float volume = 1, pan = 0;
        bool loop = false;
        uint32_t fadeRemaining = 0, fadeLength = 0;
    };
    struct Slot {
        std::atomic<uint64_t> handle{0};
        std::atomic<SoundState> state{SoundState::Stopped};
    };
    struct CatalogEntry { std::shared_ptr<SoundAsset> asset; unsigned banks = 0; };

    explicit Impl(std::unique_ptr<Audio::Backend> output) : backend(std::move(output)) {}
    std::unique_ptr<Audio::Backend> backend;
    AudioConfig config;
    std::shared_ptr<ResidentBudget> budget = std::make_shared<ResidentBudget>();
    std::unordered_map<SoundId, CatalogEntry> catalog;
    std::unordered_map<std::string, std::vector<SoundId>> banks;
    std::array<Slot, Audio::MaxVoices> slots;
    std::array<Voice, Audio::MaxVoices> voices;
    std::array<Command, CommandCapacity> commands;
    unsigned readCommand = 0, commandCount = 0;
    uint64_t generation = 0;
    mutable std::mutex commandMutex;
    std::mutex lifecycleMutex, bankMutex, startupMutex;
    std::condition_variable startupReady;
    bool startupDone = false, startupSuccess = false;
    std::atomic<bool> running{false};
    std::thread worker;
    std::atomic<unsigned> rejected{0}, errors{0}, active{0};
    std::string lastError;
    float busVolume[3] = {1, 1, 1};
    float masterVolume = 1;
    bool paused = false;

    bool Enqueue(Command command) {
        // Caller holds commandMutex; never hold it while reading or decoding.
        if (!running.load() || commandCount == CommandCapacity) { ++rejected; return false; }
        commands[(readCommand + commandCount) % CommandCapacity] = std::move(command);
        ++commandCount; return true;
    }
    void Finish(unsigned index, SoundState state) {
        voices[index] = Voice{}; // decoder goes away before the backend is closed
        slots[index].state.store(state);
    }
    void StartFade(unsigned index, float seconds) {
        if (seconds == 0) { Finish(index, SoundState::Stopped); return; }
        auto& voice = voices[index];
        voice.fadeLength = voice.fadeRemaining = std::max(1u, uint32_t(seconds * Audio::SampleRate));
    }
    void Process(Command& command) {
        unsigned index = unsigned(command.handle.value & 255);
        switch (command.operation) {
        case Operation::Play: {
            // A queued unload can invalidate this sound before it starts.
            auto& voice = voices[index];
            voice.handle = command.handle; voice.asset = std::move(command.asset);
            voice.reader = std::make_unique<SoundReader>();
            voice.volume = command.options.volume; voice.pan = command.options.pan;
            voice.loop = command.options.loop == SoundLoop::AssetDefault ? voice.asset->definition.loop :
                         command.options.loop == SoundLoop::Loop;
            if (!voice.reader->Open(voice.asset, *backend)) { ++errors; Finish(index, SoundState::Failed); }
            else slots[index].state.store(paused ? SoundState::Paused : SoundState::Playing);
            break;
        }
        case Operation::StopAll:
            for (unsigned i = 0; i < config.maxVoices; ++i) if (voices[i].reader) StartFade(i, command.value);
            break;
        case Operation::Unload:
            for (unsigned i = 0; i < config.maxVoices; ++i)
                if (voices[i].asset && std::binary_search(command.retiredSounds->begin(), command.retiredSounds->end(),
                    AudioSoundId(voices[i].asset->definition.name.c_str()))) Finish(i, SoundState::Stopped);
            break;
        case Operation::BusVolume: busVolume[command.bus] = command.value; break;
        case Operation::MasterVolume: masterVolume = command.value; break;
        case Operation::Pause:
            paused = command.value != 0;
            for (unsigned i = 0; i < config.maxVoices; ++i) if (voices[i].reader)
                slots[i].state.store(paused ? SoundState::Paused : SoundState::Playing);
            break;
        default:
            if (index >= config.maxVoices || voices[index].handle.value != command.handle.value) return;
            if (command.operation == Operation::Stop) StartFade(index, command.value);
            else if (command.operation == Operation::Volume) voices[index].volume = command.value;
            else if (command.operation == Operation::Pan) voices[index].pan = command.value;
            break;
        }
    }
    void DrainCommands() {
        std::array<Command, CommandCapacity> pending;
        unsigned count;
        {
            std::lock_guard<std::mutex> lock(commandMutex);
            count = commandCount;
            for (unsigned i = 0; i < count; ++i) pending[i] = std::move(commands[(readCommand + i) % CommandCapacity]);
            readCommand = (readCommand + count) % CommandCapacity; commandCount = 0;
        }
        for (unsigned i = 0; i < count; ++i) {
            try { Process(pending[i]); }
            catch (...) {
                ++errors;
                if (pending[i].operation == Operation::Play)
                    Finish(unsigned(pending[i].handle.value & 255), SoundState::Failed);
            }
        }
    }
    void Mix(std::array<int16_t, Audio::OutputFrames * 2>& output) {
        std::array<float, Audio::OutputFrames * 2> sum{};
        std::array<int16_t, Audio::OutputFrames * 2> samples;
        unsigned voiceCount = 0;
        for (unsigned index = 0; index < config.maxVoices; ++index) {
            auto& voice = voices[index];
            if (!voice.reader) continue;
            ++voiceCount;
            if (paused) continue;
            const unsigned channels = voice.asset->header.channels;
            const float gain = voice.volume * voice.asset->definition.volume *
                               busVolume[unsigned(voice.asset->definition.bus)] * masterVolume;
            const float left = gain * (voice.pan > 0 ? 1.f - voice.pan : 1.f);
            const float right = gain * (voice.pan < 0 ? 1.f + voice.pan : 1.f);
            unsigned cursor = 0;
            bool rewoundWithoutSamples = false;
            while (cursor < Audio::OutputFrames && voice.reader) {
                const unsigned count = voice.reader->Read(samples.data(), Audio::OutputFrames - cursor);
                if (!count) {
                    if (voice.reader->Failed() || rewoundWithoutSamples) {
                        ++errors; Finish(index, SoundState::Failed); break;
                    }
                    if (!voice.loop) { Finish(index, SoundState::Finished); break; }
                    if (!voice.reader->Rewind()) { ++errors; Finish(index, SoundState::Failed); break; }
                    rewoundWithoutSamples = true; continue;
                }
                rewoundWithoutSamples = false;
                for (unsigned frame = 0; frame < count; ++frame) {
                    const float fade = voice.fadeLength ? float(voice.fadeRemaining) / voice.fadeLength : 1.f;
                    sum[(cursor + frame) * 2] += samples[frame * channels] * left * fade;
                    sum[(cursor + frame) * 2 + 1] += samples[frame * channels + channels - 1] * right * fade;
                    if (voice.fadeLength && --voice.fadeRemaining == 0) { Finish(index, SoundState::Stopped); break; }
                }
                cursor += count;
            }
        }
        active.store(voiceCount);
        for (unsigned i = 0; i < output.size(); ++i) output[i] = int16_t(std::clamp(sum[i], -32768.f, 32767.f));
    }
    void Run() {
        bool opened = false;
        try { opened = backend && backend->Open(); }
        catch (...) { ++errors; }
        {
            std::lock_guard<std::mutex> lock(startupMutex);
            startupDone = true; startupSuccess = opened;
        }
        startupReady.notify_one();
        if (opened) {
            alignas(64) std::array<int16_t, Audio::OutputFrames * 2> output{};
            while (running.load()) {
                DrainCommands(); Mix(output);
                try {
                    if (!backend->Submit(output.data(), Audio::OutputFrames)) { ++errors; break; }
                } catch (...) { ++errors; break; }
            }
        }
        running.store(false);
        // Stop before clearing pending slots: concurrent playSound sees running=false.
        for (unsigned i = 0; i < config.maxVoices; ++i) Finish(i, SoundState::Stopped);
        { std::lock_guard<std::mutex> lock(commandMutex);
          for (auto& command : commands) command = Command{};
          commandCount = readCommand = 0; }
        active.store(0);
        if (backend) backend->Close();
    }
};

AudioManager::AudioManager(std::unique_ptr<Audio::Backend> backend)
    : impl(std::make_unique<Impl>(backend ? std::move(backend) : Audio::CreateVitaBackend())) {}
AudioManager::~AudioManager() { if (!shutdown()) std::terminate(); }

bool AudioManager::init(const AudioConfig& config) {
    std::lock_guard<std::mutex> lifecycle(impl->lifecycleMutex);
    if (impl->worker.joinable() || !config.maxVoices || config.maxVoices > Audio::MaxVoices || !impl->backend) return false;
    impl->config = config; impl->budget->limit = config.residentBudgetBytes;
    impl->startupDone = impl->startupSuccess = false;
    impl->busVolume[0] = impl->busVolume[1] = impl->busVolume[2] = impl->masterVolume = 1.f;
    impl->paused = false; impl->running.store(true);
    try { impl->worker = std::thread([this]() { impl->Run(); }); }
    catch (...) { impl->running.store(false); return false; }
    std::unique_lock<std::mutex> ready(impl->startupMutex);
    impl->startupReady.wait(ready, [this]() { return impl->startupDone; });
    if (impl->startupSuccess) return true;
    ready.unlock(); impl->worker.join(); return false;
}

bool AudioManager::shutdown() {
    std::lock_guard<std::mutex> lifecycle(impl->lifecycleMutex);
    if (impl->worker.joinable() && impl->worker.get_id() == std::this_thread::get_id()) return false;
    impl->running.store(false);
    if (impl->worker.joinable()) impl->worker.join();
    std::lock_guard<std::mutex> bank(impl->bankMutex);
    std::lock_guard<std::mutex> lock(impl->commandMutex);
    impl->catalog.clear(); impl->banks.clear(); return true;
}

bool AudioManager::loadBank(const char* path) try {
    if (!path || !impl->running.load()) return false;
    std::lock_guard<std::mutex> loading(impl->bankMutex);
    std::vector<AudioDefinition> definitions; std::string error;
    std::unordered_map<SoundId, Impl::CatalogEntry> existing;
    std::unordered_map<std::string, std::vector<SoundId>> updatedBanks;
    { std::lock_guard<std::mutex> lock(impl->commandMutex);
      if (impl->banks.count(path)) return true;
      existing = impl->catalog; updatedBanks = impl->banks; }
    std::vector<std::shared_ptr<SoundAsset>> prepared;
    auto fail = [&](const std::string& message) {
        std::lock_guard<std::mutex> lock(impl->commandMutex); impl->lastError = message; return false;
    };
    if (!ReadAudioBank(path, definitions, error)) return fail(error);
    for (auto& definition : definitions) {
        const auto found = existing.find(AudioSoundId(definition.name.c_str()));
        if (found != existing.end()) {
            if (!SameDefinition(definition, found->second.asset->definition)) return fail("Conflicting sound ID or bank definition: " + definition.name);
            prepared.push_back(found->second.asset); continue;
        }
        auto asset = std::make_shared<SoundAsset>(); asset->definition = definition; asset->budget = impl->budget;
        std::unique_ptr<FILE, FileCloser> file(fopen(definition.path.c_str(), "rb"));
        if (!file) return fail("Sound file not found: " + definition.path);
        if (!ReadAudioHeader(file.get(), asset->header, error)) return fail(definition.name + ": " + error);
        if (definition.storage == AudioStorage::Resident) {
            const size_t bytes = size_t(asset->header.dataBytes);
            const size_t used = impl->budget->bytes.load();
            if (used > impl->budget->limit || bytes > impl->budget->limit - used) return fail("Resident audio budget exceeded: " + definition.name);
            impl->budget->bytes.fetch_add(bytes); asset->reservedBytes = bytes;
            asset->resident.resize(bytes);
            if (fread(asset->resident.data(), 1, bytes, file.get()) != bytes) return fail("Truncated resident sound: " + definition.name);
        }
        prepared.push_back(std::move(asset));
    }
    auto& bank = updatedBanks[path];
    for (auto& asset : prepared) {
        const auto id = AudioSoundId(asset->definition.name.c_str());
        auto& entry = existing[id]; entry.asset = std::move(asset); ++entry.banks; bank.push_back(id);
    }
    // All allocations and reads precede publication. A rejected bank leaves
    // the currently playable catalog intact, including after allocation failure.
    std::lock_guard<std::mutex> lock(impl->commandMutex);
    if (!impl->running.load()) return false;
    impl->catalog.swap(existing); impl->banks.swap(updatedBanks);
    impl->lastError.clear(); return true;
} catch (const std::exception& exception) {
    std::lock_guard<std::mutex> lock(impl->commandMutex);
    impl->lastError = exception.what(); return false;
}

bool AudioManager::unloadBank(const char* path) {
    if (!path) return false;
    std::lock_guard<std::mutex> loading(impl->bankMutex);
    std::lock_guard<std::mutex> lock(impl->commandMutex);
    auto bank = impl->banks.find(path); if (bank == impl->banks.end()) return false;
    auto retired = std::make_shared<std::vector<SoundId>>();
    for (auto id : bank->second) if (impl->catalog.at(id).banks == 1) retired->push_back(id);
    if (!impl->running.load() || impl->commandCount == CommandCapacity) { ++impl->rejected; return false; }
    std::sort(retired->begin(), retired->end());
    Impl::Command command; command.operation = Impl::Operation::Unload; command.retiredSounds = retired;
    if (!impl->Enqueue(std::move(command))) return false;
    for (auto id : bank->second) {
        auto& entry = impl->catalog.at(id);
        if (--entry.banks == 0) {
            impl->catalog.erase(id);
        }
    }
    impl->banks.erase(bank); return true;
}

SoundHandle AudioManager::playSound(SoundId sound, const SoundOptions& options) {
    if (!Gain(options.volume) || !Pan(options.pan) || unsigned(options.loop) > unsigned(SoundLoop::Loop)) return {};
    std::lock_guard<std::mutex> lock(impl->commandMutex);
    const auto entry = impl->catalog.find(sound);
    if (entry == impl->catalog.end() || !impl->running.load()) return {};
    for (unsigned index = 0; index < impl->config.maxVoices; ++index) {
        const auto state = impl->slots[index].state.load();
        if (state == SoundState::Playing || state == SoundState::Pending || state == SoundState::Paused) continue;
        const SoundHandle handle{(++impl->generation << 8) | index};
        Impl::Command command; command.operation = Impl::Operation::Play;
        command.handle = handle; command.asset = entry->second.asset; command.options = options;
        // Publish Pending before the worker can see the command.
        impl->slots[index].handle.store(handle.value); impl->slots[index].state.store(SoundState::Pending);
        if (!impl->Enqueue(std::move(command))) { impl->slots[index].state.store(SoundState::Stopped); return {}; }
        return handle;
    }
    ++impl->rejected; return {};
}

bool AudioManager::stopSound(SoundHandle handle, float seconds) {
    if (!handle || !Fade(seconds)) return false;
    std::lock_guard<std::mutex> lock(impl->commandMutex);
    unsigned index = unsigned(handle.value & 255);
    if (index >= impl->config.maxVoices || impl->slots[index].handle.load() != handle.value) return false;
    Impl::Command command; command.operation = Impl::Operation::Stop; command.handle = handle; command.value = seconds;
    return impl->Enqueue(std::move(command));
}
bool AudioManager::stopAll(float seconds) {
    if (!Fade(seconds)) return false;
    std::lock_guard<std::mutex> lock(impl->commandMutex);
    Impl::Command command; command.operation = Impl::Operation::StopAll; command.value = seconds;
    return impl->Enqueue(std::move(command));
}
bool AudioManager::setVolume(SoundHandle handle, float volume) {
    if (!handle || !Gain(volume)) return false;
    std::lock_guard<std::mutex> lock(impl->commandMutex);
    unsigned index = unsigned(handle.value & 255);
    if (index >= impl->config.maxVoices || impl->slots[index].handle.load() != handle.value) return false;
    Impl::Command command; command.operation = Impl::Operation::Volume; command.handle = handle; command.value = volume;
    return impl->Enqueue(std::move(command));
}
bool AudioManager::setPan(SoundHandle handle, float pan) {
    if (!handle || !Pan(pan)) return false;
    std::lock_guard<std::mutex> lock(impl->commandMutex);
    unsigned index = unsigned(handle.value & 255);
    if (index >= impl->config.maxVoices || impl->slots[index].handle.load() != handle.value) return false;
    Impl::Command command; command.operation = Impl::Operation::Pan; command.handle = handle; command.value = pan;
    return impl->Enqueue(std::move(command));
}
bool AudioManager::setBusVolume(AudioBus bus, float volume) {
    if (unsigned(bus) > 2 || !Gain(volume)) return false;
    std::lock_guard<std::mutex> lock(impl->commandMutex);
    Impl::Command command; command.operation = Impl::Operation::BusVolume; command.bus = unsigned(bus); command.value = volume;
    return impl->Enqueue(std::move(command));
}
bool AudioManager::setMasterVolume(float volume) {
    if (!Gain(volume)) return false;
    std::lock_guard<std::mutex> lock(impl->commandMutex);
    Impl::Command command; command.operation = Impl::Operation::MasterVolume; command.value = volume;
    return impl->Enqueue(std::move(command));
}
bool AudioManager::setPaused(bool paused) {
    std::lock_guard<std::mutex> lock(impl->commandMutex);
    Impl::Command command; command.operation = Impl::Operation::Pause; command.value = paused ? 1.f : 0.f;
    return impl->Enqueue(std::move(command));
}
SoundState AudioManager::getState(SoundHandle handle) const {
    unsigned index = unsigned(handle.value & 255);
    if (!handle || index >= impl->config.maxVoices || impl->slots[index].handle.load() != handle.value) return SoundState::Stopped;
    const auto state = impl->slots[index].state.load();
    return impl->slots[index].handle.load() == handle.value ? state : SoundState::Stopped;
}
bool AudioManager::isPlaying(SoundHandle handle) const {
    auto state = getState(handle);
    return state == SoundState::Pending || state == SoundState::Playing || state == SoundState::Paused;
}
AudioStats AudioManager::getStats() const {
    return {impl->budget->bytes.load(), impl->active.load(), impl->rejected.load(), impl->errors.load()};
}
std::string AudioManager::getLastError() const {
    std::lock_guard<std::mutex> lock(impl->commandMutex); return impl->lastError;
}
