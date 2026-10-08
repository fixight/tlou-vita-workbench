# Render HUD and noclip

Triangle shows/hides the HUD. SELECT toggles the existing ThirdPerson/Spectate modes.
Spectate is noclip: the camera flies freely, the character is frozen, velocity is
cleared, gravity and collision processing are skipped. Returning to ThirdPerson
restores gravity and collision. Character position is retained; there is no teleport
to the spectator camera. Spawn behavior and the LVL5 loader are unchanged.

HUD:
- FPS / frame ms: measured process-clock time between frames, averaged over ~0.5 s.
  This uses the raw interval, not the movement delta capped at 100 ms.
- SUBMIT: wall-clock CPU time spent in scene renderer calls. Not a GPU timer;
  may include driver stalls. HUD drawing is excluded from this timer.
- SCENE DRAWS / TRIANGLES / VERTICES: actual submitted triangle-list calls after
  distance and frustum culling. HUD's one extra draw is excluded. Triangles are
  submitted primitives, not the number of pixels or necessarily rasterized faces.
- OBJECTS / CULL / INVALID: submitted/tested instances and rejection counts.
- TEX/VBO BINDS: scene resource switches. VERTEX DATA is vertex bytes referenced
  by scene draws (16-byte stride), not uploads or resident VRAM.
- VISIBLE TEX: unique visible texture RGBA storage, not total GPU or process memory.
- UPLOAD: texture bytes newly uploaded that frame.
- PHYSICS: collision-processing wall time and resident collision triangle count.

VITA MODEL is deliberately labelled UNCALIBRATED. Its default assumptions are
optimistic/conservative CPU base 2/5 ms, 20/100 microseconds per draw, and
20/5 million submitted vertices per second. These are editable assumptions in
Engine/RenderStats.h, NOT measurements or specifications of Vita hardware.
It uses max(CPU, vertex-processing budget) and a 60 FPS cap. It does not use
the emulator FPS to infer the device FPS. It excludes fill rate, overdraw,
texture sampling, physics, streaming and HUD cost. Treat the displayed range
only as a rough workload model; calibrate the coefficients using real-device
measurements for this particular shader before relying on numerical predictions.

Host tests: `python3 tools/tests/run_debug_smoke.py`. They compile the real
renderer, HUD, camera and character sources with mock GL/controller calls and
verify counters, resource rebinding, noclip freeze/resume and SELECT debounce.
They do not test native shader compilation or rendered pixels. Build with the
normal VitaSDK CMake configuration to create the actual VPK.
