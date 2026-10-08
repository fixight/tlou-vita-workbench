"""PS4 AC primary-pose bytecode and predictive log-quaternion codec.

Offsets in the pose maps address 48-byte S/Q/T joint records. Working-vector
offsets address 32-byte slots (the runtime evaluates two samples at once).
This module deliberately does not interpret RAWCHANNELS hashes as bone names.
"""
import math
import struct
from dataclasses import dataclass


class AnimationDecodeError(ValueError):
    pass


@dataclass(frozen=True)
class Command:
    opcode: int
    count: int
    offset: int
    args: tuple
    per_curve: bool = False

    @property
    def first_curve(self):
        if not self.args or self.args[0] % 32:
            raise AnimationDecodeError('unaligned working-vector offset')
        return self.args[0] // 32


def require(data, offset, size):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise AnimationDecodeError(f'truncated animation data at {offset:#x} ({size} bytes)')


def commands(section):
    require(section, 0, 8)
    limit = struct.unpack_from('<H', section, 6)[0]
    if limit < 8:
        raise AnimationDecodeError('invalid command-table boundary')
    require(section, 0, limit)
    result = []
    offset = 0
    while offset < limit:
        require(section, offset, 2)
        opcode = struct.unpack_from('<H', section, offset)[0]
        if opcode == 0:
            break
        size = 2 * ((opcode >> 8) + 1)
        if size < 8 or offset + size > limit:
            raise AnimationDecodeError(f'invalid command {opcode:#x} at {offset:#x}')
        fields = struct.unpack_from(f'<{size // 2}H', section, offset)
        if fields[2] != 3:
            raise AnimationDecodeError(f'unsupported command addressing mode {fields[2]}')
        result.append(Command(opcode, fields[1] & 0x7fff, fields[3], fields[4:], bool(fields[1] & 0x8000)))
        offset += size
    return result


def unpack_vector64(data, offset, signed):
    """Truncated IEEE floats, Z/Y/X in 21/21/22 bits; scales omit signs."""
    require(data, offset, 8)
    bits = int.from_bytes(data[offset:offset + 8], 'little')
    out = []
    for width in (21, 21, 22):
        value = bits & ((1 << width) - 1)
        bits >>= width
        value <<= (32 if signed else 31) - width
        out.append(struct.unpack('<f', struct.pack('<I', value))[0])
    if not all(math.isfinite(v) for v in out):
        raise AnimationDecodeError('non-finite quantization parameters')
    return tuple(reversed(out))


def normalize(q):
    length = math.hypot(*q)
    if not math.isfinite(length) or length < 1e-12:
        raise AnimationDecodeError('invalid quaternion')
    return tuple(v / length for v in q)


def multiply(a, b):
    x, y, z, w = a
    X, Y, Z, W = b
    return (w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X,
            w*Z+x*Y-y*X+z*W, w*W-x*X-y*Y-z*Z)


def quaternion_exp(v):
    """Stored values are quaternion logarithms, not imaginary components."""
    angle = math.hypot(*v)
    if not math.isfinite(angle):
        raise AnimationDecodeError('non-finite log-quaternion')
    scale = math.sin(angle) / angle if angle else 1.0
    return (v[0]*scale, v[1]*scale, v[2]*scale, math.cos(angle))


def quaternion48(data, offset):
    require(data, offset, 6)
    bits = int.from_bytes(data[offset:offset+6], 'little')
    largest = bits & 3
    values = [(((bits >> shift) & ((1 << width)-1)) / (1 << (width-1)) - 1) / math.sqrt(2)
              for shift, width in ((2,15), (17,15), (32,16))]
    values.reverse()
    # The omitted component was swapped with W before packing, not removed
    # with a shift of the remaining components. Insertion corrupts X/Y-largest
    # rotations (notably the heel), while identity/Z-largest still look right.
    values.append(math.sqrt(max(0, 1 - sum(v*v for v in values))))
    values[largest], values[3] = values[3], values[largest]
    return normalize(values)


