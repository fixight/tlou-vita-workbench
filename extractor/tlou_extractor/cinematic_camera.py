"""PS4 animated camera poses, photographic lens and legacy depth-of-field curves.

Native camera samplers at eboot file offsets 0x75c260/0x75c580 request
0x306c3455 and compose it with `align` (0x76655cc5). The owning actor's
initial animation placement supplies the outer world transform.
"""
import math
import struct
from .anim_codec import AnimationDecodeError, require
from .door_interaction_data import animation_entry, compose_rigid

CAMERA_CHANNEL = 0x306c3455
ALIGN_CHANNEL = 0x76655cc5
DOF_CHANNEL = 0xb1e7c2e0
FILM_WIDTH_MM = 36.0
DEFAULT_FOCAL_LENGTH_MM = 23.458
DEFAULT_HORIZONTAL_FOV = 75.0


def horizontal_fov(scale):
    """Native 0x74b130: camera scale X is focal length, Y blends to 75 degrees.

    36 mm film width; nonpositive focal length uses the native 46.916 mm
    denominator. Scale Z belongs to cut detection, not geometric scaling.
    """
    focal_length, default_blend, _ = scale
    denominator = 2 * focal_length if focal_length > 0 else 2 * DEFAULT_FOCAL_LENGTH_MM
    angle = math.degrees(2 * math.atan2(FILM_WIDTH_MM, denominator))
    weight = max(0.0, min(1.0, default_blend))
    return angle * (1 - weight) + DEFAULT_HORIZONTAL_FOV * weight


def vertical_fov(horizontal_degrees, aspect):
    if not math.isfinite(aspect) or aspect <= 0:
        raise ValueError('Invalid camera aspect ratio')
    return math.degrees(2 * math.atan(math.tan(math.radians(horizontal_degrees) / 2) / aspect))


def extract_lens(pak, item, camera, fps):
    """Preserve every native sample; DOF uses four planes, not a focal target.

    CameraControlAnimated 0x74b55e converts focal length to horizontal FOV.
    0x74b6da maps DOF translation XYZ / scale XY; scale Z >= .5 disables
    the authored override. Neither this flag nor a missing channel means
    that all engine depth-of-field processing is disabled.
    """
    dof = channel_curve(pak, item, DOF_CHANNEL)
    if dof and dof['frame_count'] != camera['frame_count']:
        raise AnimationDecodeError('Camera/DOF frame counts disagree')
    lens_samples = []
    for index, value in enumerate(camera['samples']):
        focal, default_blend, cut = value['scale']
        lens_samples.append([horizontal_fov(value['scale']), focal, default_blend, cut])
    depth = None
    if dof:
        depth = {'channel_id': f'0x{DOF_CHANNEL:08x}',
                 'fields': ['blur_radius', 'near_start_m', 'near_end_m',
                            'far_start_m', 'far_end_m', 'override_disable'],
                 'samples': [v['position'] + v['scale'] for v in dof['samples']],
                 'curve': {k: v for k, v in dof.items() if k != 'samples'},
                 'semantics': 'sharp range between near_end and far_start; override disabled when final component >= .5'}
    return {'fps': fps, 'film_width_mm': FILM_WIDTH_MM,
            'fields': ['horizontal_fov_degrees', 'focal_length_mm', 'default_fov_blend', 'cut_marker'],
            'samples': lens_samples, 'depth_of_field': depth,
            'evidence': 'PS4 eboot 0x74b130 / 0x74b55e / 0x74b6da; DOF labels 0xaf144d..0xaf1770',
            'projection_axis': 'horizontal; 0xa2ff23 and 0xa2ffc0..0xa2ffe4',
            'cut_evidence': 'camera scale Z discontinuity checked by native sampler 0x9fda85..0x9fdc43'}


def channel_curve(pak, item, channel_id):
    field=item.abs_offset+0x30
    if field not in pak.pointer_page_ids:
        return None
    table=pak.read_ptr(field)
    require(pak.data,table,24)
    count=struct.unpack_from('<I',pak.data,table)[0]
    if not 0<count<=4096:
        raise AnimationDecodeError('Invalid auxiliary channel table')
    keys,values=pak.read_ptr(table+8),pak.read_ptr(table+16)
    require(pak.data,keys,count*4)
    require(pak.data,values,count*8)
    for index in range(count):
        if struct.unpack_from('<I',pak.data,keys+index*4)[0]==channel_id:
            return read_transform_curve(pak,pak.read_ptr(values+index*8))
    return None


