# Native study cinematic camera evidence

The PS4 eboot camera samplers at file offsets `0x75c260` and `0x75c580`
request auxiliary ANIM channels, separate from the primary skeletal AC stream.
At `0x75c2b8` the first sampler selects `0x306c3455`, then calls the auxiliary
sampler at `0x9fe2d0`. At `0x75c2eb` it selects `align` (`0x76655cc5`).
The code at `0x75c2ff..0x75c419` rotates the camera position by align,
adds the align translation and multiplies/normalizes their quaternions.

These are local camera transforms. The owning actor entry comes from
`inverse(apReference(0))`, placed at the shared scenario locator.
The resulting world transform is:

`locatorWorld * inverse(apReference(0)) * align(t) * cameraChannel(t)`

Independent verification: `ownerEntryWorld * align(t)` matches the actor's
full `locatorWorld * inverse(apReference(t))` motion across all three clips.
The preview uses authored world orientation directly, not the native
renderer-specific view representation built later in the function.

Precision is selected by bit `0x100` for both quaternion and vectors.
Bit `0x2` does not make a quaternion float32: camera `04-sick--joel`
uses `00e2` with half-float Q4/T3 and a 14-byte subsequent stride.

Verified curves:

| Joel clip | Frames | Camera flags | Subsequent sample bytes |
|---|---:|---|---:|
| hom1-house-study | 899 | 01e2 | 28 |
| hom1-house-study-backup | 157 | 0060 | 16 |
| hom1-house-study-and-escape-04-sick | 334 | 00e2 | 14 |
| hom1-house-study-and-escape-05-inf-reveal | 129 | 0040 | 18 |
| hom1-house-study-and-escape-outro | 1523 | 0040 | 18 |

First samples contain quaternion XYZW, translation XYZ, scale XYZ.
0040: ten half-floats first; subsequent Q4/T3/scale-XZ, scale Y constant.
01e2: ten float32 first; subsequent Q4/T3, all scale components constant.
The camera scale values are lens/cut metadata, not geometric scaling. See
native lens evidence below. The previous preview default of 60 vertical degrees
has been replaced with the original photographic lens calculation.

Scripts `ss-hom-house-study` and `ss-hom-house-escape` call camera-enable
with animated mode. Exact activation time and transitions remain unresolved.
Depth-of-field parameters are exported, but no blur or colour-grading pass is enabled.
Closed static double doors of the study are hidden in the preview because
scenario door opening is not yet reproduced. Source GLB is unchanged.

The study script references backup--joel at file offset 10032 and
backup--sarah at 10608 (CRC IDs 035009a0 / 60201365). Both camera owners
produce matching world trajectories within half-float quantization error.
The backup fragment is selectable before reveal/outro; exact inter-stage
activation times remain unresolved.


## Native lens and focus range (2026-10-07)

CameraControlAnimated `0x74b130..0x74b1ad` and `0x74b55e..0x74b5ea`
convert scale X as focal length (mm), using 36 mm horizontal film width:

```
baseFov = degrees(2 * atan2(36, focalLength > 0 ? 2*focalLength : 46.916))
blend = clamp(scaleY, 0, 1)
horizontalFov = baseFov*(1-blend) + 75*blend
```

Constants at `0x111da44..0x111da60`: 46.916, 36, radians-to-degrees,
1, 75, .5, .1, 0. Projection `0xa2ff23..0xa2ff4f` constructs inverse
half-angle tangent. Ray construction `0xa2ffc0..0xa2ffe4` applies that to
horizontal coordinates and additionally multiplies vertical coordinates by
aspect. Therefore glm/Three vertical FOV is `2*atan(tan(horizontalFov/2)/aspect)`.
At fractional frames interpolate focal length and blend *before* converting
FOV; interpolation of converted angles would produce a different lens curve.

`0xbf33e0` appends the camera index to a CRC state via MSB-first CRC32.
The camera base `0x47ca5e64`, with suffix "1", gives `0x306c3455`.
The DOF base `0x1129c474`, with suffix "1", gives `0xb1e7c2e0`.
This is why hashing just the string "camera" did not resolve the channel name.
The current cinematic slot is camera 1; other slots require the selected
camera index from the script, rather than arbitrary channel matching.

DOF extraction `0x74b6da..0x74b72f` reads translation XYZ / scale XY into
camera animation override fields 104,108,10c,110,114. `0x749634..0x74964c`
maps these to cc,d0,d4,d8,dc; the animated camera applies them as radius and
four DOF planes at `0x749a53..0x749b6c`. Native debug labels at
`0xaf144d..0xaf1770` confirm:

| Source component | Meaning |
|---|---|
| translation X | DOF blur radius |
| translation Y | near start distance |
| translation Z | near end distance |
| scale X | far start distance |
| scale Y | far end distance |
| scale Z | authored override disabled when >= .5 |

This is legacy plane-based DOF, **not** an aperture/f-stop channel and not a
unique focal distance. The sharp band is between near-end and far-start.
An override-disable flag does not prove that all runtime DOF is disabled;
other engine settings can still apply. Physical DOF settings exist separately
in the executable (film width, f-stop, focal length, focus plane), but their
script/volume overrides are not reconstructed by this channel exporter.

The auxiliary sampler `0x9fda85..0x9fdc43` uses camera scale Z for cuts:
when the interpolated marker lies strictly between .00001 and .99999 and
the adjacent marker difference exceeds .4, its interpolation weight becomes
1. Thus pose, lens and DOF all select the next frame together. At exact source
frame times original samples are retained. Older manifests without lens data
keep the previous pose-jump heuristic and vertical-FOV fallback.

Bedroom: 912 frames retained; first lens 50 mm -> 39.5977527 horizontal
degrees, first DOF [4,0,3.039513588,5.84795332,23.462293625,1]. The camera
marker changes at frame 757. This is data extraction, not a Sarah-specific
position correction. Verified on bedroom and all exported study camera clips.
