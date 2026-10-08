# AABB trigger diagnostics

The engine loads `app0:/assets/metadata/triggers.bin` after loading `level.bin`.
LVL5, PlayerStart, render instances and physical collision triangles are unchanged.

The Vita Blender exporter (v1.3) writes this sidecar alongside streaming metadata.
Rerun the updated `tools/blender/blender_vita_export.py` in Blender before exporting.
It imports the parser package from `D:/TLOUPS4/fervent-pascal`.

The diagnostic set includes callback gameplay/dialogue/effect areas in exported
chapter families, plus explicitly authored port bindings. Audio-only and reflection
zones and streaming selectors are omitted from this diagnostic set. Companion
logic PAKs are kept even when they have no visual chunk. Current Austin data: 83
regions. This is a chapter-wide diagnostic list; loading/unloading chunks does not
currently enable or disable its regions.

AABB coordinates use the same native Y-up metre space as LVL5. Blender edits are
collected by the streaming exporter. Each source volume becomes a separate AABB;
multiple volumes are ORed, never merged across an empty gap. Sphere, cylinder and
convex bounds are approximate, so an AABB may be entered before the original shape.
Original activation flags, callback conditions and task state are not executed.

After physical collision resolution, the normal probe matches the existing player
broadphase AABB: radius 0.35m, height 1.6m, feet at Character.GetPosition(). Noclip
uses a 0.1m camera probe and does not move the frozen character. Triggers do not
block movement or alter velocity, gravity, camera, spawn or physical collision.

Triangle toggles the existing HUD. Below render stats it shows active/loaded count,
probe type, up to four active names (small volumes first), additional active count,
and the most recent entered name. Full stable IDs and names remain in the manager;
the ASCII HUD truncates long names. Overlap is sampled once per frame, without swept
crossing detection. There are no actions or task handlers yet.

VTGR v1 is little endian: magic `VTGR`, u32 version, u32 trigger count; each record
contains two u32-length UTF-8 strings (stable region ID and display name), u32 box
count, then six float32 values per box (min XYZ, max XYZ). Load rejects malformed,
nonfinite, reversed or excessive data. Missing files leave an empty trigger system
and show a status in the HUD instead of breaking level loading. Loading resets state.

The overlap loop allocates no memory. HUD text is rebuilt only when membership or
probe mode changes. Original source actions are not bound automatically.

Verification (WSL):
```
python3 /home/TLOU_Vita/tools/tests/run_trigger_smoke.py
python3 /home/TLOU_Vita/tools/tests/run_debug_smoke.py
```
These host tests cover real TriggerManager/HUD code. They do not validate rendered
pixels or hardware timing. Use Vita3K or hardware to verify room alignment visually.

## Spatial view

Circle cycles Nearby (default), Focus, Off, once per press. Nearby draws up to three
visible trigger regions within 12m of the camera; Focus draws only one. Active areas
have priority, then distance to the nearest AABB. Volumes larger than 40m are hidden
from the spatial view to keep local room/door areas readable, but still participate
in overlap checks and the HUD. Distance uses distance to the box, not its centre.

Cyan edges are nearby areas; green edges belong to an active region. This colour
indicates overlap only, not permission to execute an original game callback. Edges
use scene depth testing so walls hide them. At most eight volumes are submitted in
one GL_LINES draw; rendering statistics continue to count scene geometry separately.

Small on-screen labels remove technical hom-house/rgn prefixes; they keep the
original descriptive words and a local index. Names are not inferred actions.
Label placement avoids the stats panel and nearby labels; connector lines lead to
the projected box centre. Labels are annotation overlays, so unlike edges their
text is not depth tested. A label requires a projected box centre inside the screen.
The existing Triangle toggle hides stats while leaving the spatial view visible;
use Circle to hide trigger geometry and labels. Original source names/IDs remain
available in the manager and HUD. There are still no bound actions or task logic.