def decode_primary(section, stream, stride, frame_count, bone_count):
    """Return {(bone index, TRS path): samples}, plus unsupported opcodes.

    Unknown operations are reported. They never invoke a guessed codec or a
    motion filter. Secondary-pose/float-property streams are separate from this
    primary skeletal stream and are not yet evaluated here.
    """
    ops = commands(section)
    output = {}
    unsupported = set()

    def target(slot):
        bone, field = divmod(slot, 48)
        if bone >= bone_count:  # Padding writes go to the dummy joint.
            return None
        path = {0: 'scale', 16: 'rotation', 32: 'translation'}.get(field)
        if path is None:
            raise AnimationDecodeError(f'invalid pose destination {slot}')
        return bone, path

    def put(slot, values):
        key = target(slot)
        if key is None:
            return
        if key[1] == 'rotation':
            continuous = []
            for value in values:
                q = normalize(value)
                if continuous and sum(a*b for a,b in zip(continuous[-1],q)) < 0:
                    q = tuple(-v for v in q)
                continuous.append(q)
            values = continuous
        if not all(math.isfinite(v) for sample in values for v in sample):
            raise AnimationDecodeError('non-finite pose value')
        output[key] = values

    def slots(op):
        require(section, op.offset, op.count * 2)
        return struct.unpack_from(f'<{op.count}H', section, op.offset)

    for op in ops:
        if op.opcode not in (789,790,791,792):
            continue
        values_at = op.offset + op.count * 2
        for i, slot in enumerate(slots(op)):
            if target(slot) is None:
                continue
            if op.opcode in (789,790):
                size = 12 if op.opcode == 789 else 6
                require(section, values_at + i*size, size)
                value = struct.unpack_from('<3f' if op.opcode == 789 else '<3e', section, values_at+i*size)
                if slot % 48 == 16:
                    raise AnimationDecodeError('vector constant targets a rotation')
            else:
                if slot % 48 != 16:
                    raise AnimationDecodeError('quaternion constant targets a vector')
                if op.opcode == 791:
                    require(section, values_at + i*16, 16)
                    value = struct.unpack_from('<4f', section, values_at+i*16)
                else:
                    value = quaternion48(section, values_at+i*6)
            put(slot, [value] * frame_count)

    width_ops = [op for op in ops if op.opcode == 1547]
    if not width_ops and stride != 0:
        unsupported.update(op.opcode for op in ops if op.opcode not in (789,790,791,792))
        return output, unsupported
    require(stream, 0, stride * frame_count)
    packed_frames = [int.from_bytes(stream[f*stride:(f+1)*stride], 'big')
                     for f in range(frame_count)]
    widths, bit_offsets, vectors, rotations = [], [], [], {}
    if not width_ops and stride == 0:
        # Zero-bit quantized curves still carry their constant bias and rotation
        # basis; some cinematic chunks omit the empty width-table command.
        curve_count = max((op.first_curve+op.count for op in ops
                           if op.opcode in (1050,1051,1052,1053,1054,1039,1040)), default=0)
        widths, bit_offsets = [0] * curve_count, [0] * curve_count
        vectors = [None] * curve_count

    for op in ops:
        if op.opcode == 1547:
            # A cinematic chunk can decode several groups into the same working
            # vectors. args[1] is the group's byte offset within each frame;
            # args[2] is the full frame stride, not the group's byte length.
            if len(op.args) != 3 or op.args[0] != 0:
                raise AnimationDecodeError('unsupported width-table stream addressing')
            require(section, op.offset, op.count if op.per_curve else 1)
            widths = (list(section[op.offset:op.offset+op.count]) if op.per_curve
                      else [section[op.offset]] * op.count)
            used = op.args[1] * 8
            bit_offsets = []
            for width in widths:
                bit_offsets.append(used)
                used += width
            if used > stride * 8:
                raise AnimationDecodeError('curve widths exceed the frame stride')
            vectors, rotations = [None] * len(widths), {}
            # Raw cinematic curves are already IEEE components. They have no
            # quantizer command between the width table and the pose map.
            for curve, width in enumerate(widths):
                if width not in (96,128):
                    continue
                values = []
                for packed in packed_frames:
                    code = (packed >> (stride*8-bit_offsets[curve]-width)) & ((1 << width)-1)
                    value = tuple(reversed(struct.unpack('>3f' if width == 96 else '>4f',
                                                         code.to_bytes(width//8, 'big'))))
                    values.append(value)
                if width == 96:
                    vectors[curve] = values
                else:
                    rotations[curve] = values
        elif op.opcode == 1051:
            first = op.first_curve
            if first + op.count > len(widths):
                raise AnimationDecodeError('quantizer exceeds the curve table')
            require(section, op.offset, op.count * 16 + (op.count if op.per_curve else 1) * 4)
            for i in range(op.count):
                curve = first + i
                scale = unpack_vector64(section, op.offset+i*16, False)
                bias = unpack_vector64(section, op.offset+i*16+8, True)
                cx, cy, xy_bits, cz = struct.unpack_from('<4B', section, op.offset+op.count*16+(i if op.per_curve else 0)*4)
                counts = (cx & 63, cy & 63, cz & 63)
                predictors = (cx >> 6, cy >> 6, cz >> 6)
                width = widths[curve]
                if xy_bits != counts[0]+counts[1] or (width and width != sum(counts)):
                    raise AnimationDecodeError('component widths disagree with the frame table')
                if any(predictors) and (curve == 0 or vectors[curve-1] is None):
                    raise AnimationDecodeError('missing predictive predecessor')
                samples = []
                for frame, packed in enumerate(packed_frames):
                    code = (packed >> (stride*8-bit_offsets[curve]-width)) & ((1 << width)-1)
                    xbits,ybits,zbits = counts
                    integers = ((code >> (ybits+zbits)) & ((1<<xbits)-1),
                                (code >> zbits) & ((1<<ybits)-1), code & ((1<<zbits)-1))
                    value = [bias[j] + scale[j]*integers[j] for j in range(3)]
                    for j, predictor in enumerate(predictors):
                        if predictor:
                            value[j] += vectors[curve-1][frame][predictor-1]
                    samples.append(tuple(value))
                vectors[curve] = samples
        elif op.opcode in (1050,1052):
            first = op.first_curve
            if first + op.count > len(widths):
                raise AnimationDecodeError('direct curve exceeds the frame table')
            if op.opcode == 1052:
                require(section, op.offset, (op.count if op.per_curve else 1) * 4)
            for i in range(op.count):
                curve = first + i
                width = widths[curve]
                if op.opcode == 1050:
                    if width != 48:
                        raise AnimationDecodeError('half-vector curve must use 48 bits')
                else:
                    cx, cy, xy_bits, cz = struct.unpack_from('<4B', section, op.offset+(i if op.per_curve else 0)*4)
                    counts = (cx & 63, cy & 63, cz & 63)
                    if any(v >> 6 for v in (cx,cy,cz)) or min(counts) < 1:
                        raise AnimationDecodeError('unsupported direct quaternion descriptor')
                    if xy_bits != counts[0]+counts[1] or width != sum(counts)+2:
                        raise AnimationDecodeError('quaternion widths disagree with the frame table')
                samples = []
                for packed in packed_frames:
                    code = (packed >> (stride*8-bit_offsets[curve]-width)) & ((1 << width)-1)
                    if op.opcode == 1050:
                        value = tuple(reversed(struct.unpack('>3e', code.to_bytes(6, 'big'))))
                    else:
                        # Same swap-with-W convention as the constant 48-bit codec.
                        largest = code & 3
                        code >>= 2
                        components = []
                        for bits in reversed(counts):
                            component = ((code & ((1 << bits)-1)) / (1 << (bits-1)) - 1) / math.sqrt(2)
                            components.append(component)
                            code >>= bits
                        components.reverse()
                        components.append(math.sqrt(max(0,1-sum(v*v for v in components))))
                        components[largest],components[3] = components[3],components[largest]
                        value = normalize(components)
                    samples.append(value)
                if op.opcode == 1050:
                    vectors[curve] = samples
                else:
                    rotations[curve] = samples
        elif op.opcode in (1053,1054):
            first = op.first_curve
            if first + op.count > len(vectors):
                raise AnimationDecodeError('rotation operation exceeds the curve table')
            size = ((op.count+1)//2)*16 if op.opcode == 1053 else op.count*16
            require(section, op.offset, size)
            for i in range(op.count):
                curve = first + i
                if vectors[curve] is None:
                    continue
                if op.opcode == 1053:
                    h = struct.unpack_from('<8h', section, op.offset+(i//2)*16)
                    a = normalize(h[i%2::2])
                    b = (0,0,0,1)
                else:
                    h = struct.unpack_from('<8h', section, op.offset+i*16)
                    a, b = normalize(h[::2]), normalize(h[1::2])
                rotations[curve] = [multiply(multiply(a, quaternion_exp(v)), b) for v in vectors[curve]]
        elif op.opcode in (1039,1040):
            first = op.first_curve
            for i, slot in enumerate(slots(op)):
                curve = first + i
                if target(slot) is None:
                    continue
                if curve >= len(vectors):
                    raise AnimationDecodeError('pose map exceeds the curve table')
                values = rotations.get(curve) if op.opcode == 1040 else vectors[curve]
                if values is not None:
                    if (slot % 48 == 16) != (op.opcode == 1040):
                        raise AnimationDecodeError('pose map type mismatch')
                    put(slot, values)
        elif op.opcode not in (789,790,791,792,1547):
            unsupported.add(op.opcode)
    return output, unsupported
