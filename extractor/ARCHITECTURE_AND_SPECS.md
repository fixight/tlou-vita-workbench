# The Last of Us (PS4) Engine & Reverse-Engineering Specification
**Target Audience**: Developers and AI Agents working on this codebase.  
**Project Goal**: Robust, clean, general extraction and conversion pipeline of Naughty Dog PS4 assets for a custom PS Vita game engine (and WebGL visual verification).

---

## 1. Architectural Philosophy & Constraints

1. **Platform Target: PS Vita Engine**:
   - Real-time performance on Vita GPU/CPU requires pruning micro-details (e.g. 20 individual toe joints, facial mimicry/eyeball micro-tracks).
   - Core locomotion must preserve source motion and avoid decoder-induced jitter. Validate fidelity against independent raw reference tracks; do not force bilateral symmetry or cap legitimate angular velocity.
2. **General Architecture (No Clip/Bone Crutches)**:
   - **Strict Rule**: Never write ad-hoc per-clip workarounds (e.g. `if clip == "sar-p-walk-fw": offset_y += 10`). Every calculation must be derived from Naughty Dog's binary tags and mathematical principles so ANY actor and ANY animation parses cleanly.
3. **Continuous Verification**:
   - The test suite in `tests/test_animations.py` contains strict tests (FK positions, IBM identity, quaternion continuity, limb symmetry). **Keep the test suite green; when a historical workaround conflicts with independent source data, replace it with a source-fidelity regression and document the evidence.**

---

## 2. PS4 PAK File Format (`tlou_extractor/pak_reader.py`)

* **Magic**: `0x0A79` (decimal `2681`). (Note: PC TLOU uses `0x0A7D` / `2685` and linear DDS textures; this project focuses strictly on PS4).
* **Pages & Fixups**: PAKs are paged memory dumps with pointer relocation tables. Pointers in resource headers are resolved via `pak.read_ptr(offset)`.
* **Resource Types (`ResItemEntry.type_id`)**:
  * `0x228`: `ANIM` — Skeletal animation header, channel tables, bitstream.
  * `0x229`: `ANIM_RAWCHANNELS` — Uncompressed root motion and pelvis trajectory.
  * `0x238`: `GEOMETRY_1` — Mesh vertex buffers, index buffers, submesh tables, collections, instances, shader descriptors.
  * `0x240`: `JOINT_HIERARCHY` — Skeleton bone names, parenting table, rest transforms.
  * `0x248`: `VRAM_DESC` — GPU texture metadata and morton swizzling parameters.
  * `0x250`: `TEXTURE_DICT` — Texture dictionaries (`world-home-tstrm.pak`).

---

## 3. Skeleton & Rigging (`tlou_extractor/skeleton_reader.py`)

### A. Structure of `JOINT_HIERARCHY`
- At `res_abs + 0x20` / `0x24`: Bone counts (`cnt_a`, `cnt_b`).
- At `res_abs + 0x28`: Pointer `xforms_ptr` to transform data block.
- At `res_abs + 0x38`: Pointer `names_ptr` to bone name string offsets.

### B. Native Binary Joint Hierarchy Table
- At `xforms_ptr + 0x4C`: `hier_off = unpack('<I', data, xforms_ptr + 0x4C)[0]`.
- At `base = xforms_ptr + hier_off`: `hashes_sz = unpack('<I', data, base + 20)[0]`.
- Table start: `p_start = base + 24 + (hashes_sz - 24)`.
- 16 bytes per joint: `(grp_id, parent_id, child_id, chain_id) = unpack('<4i', data, p_start + b * 16)`.
- **Parenting Rules**:
  - `parent_id` from binary table is authoritative.
  - Helper/twist/grp bones (`l_elbow_helper_grp`, `pelvis_helper_grp`) where `parent_id == -1` are reparented to their base bone using string regex clean-up:  
    `clean = re.sub(r'(_helper|_grp|_offset|_base|_twist[a-z]?|_muscle)+', '', name.lower())`.
  - **CRITICAL**: Never heuristically parent bones to `root` or `ankle` by substring match (`ball` -> eyeball vs foot ball).

