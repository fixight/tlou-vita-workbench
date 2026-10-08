// Standalone native test; it never loads a level or plays the intro movie.
#include "Managers/AudioManager.h"
#include <psp2/kernel/clib.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/threadmgr.h>
#include <pthread.h>

static bool PlayUntilFinished(AudioManager& audio, const char* name, unsigned timeoutMs) {
    auto voice = audio.playSound(name);
    if (!voice) { sceClibPrintf("[AudioTest] FAIL cannot queue %s\n", name); return false; }
    for (unsigned elapsed = 0; elapsed < timeoutMs; elapsed += 10) {
        auto state = audio.getState(voice);
        if (state == SoundState::Finished) {
            sceClibPrintf("[AudioTest] PASS %s completed\n", name); return true;
        }
        if (state == SoundState::Failed || state == SoundState::Stopped) {
            sceClibPrintf("[AudioTest] FAIL %s state=%d\n", name, int(state)); return false;
        }
        sceKernelDelayThread(10000);
    }
    audio.stopSound(voice);
    sceClibPrintf("[AudioTest] FAIL timeout %s\n", name); return false;
}
int main() {
    if (!pthread_init()) { sceClibPrintf("[AudioTest] FAIL pthread\n"); return 1; }
    AudioManager audio;
    sceClibPrintf("[AudioTest] before init\n");
    if (!audio.init()) { sceClibPrintf("[AudioTest] FAIL init\n"); return 1; }
    sceClibPrintf("[AudioTest] init ready\n");
    if (!audio.loadBank("app0:/assets/audio/smoke.vabk")) {
        sceClibPrintf("[AudioTest] FAIL init/bank %s\n", audio.getLastError().c_str()); return 1;
    }
    sceClibPrintf("[AudioTest] bank ready\n");
    bool pcm = PlayUntilFinished(audio, "pcm.smoke", 2000);
    bool at9 = PlayUntilFinished(audio, "sarah.phone.call", 30000);
    bool resident = PlayUntilFinished(audio, "sarah.phone.dead", 13000);
    const auto stats = audio.getStats();
    sceClibPrintf("[AudioTest] errors=%u resident=%u\n", stats.playbackErrors, unsigned(stats.residentBytes));
    audio.shutdown();
    sceClibPrintf("[AudioTest] %s shutdown resident=%u\n", pcm && at9 && resident && !stats.playbackErrors ? "PASS" : "FAIL", unsigned(audio.getStats().residentBytes));
    sceKernelExitProcess(pcm && at9 && resident && !stats.playbackErrors ? 0 : 1);
    return 0;
}