def read_transform_curve(pak, offset):
    require(pak.data,offset,16)
    frames,flags=struct.unpack_from('<HH',pak.data,offset)
    if not frames or flags & ~0x1fe or flags & 1:
        raise AnimationDecodeError(f'Unsupported auxiliary transform packing {flags:#x}')
    if offset+8 not in pak.pointer_page_ids:
        raise AnimationDecodeError('Missing auxiliary transform relocation')
    payload=pak.read_ptr(offset+8)
    if not payload:
        raise AnimationDecodeError('Missing auxiliary transform relocation')
    # 0x100 selects component precision for both Q and vectors. In particular,
    # 0x00e2 contains half-float quaternions even though bit 0x2 is set.
    q_format='f' if flags & 0x100 else 'e'
    v_format='f' if flags & 0x100 else 'e'
    q_bytes=16 if flags & 0x100 else 8
    v_bytes=4 if flags & 0x100 else 2
    first_size=q_bytes+6*v_bytes
    require(pak.data,payload,first_size)
    first_q=list(struct.unpack_from('<4'+q_format,pak.data,payload))
    first_vectors=list(struct.unpack_from('<6'+v_format,pak.data,payload+q_bytes))
    # Constant-component flags: quaternion, translation X/Z, translation Y,
    # scale X, Y and Z. First frame always contains all components.
    masks=[4,16,4,32,64,128]
    variable=[i for i,mask in enumerate(masks) if not flags & mask]
    stride=(0 if flags & 8 else q_bytes)+len(variable)*v_bytes
    require(pak.data,payload+first_size,(frames-1)*stride)
    samples=[]
    for frame in range(frames):
        q,v=list(first_q),list(first_vectors)
        if frame:
            current=payload+first_size+(frame-1)*stride
            if not flags & 8:
                q=list(struct.unpack_from('<4'+q_format,pak.data,current))
                current+=q_bytes
            values=struct.unpack_from('<'+str(len(variable))+v_format,pak.data,current)
            for component,value in zip(variable,values):
                v[component]=value
        length=math.hypot(*q)
        if not all(math.isfinite(x) for x in q+v) or abs(length-1)>.005:
            raise AnimationDecodeError('Invalid auxiliary camera transform')
        samples.append({'rotation_xyzw':[x/length for x in q], 'position':v[:3],
                        'scale':v[3:]})
    return {'samples':samples,'frame_count':frames,'flags':f'0x{flags:04x}',
            'channel_offset':offset,'sample_offset':payload,'sample_stride':stride}


def extract_camera(pak, item, locator, fps, expected_frames):
    camera=channel_curve(pak,item,CAMERA_CHANNEL)
    if camera is None:
        return None
    align=channel_curve(pak,item,ALIGN_CHANNEL)
    if camera['frame_count']!=expected_frames or (align and align['frame_count']!=expected_frames):
        raise AnimationDecodeError('Camera/pose frame counts disagree')
    entry=animation_entry(pak,item)
    if not entry:
        raise AnimationDecodeError('Camera owner has no animation placement')
    actor_entry=compose_rigid(locator,entry['relative_to_shared_locator'])
    identity={'position':[0,0,0],'rotation_xyzw':[0,0,0,1]}
    world=[]
    for index,transform in enumerate(camera['samples']):
        alignment=align['samples'][index] if align else identity
        if align and any(abs(x-1)>.005 for x in alignment['scale']):
            raise AnimationDecodeError('Non-rigid camera alignment')
        result=compose_rigid(actor_entry,compose_rigid(alignment,transform))
        world.append(result['position']+result['rotation_xyzw'])
    lens = extract_lens(pak, item, camera, fps)
    return {'fps':fps,'samples':world,'duration':(expected_frames-1)/fps,
            'source_clip':item.name,'source_bank':pak.filepath,'source_offset':item.abs_offset,
            'camera_channel_id':f'0x{CAMERA_CHANNEL:08x}', 'camera_curve':{k:v for k,v in camera.items() if k!='samples'},
            'align_curve':{k:v for k,v in align.items() if k!='samples'} if align else None,
            'semantics':'owner_entry_world * align(t) * camera_channel(t)',
            'evidence':'PS4 eboot camera sampler 0x75c260 / 0x75c580',
            'lens': lens, 'fov_axis': 'horizontal',
            'fov_degrees': lens['samples'][0][0],
            'fov_source': 'native 36 mm film gate and animated focal length; camera scale Y blends to 75 degrees',
            'sampling':'all original transform samples retained; no inferred script cuts'}