### C. Local Transforms
- Start at `xforms_ptr + 144`, 48 bytes per bone:
  - `+0x00`: Scale `float32[3]` (sx, sy, sz).
  - `+0x10`: Rotation `float32[4]` (`qx, qy, qz, qw`).
  - `+0x20`: Translation `float32[3]` (tx, ty, tz).
- These transforms are **parent-relative local transforms**, NOT model space.
- Forward kinematics multiplied by Inverse Bind Matrices gives an exact Identity matrix with **0.0000 deformation error**.

---

## 4. Animation Engine (`anim_reader.py`, `anim_codec.py`)

### Confirmed primary-pose codec (2026-09-28)

The previous scalar SLERP interpretation, velocity clamps and cyclic filters were
incorrect. They are removed. No clip-name or bone-name motion corrections are used.
The decoder preserves native root, base, toe, scale and constant channels.

**AC header**, relative to `pak.read_ptr(ANIM.abs_offset + 0x28)`:

| Offset | Meaning |
|---|---|
| `+0x00` | Supported header prefix `02 01 43 41` |
| `+0x08` | Payload size, including its header |
| `+0x0e` | Number of sampled keys, uint16 |
| `+0x1c` | FPS, float32 |
| `+0x28` | Last sample index, e.g. 119 for 120 samples |
| `+0x2c` | Sample interval, **not clip duration** |
| `+0x30/+0x34/+0x36` | Primary command section offset/size/dummy-joint index |
| `+0x38/+0x3c` | Primary frame bitstream offset/byte stride |
| `+0x40` | Secondary command section offset (not decoded yet) |

Sample `f` occurs at `f / fps`; duration is `(num_keys - 1) / fps`.
Bounds are checked against the AC payload, not just the containing PAK.

**Command layout**: uint16 opcode, count, addressing mode, relative payload offset,
then additional uint16 arguments. Command size is `2 * ((opcode >> 8) + 1)`.
Thus 790/792 are 8 bytes, 1051/1053/1054 are 10, and 1547 is 14. Scanning every
2 bytes for apparent tag IDs can mistake command arguments for commands.
The count's high bit is excluded from the element count. Repeated opcodes are
retained in order. The first payload offset bounds the command list.

