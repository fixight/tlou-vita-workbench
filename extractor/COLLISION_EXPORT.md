# Editor FBX and native collision export

Open one or several PAKs in the viewer, then choose **Экспорт FBX + коллизии**.
The button exports the whole loaded model, including when a submesh is isolated.
The ZIP contains `scene.fbx`, textures, `report.json`, the Blender log and original
Havok blobs where available. Blender runs in the background, without modifying
an open Blender session. Set `BLENDER_PATH` if automatic detection cannot find it.

This is a static geometry export, not an animation/rig export. Both visible
geometry and collision use the same Y-up to Blender Z-up conversion and meters.
Collision objects have a `COLLISION_` prefix and custom properties `collision`,
`collision_kind=triangle_mesh`, and `source_resource`. They are not convex hulls;
an engine must import them as triangle collision, not automatically run convex
decomposition. FBX importers may not preserve collections or viewport display
settings, so the object names and custom properties are authoritative.

Supported native collision: PS4 `COLLISION_DATA_HAVOK_BG`, 64-bit little-endian
Havok `hk_2011.3.0-r1`, one `hkpBvCompressedMeshShape` per packfile. No visual mesh
is used to fabricate collision. Other shapes, moving prop collision, material
responses, trigger behavior and physics constraints are not decoded yet.
If a level's collision lives in a separate PAK, include that PAK in the file
selection too. No collision in a supplied file is different from decoder failure;
both are reflected in the export report. GLB-only exports have no native PAK
collision source; load the PAK together with it when needed.

## Confirmed layout

Resource +0x2c is the Havok byte count; +0x30 is a relocated pointer. Resolve the
packfile's own local fixups separately from PAK fixups. The data section contains
the shape at offset 0. Tree bounds are +0x60/+0x70. Arrays: sections +0x90,
primitives +0xa0, shared indices +0xb0, packed vertices +0xc0, shared vertices
+0xd0. Sections are 96 bytes: bounds +16/+32, codec offset/scale +48/+60,
first packed vertex +72, shared range +76, primitive range +80, vertex counts
+88/+89. Packed coordinates are 11/11/10 bits with section scale and offset;
shared coordinates are 21/21/22 bits spanning the tree bounds. Four-byte
primitives describe triangles or quads, with duplicated final indices for
triangles. Decoder validates all indices and native section bounds.

Cross-game layout references used during investigation (no external runtime
dependency):
- [Soulstruct Havok section definitions](https://github.com/Grimrukh/soulstruct-havok/blob/main/src/soulstruct/havok/types/hk2014/_hkcd/hkcdStaticMeshTreeBaseSection.py)
- [Smithbox HKX2 vertex quantization](https://github.com/vawser/Smithbox/blob/main/src/Havok/HKX2/Manual/hknpCompressedMeshShapeData.cs)

Offsets and decoding were verified on the actual TLOU PS4 Havok 2011 files:
house 7,575 section vertices / 9,561 triangles; freeway 4,122 / 5,910.
Vertices shared across sections are intentionally retained; there is no
simplification or collision generation step.
Some native faces have both windings. Blender removes duplicate face topology,
so the exporter duplicates the three vertices for repeated faces, preserving
both windings and the original triangle count without changing coordinates.
