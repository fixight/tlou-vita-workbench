> Историческая заметка от 2026-10-04. Актуальный порядок восстановления и состояние на 2026-10-08: [RESTORE.md](../RESTORE.md).

# TLOU Vita engine — recovery snapshot 2026-10-04

C++17 / VitaSDK / vitaGL. Sources include the original engine, collision and trigger
logic, packed 16-byte vertices, SK16 v1/v2 playback and door InteractionProcess.
Detailed parser/export pipeline and known limits: RECOVERY.md in the parser repository.

## Restore assets first

Extract `engine-assets.zip` into this repository. It contains `assets/level.bin`,
`assets/assets/models`, textures/metadata/chunks and `assets/characters/sarah16`.
Assets are not tracked in the source commit. Without them a source build is not a
playable reconstruction of the current scene. Do not replace only level.bin: VDOR
and VDIP sidecars must match the level hash.

## Build

Install VitaSDK and dependencies: vitaGL, vitashark, SceShaccCgExt, mathneon, taihen
and their required stubs/headers. Current compiler was arm-vita-eabi-g++ 15.2.0.
GLM is a pinned submodule in Engine/glm: clone with --recurse-submodules, or run
`git submodule update --init`. An offline glm.bundle is also in the backup. Dependency archive/manifests
in the backup retain the installed external libraries for exact recovery.

```sh
export VITASDK=/usr/local/vitasdk
cmake -S . -B cmake-build-debug-wsl -DCMAKE_BUILD_TYPE=Debug
cmake --build cmake-build-debug-wsl -j4
```

Output: eboot.bin and TLOU_Vita.vpk, title ID TLOU00001.
Optional auto-deployment: configure `-DVITA3K_APP_DIR=/path/to/ux0/app/TLOU00001`.
The previous user's path is used only when it already exists on this machine.
Packaging/copying the full assets directory can take several minutes.

## Tests

On Linux/WSL with g++:

```sh
python3 tools/tests/run_skinned_smoke.py
python3 tools/tests/run_door_smoke.py
python3 tools/tests/run_debug_smoke.py
```

These are host logic/format tests, not a measurement of performance on Vita.

## Animation and interaction implementation

- Engine/SkinnedModel.cpp: playback, pivot-aware quaternion transitions, GPU palettes;
- Objects/Character.cpp: movement and clip selection;
- Engine/InteractionProcess.h: approach/turn/playback state;
- Engine/DoorManager.cpp: interaction profiles, synchronized leaf pose/collision;
- Engine/VitaEngine.cpp: update order, collision and graphics submission.

Locomotion blends over 0.28 s; interactions over 0.18 s. New SK16 v2 packages retain
16-byte vertices and add 12 bytes per bind-space bone pivot (2772 bytes for Sarah).
No asynchronous asset loader yet. The main engine loop still runs in one thread.
