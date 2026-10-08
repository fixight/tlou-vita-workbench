//
// Created by egors on 29.07.2026.
//

#include <vitasdk.h>
#include <pthread.h>

#include "VitaEngine.h"
#include "System/DataLoader.h"

#include <psp2/kernel/sysmem.h>

// VitaSDK uses this C-linkage variable as the malloc/new heap size.
// GPU pools and decoder buffers have their own allocations.
extern "C" {
    unsigned int _newlib_heap_size_user = 320 * 1024 * 1024;
}


int main(int argc, char *argv[]) {

    // VitaSDK pthread_init returns 1 on success (unlike pthread_create).
    // Initialise before constructing anything that uses std::mutex/std::thread.
    if (pthread_init() == 0) {
        sceClibPrintf("[Startup] pthread runtime initialisation failed\n");
        sceKernelExitProcess(1);
        return 1;
    }
    sceClibPrintf("[Startup] pthread runtime ready\n");

    VitaEngine engine;
    engine.InitEngine();
    // 1. Включаем стики
    sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG);



    sceKernelExitProcess(0);
    return 0;
}
