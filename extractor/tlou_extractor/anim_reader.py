"""
anim_reader.py - Parsing animation clips, curves, and bone tracks for TLOU PS4.
"""
import struct
import math
from typing import Dict, List, Optional, Tuple, Any
from .pak_reader import PakFile, ResItemEntry
from .skeleton_reader import Skeleton

def q_mul(q1: Tuple[float, float, float, float], q2: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    """Quaternion multiplication q1 * q2."""
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return (
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
        w1*w2 - x1*x2 - y1*y2 - z1*z2
    )

def q_conj(q: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    """Quaternion conjugate / inverse for unit quaternions."""
    return (-q[0], -q[1], -q[2], q[3])

def q_rot_vec(q: Tuple[float, float, float, float], v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Rotate 3D vector v by unit quaternion q."""
    qx, qy, qz, qw = q
    vx, vy, vz = v
    cx = 2.0 * (qy * vz - qz * vy)
    cy = 2.0 * (qz * vx - qx * vz)
    cz = 2.0 * (qx * vy - qy * vx)
    rx = vx + qw * cx + (qy * cz - qz * cy)
    ry = vy + qw * cy + (qz * cx - qx * cz)
    rz = vz + qw * cz + (qx * cy - qy * cx)
    return (rx, ry, rz)

def slerp(q1: Tuple[float, float, float, float], q2: Tuple[float, float, float, float], t: float) -> Tuple[float, float, float, float]:
    """Spherical Linear Interpolation between two unit quaternions q1 and q2."""
    dot = sum(a * b for a, b in zip(q1, q2))
    if dot < 0.0:
        q2 = (-q2[0], -q2[1], -q2[2], -q2[3])
        dot = -dot
    if dot > 0.9995:
        res = [(1.0 - t) * a + t * b for a, b in zip(q1, q2)]
        L = math.hypot(*res) or 1.0
        return (res[0] / L, res[1] / L, res[2] / L, res[3] / L)
    dot = min(1.0, max(-1.0, dot))
    theta_0 = math.acos(dot)
    sin_theta_0 = math.sin(theta_0)
    theta = theta_0 * t
    s0 = math.sin(theta_0 - theta) / sin_theta_0
    s1 = math.sin(theta) / sin_theta_0
    res = [s0 * a + s1 * b for a, b in zip(q1, q2)]
    L = math.hypot(*res) or 1.0
    return (res[0] / L, res[1] / L, res[2] / L, res[3] / L)

def decode_quaternion_drop_largest(u: int) -> Tuple[float, float, float, float]:
    """Decode a 32-bit drop-largest quantized quaternion from Naughty Dog PS4 ANIM Sec 3."""
    idx = (u >> 30) & 3
    c0 = (u >> 20) & 0x3FF
    c1 = (u >> 10) & 0x3FF
    c2 = u & 0x3FF

    inv_s = 1.0 / math.sqrt(2.0)
    s_scale = math.sqrt(2.0)
    v0 = (c0 / 1023.0) * s_scale - inv_s
    v1 = (c1 / 1023.0) * s_scale - inv_s
    v2 = (c2 / 1023.0) * s_scale - inv_s

    S = v0 * v0 + v1 * v1 + v2 * v2
    w = math.sqrt(max(0.0, 1.0 - S))

    comps = [v0, v1, v2]
    comps.insert(idx, w)

    # Mandatory Renormalization
    L = math.hypot(*comps) or 1.0
    return (comps[0] / L, comps[1] / L, comps[2] / L, comps[3] / L)

class AnimationTrack:
    def __init__(self, node_index: int, target_path: str = "rotation"):
        self.node_index = node_index
        self.target_path = target_path # "translation", "rotation", "scale"
        self.timestamps: List[float] = []
        self.values: List[List[float]] = [] # Vec3 for trans/scale, Quat for rot

class AnimationClip:
    def __init__(self, name: str, duration: float = 1.0, fps: float = 30.0):
        self.name = name
        self.duration = duration
        self.fps = fps
        self.tracks: List[AnimationTrack] = []
        self.unsupported_opcodes: List[int] = []
        self.has_secondary_stream = False
        self.source_rig_id: Optional[int] = None
        self.target_rig_id: Optional[int] = None

    def __repr__(self):
        return f"<AnimationClip '{self.name}' duration={self.duration:.2f}s tracks={len(self.tracks)}>"

class AnimationReader:
    @staticmethod
    def read_animations(pak: PakFile, skeleton: Optional[Skeleton] = None,
                        source_skeleton: Optional[Skeleton] = None) -> List[AnimationClip]:
        import logging
        from .anim_codec import AnimationDecodeError
        from .animation_binding import bank_source, clip_rig_id
        source = bank_source(pak, skeleton, source_skeleton)
        clips = []
        foreign = []
        failures = []
        partial = []
        for item in pak.get_items('ANIM'):
            try:
                rig = clip_rig_id(pak, item)
                clip_source = skeleton if skeleton is not None and rig == skeleton.native_rig_id else source
                if clip_source is not None and clip_source.native_rig_id is not None and rig != clip_source.native_rig_id:
                    foreign.append(item.name)
                    continue
                clip = AnimationReader._parse_clip(pak, item, clip_source)
                if clip and clip_source is not None and skeleton is not None and clip_source is not skeleton:
                    AnimationReader.remap_tracks(clip, clip_source, skeleton)
                if clip and skeleton is not None:
                    clip.target_rig_id = skeleton.native_rig_id
                if clip and clip.tracks:
                    clips.append(clip)
                    if clip.unsupported_opcodes:
                        partial.append(clip.name)
            except (AnimationDecodeError, struct.error) as exc:
                failures.append(f"{item.name}: {exc}")
        logger = logging.getLogger(__name__)
        if foreign:
            logger.info("Excluded %d clips for other skeleton layouts in %s (first: %s)",
                        len(foreign), pak.filepath, foreign[0])
        if failures:
            logger.warning("Skipped %d invalid/unsupported animations in %s: %s",
                           len(failures), pak.filepath, "; ".join(failures[:5]))
        if partial:
            logger.warning("%d animations have unsupported primary operations; inspect "
                           "clip.unsupported_opcodes (first: %s)", len(partial), partial[0])
        return clips

    @staticmethod
    def remap_tracks(clip: AnimationClip, source: Skeleton, target: Skeleton):
        """Bind source pose slots to named target joints; never reuse foreign indices.

        This preserves authored local transforms, not proportional retargeting.
        Source-only joints have no destination and are omitted.
        """
        mapped = []
        for track in clip.tracks:
            if not 0 <= track.node_index < len(source.bones):
                raise ValueError('animation track outside source skeleton')
            destination = target.bone_by_name.get(source.bones[track.node_index].name)
            if destination is not None:
                track.node_index = destination.index
                mapped.append(track)
        clip.tracks = mapped

    @staticmethod
    def _parse_clip(pak: PakFile, item: ResItemEntry, skeleton: Optional[Skeleton] = None) -> Optional[AnimationClip]:
        from .anim_codec import AnimationDecodeError, decode_primary, require
        data = pak.data
        require(data, item.abs_offset, 0x38)
        start = pak.read_ptr(item.abs_offset + 0x28)
        if not start:
            return None
        require(data, start, 0x50)
        if data[start:start+4] != b'\x02\x01CA':
            raise AnimationDecodeError('unsupported AC header')
        size = struct.unpack_from('<I', data, start+8)[0]
        require(data, start, size)
        payload = data[start:start+size]
        require(payload, 0, 0x50)
        rig_id = struct.unpack_from("<I", payload, 4)[0]
        if skeleton is not None and skeleton.native_rig_id is not None and rig_id != skeleton.native_rig_id:
            raise AnimationDecodeError(f"pose layout {rig_id:08x} does not match skeleton {skeleton.native_rig_id:08x}")
        count = struct.unpack_from('<H', payload, 0x0e)[0]
        fps = struct.unpack_from('<f', payload, 0x1c)[0]
        if count == 0 or not math.isfinite(fps) or fps <= 0:
            raise AnimationDecodeError('invalid sample count or frame rate')
        sec_off, sec_size, joint_count = struct.unpack_from('<IHH', payload, 0x30)
        stream_off, stride = struct.unpack_from('<IH', payload, 0x38)
        require(payload, sec_off, sec_size)
        require(payload, stream_off, count*stride)
        if not sec_off or not sec_size or not joint_count:
            raise AnimationDecodeError('missing primary pose section')
        # The section's dummy joint is distinct from a supplied skeleton's size.
        # Use the smaller bound so padding never becomes a real bone track.
        bone_count = min(joint_count, len(skeleton.bones)) if skeleton else joint_count
        samples, unsupported = decode_primary(
            payload[sec_off:sec_off+sec_size],
            payload[stream_off:stream_off+count*stride], stride, count, bone_count)
        clip = AnimationClip(item.name or item.item_name or 'anim', (count-1)/fps, fps)
        clip.source_rig_id = struct.unpack_from("<I", payload, 4)[0]
        clip.unsupported_opcodes = sorted(unsupported)
        clip.has_secondary_stream = bool(struct.unpack_from('<I', payload, 0x40)[0])
        times = [frame/fps for frame in range(count)]
        for (bone, path), values in samples.items():
            track = AnimationTrack(bone, path)
            track.timestamps = list(times)
            track.values = [list(value) for value in values]
            clip.tracks.append(track)
        return clip
