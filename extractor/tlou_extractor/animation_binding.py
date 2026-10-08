"""Resolve AC pose layouts using the AH skeleton signature, not clip names."""
from collections import Counter
from pathlib import Path
import struct
from .pak_reader import PakFile
from .skeleton_reader import SkeletonReader
from .anim_codec import AnimationDecodeError, require

_cache = {}

def clip_rig_id(pak, item):
    start = pak.read_ptr(item.abs_offset + 0x28)
    if not start:
        return None
    require(pak.data, start, 8)
    if pak.data[start:start+4] != b'\x02\x01CA':
        raise AnimationDecodeError('unsupported AC header')
    return struct.unpack_from('<I', pak.data, start+4)[0]


def skeleton_library(directory):
    directory = Path(directory)
    files = sorted(directory.glob('*skel*.pak'))
    fingerprint = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files)
    key = str(directory.resolve())
    cached = _cache.get(key)
    if cached and cached[0] == fingerprint:
        return cached[1]
    result = {}
    for path in files:
        skeleton = SkeletonReader.read_skeleton(PakFile(str(path)))
        if skeleton is None or skeleton.native_rig_id is None:
            continue
        rig = skeleton.native_rig_id
        previous = result.get(rig)
        if previous and [b.name for b in previous.bones] != [b.name for b in skeleton.bones]:
            raise AnimationDecodeError(f'ambiguous skeleton layout {rig:08x}')
        result.setdefault(rig, skeleton)
    _cache[key] = fingerprint, result
    return result


def compatible_variant(source, target):
    """Conservative named-rig retarget eligibility, not proportional retargeting.

    Both complete rigs must largely match, including the root. This prevents a
    prop/accessory's small subset from being mistaken for its owner's body.
    Actual per-track mapping still uses bone names, never numeric foreign slots.
    """
    if not source.bones or not target.bones or source.bones[0].name != target.bones[0].name:
        return False
    a, b = set(source.bone_by_name), set(target.bone_by_name)
    shared = len(a & b)
    return shared / len(a) >= .65 and shared / len(b) >= .65


def bank_source(pak, target, explicit=None):
    if explicit is not None or target is None or target.native_rig_id is None:
        return explicit or target
    rigs = Counter()
    for item in pak.get_items('ANIM'):
        try:
            rig = clip_rig_id(pak, item)
            if rig is not None:
                rigs[rig] += 1
        except AnimationDecodeError:
            pass  # The reader reports malformed items individually.
    if not rigs or rigs.most_common(1)[0][0] == target.native_rig_id:
        return target
    # A mixed bank's minority clips belong to partner actors/props. They must
    # not influence source selection for a bank requested for this character.
    dominant = rigs.most_common(1)[0][0]
    source = skeleton_library(Path(pak.filepath).parent).get(dominant)
    return source if source and compatible_variant(source, target) else target