**Pose destinations** address 48-byte S/Q/T records: `bone = slot // 48`,
`slot % 48` is 0 for scale, 16 for rotation, 32 for translation. Destinations at
the dummy-joint index are padding. Working-vector offsets in command arguments
use 32 bytes per curve (the engine's two-sample evaluation layout).

| Opcode | Confirmed operation |
|---|---|
| 790 | uint16 pose map followed by constant float16 Vec3 values |
| 792 | uint16 pose map followed by constant 48-bit smallest-three quaternions |
| 1547 | Per-curve bit widths; frame fields read MSB first |
| 1051 | Quantized Vec3 ranges and predictive component descriptors |
| 1053 | Apply a base quaternion to an exponential-map rotation |
| 1054 | Apply left/right quaternion bases around an exponential-map rotation |
| 1039 | Copy working vectors to scale/translation pose slots |
| 1040 | Copy reconstructed quaternions to rotation pose slots |

**1051 quantizers**: `count * 16` bytes of ranges, followed by `count * 4`
component descriptors. Each range record consists of an unsigned-scale packed
Vec3 (8 bytes) and a signed-bias packed Vec3 (8 bytes). Their little-endian
64-bit fields are Z/Y/X with widths 21/21/22. Restore truncated IEEE float bits
by shifting each field left by `(31 - width)` for scales or `(32 - width)` for
biases, then reverse to XYZ order.

Descriptor bytes are `(X, Y, Xbits+Ybits, Z)`. Low six bits of X/Y/Z give component
widths; high two bits give a predictor selector. Dequantize `bias + scale * code`.
Selector zero means no predictor; selectors 1/2/3 add the **previous decoded
curve's X/Y/Z component at the same frame**. Reconstruct sequentially, including
predictor chains. Ignoring these selectors distorts correlated limb motion.

**Rotation reconstruction**: for decoded vector `v`, `a = length(v)`:

```python
D = (v * sin(a) / a, cos(a))  # identity for a == 0
Q_1053 = normalize(A * D)
Q_1054 = normalize(A * D * B)
```

1053 stores two base quaternions per 16-byte tile, interleaved as
`Ax, Bx, Ay, By, Az, Bz, Aw, Bw` (signed int16).
1054 stores the left/right bases in the same interleaved layout, one tile per
curve. Normalize the bases. These are not interpolation endpoints.
Keep quaternion hemispheres consistent; do not limit angular velocity or filter
sample values. Fast original movement must remain fast.

For 792, bits 0..1 select the omitted largest quaternion component. Remaining
fields at bit 2 (15 bits), bit 17 (15 bits), bit 32 (16 bits) are mapped by
`(code / 2**(bits-1) - 1) / sqrt(2)`, reversed, then the positive square-root
component is appended as W, then W is swapped with the omitted index. It is
not inserted with a shift: that misorders X/Y-largest quaternions and rotated
Sarah's static right heel by about 111 degrees. The native rest heel and the
independent animated log-quaternion representation confirm this ordering.

### Independent evidence and regression tests

In Sarah locomotion clips, raw channel hashes `0x14643f16` and `0x2195b1f1`
match **left and right ankle model-space transforms**, respectively. They are
not pelvis or upper-base channels. This interpretation is tested against FK;
it is not used to synthesize or correct the decoded pose.

Raw records of type `0x1e2` have a first Q/T sample at track+16, followed by
additional Q/T samples at track+56 with stride 28 bytes. The header supplies
the sample count. Do not generalize this layout to other raw track types.

`tests/test_anim_codec.py` compares every frame in forward walk, backward walk
and tired forward walk against both independent raw references. Tolerances:
2 mm maximum positional error, 3 mm maximum displacement-increment error,
0.25 degrees maximum orientation error. Synthetic tests cover predictive
reconstruction, quaternion exponentiation, paired bases, constants, truncation,
unsupported operations and export. Existing rest-pose, mesh and anatomy checks
remain. Historical tests that demanded root/toe removal, identical pelvis and
upper-base translations, or a 3.5-degree velocity cap were replaced: those rules
encoded workarounds and rejected source-accurate animation.

### Viewer and export

The viewer previously interpolated translation Z using the next key's Y.
Both `build_viewer.py` and `viewer.html` now use Z at both endpoints. This bug
caused between-frame motion even with valid GLB samples.
Constant exported channels retain only their first/last samples, preserving
clip duration. Nonconstant channels retain all samples.

### Explicit limits of this step

- 149 primary Sarah clips decode and are exported; compact headers for
  `sar-p-tense-idle` and `sar-p-tired-idle` are still unsupported and logged.
- Secondary-pose and float-property streams are not yet reconstructed.
- Shared infected banks (`anim-runner`, `anim-infected-hom`, `anim-clicker`,
  `anim-inf-shared`) use `infected-skel` joint order. `infected-fem-skel` has a
  different order starting at slot 18: source left clavicle versus target neck.
  Decode against the source skeleton, then bind tracks by exact bone name.
  Source-only joints are omitted; authored local transforms are preserved.
  This is joint binding, not proportional retargeting. Four bank fixtures verify
  identical upper-body world transforms on every frame after binding.
- Primary operations 1050/1052 observed in some Joel clips still need reverse
  engineering. Known channels can be returned with `clip.unsupported_opcodes`;
  those clips must not be treated as complete. Three other Joel clips currently
  fail component-width validation and are skipped with diagnostics.
- Coverage information is retained in glTF animation `extras.decoding`.
- Raw root locomotion accumulation and additive/layer composition remain outside
  the primary-pose decoder. No raw channel is assigned to a bone by guessed hash.

---

## 5. Level Chunks & Props (`tlou_extractor/mesh_builder.py`, `level_assembler.py`)

### A. PS4 `GEOMETRY_1` Data Pairs
- Pair 1 (`res_abs + 0x28` / `0x30`): `SubMeshDescTable` (stride 136B).
- Pair 2 (`res_abs + 0x38` / `0x40`): `Collections` (stride 120B).
  - Each collection has `uint32 submeshCount` at `+0x04` and `ptr64 namePtr` at `+0x10`.
  - Submeshes in Pair 1 are sequential: $\text{start\_submesh}_k = \sum_{j=0}^{k-1} \text{count}_j$.
- Pair 3 (`res_abs + 0x48` / `0x50`): `Instances` (stride 192B = `0xC0`).
  - `+0x08`: `ptr64 prototypeNamePtr` — matches the Collection name string with 100% precision.
  - `+0x24`: uint32 instance-local matrix palette count; `+0x38`: relocated palette pointer.
  - Each palette entry is a row-major 3x4 affine matrix (48 bytes). Submesh skin
    data at `SubMeshDesc + 0x60` selects entries with joint indices and weights.
    Bake these transforms before applying the world matrix. Different instances
    of the same books/frames/clutter prototype have different palettes.
  - `+0x60` / `+0x70`: local minimum/maximum bounds after palette deformation.
  - `+0x80`: 4x4 world matrix, stored as basis vectors followed by translation
    (column-major for column-vector multiplication, `float32[16]`).
  - **Instancing**: `worldPosition = worldMatrix * sum(weight * palette[joint] * position)`.
    With no palette, apply only the world matrix. Remove baked skin attributes
    to avoid deforming the same vertices again. Normals use the inverse transpose.
  - Verified against independent stored bounds for palette instances in
    `hom-house-interior` and `hom-town-freeway`; JavaScript viewer fixtures also
    check two differently arranged books instances. No per-prop offsets are used.
- Pair 5 (`res_abs + 0x68` / `0x70`): `ShaderDesc` array (stride 72B).
  - Material string pointer at `+0x00`.
  - Texture headers array at `+0x28`, count at `+0x34`.
  - Texture path at `+0x10` contains the exact 16-hex hash `.../<16HEX_HASH>.ndb`.

### B. Texture Resolution
- Auto-load texture dictionary `D:\TLOUPS4\Extracted\texturedict1\world-home-tstrm.pak`.
- Map textures strictly by 16-hex hash (O(1) exact matching). Avoid heuristic substring guessing.

---

## 6. Character Multi-Material Texturing Pipeline

### A. The Single-Texture / Eye-Texture Bug
- In earlier versions of `tlou_extractor/cli.py`, a single global material was created for the entire actor and assigned to all submeshes (`writer.add_submesh(sm, material_idx=mat_idx)`).
- The single texture was picked from whatever entry in `exported_tex` happened to match first (e.g. submesh 0 `eyes_lod0` matched `sarah-eyes-color.png`), stretching the eye texture across the head, shirt, pants, arms, and feet.

### B. Deterministic 16-Hex Hash Material Resolution
- In `GEOMETRY_1` Pair 5, every submesh extracts its exact 16-hex `diffuse_hash` and `normal_hash` from its `ShaderDesc`:
  * Sarah Head: `fa352cb02dbbc2d0` -> `sarah-head-fma2-color` (2048x2048)
  * Sarah Shirt: `d574762508d86a73` -> `fma-shirt-sarah-wrinkle-neutral-color` (2048x2048)
  * Sarah Pants: `13226466b29f595c` -> `fma-pants-sarah-color` (1024x1024)
  * Sarah Arms: `87c8515a72723379` -> `sarah-arm-hires-color` (1024x1024)
  * Sarah Feet: `4977fa07e5a943cd` -> `fma-sarah-feet-color` (256x256)
  * Sarah Eyes: `f3d8a5c5c27090b2` -> `sarah-eyes-color` (256x256)
  * Sarah Bracelets/Necklace: `3b2482832d471d94` -> `sarah-bracelets-necklace-color` (256x256)
- In `cli.py`, each submesh resolves its specific diffuse and normal textures via its hashes, creates or retrieves a distinct glTF material in `mat_cache`, and assigns it to `writer.add_submesh(sm, material_idx=sm_mat_idx)`.
- Master texture dictionaries (`world-home-tstrm.pak`, `sp-common-tstrm.pak`, `common-tstrm.pak`) are loaded into `TextureHandler`. High-resolution 2048x2048 master textures take precedence over low-res 64x64 base mips, and only referenced character textures are exported.

---

## 7. WebGL 3D Viewer & Server (`build_viewer.py`, `viewer.html`, `serve.py`)

* **Multi-Material WebGL Batching**:
  - `parseGLBBuffer` reads `prim.material` from glTF materials, extracts individual texture names and `texHash` from `mat.extras.diffuse_hash`.
  - `loadModelData` groups primitives by `sm.texHash || sm.texName`, maintaining separate WebGL draw batches and textures per submesh group.
  - Default fallback `glTexture` is initialized to a neutral 1x1 grey pixel, preventing cross-submesh texture contamination while network textures load.

* **Dual-Pass X-Ray Bone Visualization**:
  - `Pass 1`: `gl.depthMask(false)`, `gl.disable(gl.DEPTH_TEST)` with semi-transparent cyan lines (`#0fbbd459`) and amber joint nodes (`#f59e0b66`).
  - `Pass 2`: `gl.depthMask(true)`, `gl.enable(gl.DEPTH_TEST)`, `gl.depthFunc(gl.LEQUAL)` with opaque bright cyan lines (`#22d3ee`) and gold joint dots (`#fbbf24`).
* **Controls**:
  - `🦴 Кости: Вкл/Выкл` (Hotkey `B`) — toggle skeleton visualization.
  - `Space` — play/pause animation.
  - Quick-switch buttons in header: Sarah, Joel, Tommy, Runner.
* **Server**:
  - Run via `python serve.py` (serves on `http://127.0.0.1:8080/viewer.html`).
  - Uses `Cache-Control: no-cache, no-store, must-revalidate` to avoid browser texture caching issues.
  - At startup, discovers `texturedict1`, `pak32`, and `actor50` under extracted
    chapters in `D:\TLOUPS4` (override with `TLOU_ASSET_ROOT`). Textures can be
    served directly from another chapter's PAK without copying them.
  - The index cache is invalidated by source paths, sizes, and modification times.
  - A requested texture hash must match exactly. A missing hash returns 404;
    name-only requests accept exact names only, never substring/token guesses.
    The viewer keeps its existing texture on failure, matches batches by hash,
    and ignores responses for a model that has since been replaced.

---

## 8. Running Tests & CLI Commands

```bash
# 1. Run all automated unit tests
python -m unittest discover tests

# 2. Re-export characters to GLB/glTF
python -m tlou_extractor.cli -i D:\TLOUPS4\Extracted\actor50\sarah-tstrm.pak -o extracted_models
python -m tlou_extractor.cli -i D:\TLOUPS4\Extracted\actor50\young-joel-tstrm.pak -o extracted_models
python -m tlou_extractor.cli -i D:\TLOUPS4\Extracted\actor50\young-tommy-tstrm.pak -o extracted_models
python -m tlou_extractor.cli -i D:\TLOUPS4\Extracted\actor50\inf-fem-home-run-a-tstrm.pak -o extracted_models

# 3. Assemble level chunk
python -m tlou_extractor.cli -i D:\TLOUPS4\Extracted -c hom-house-interior -o output_house_interior

# 4. Rebuild WebGL viewer HTML
python build_viewer.py
```
