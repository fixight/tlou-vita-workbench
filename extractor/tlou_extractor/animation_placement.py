"""Native animation-placement curves, separate from skeletal poses."""
from .anim_codec import AnimationDecodeError
from .door_interaction_data import animation_entry, compose_rigid, inverse_rigid
from .cinematic_camera import read_transform_curve


def placement_motion(pak, item, locator, fps, expected_frames):
    """Expand the component-packed apReference into actor world transforms.

    Placement and camera channels share transform packing. Constant components
    are retained across frames, including wholly stationary object references.
    """
    entry = animation_entry(pak, item)
    if not entry:
        raise AnimationDecodeError('Missing animation placement')
    curve = read_transform_curve(pak, entry['channel_offset'])
    if curve['frame_count'] != expected_frames:
        raise AnimationDecodeError('Placement and pose frame counts disagree')
    samples = []
    for transform in curve['samples']:
        if any(abs(value - 1) > 1e-5 for value in transform['scale']):
            raise AnimationDecodeError('Non-rigid animation placement scale')
        world = compose_rigid(locator, inverse_rigid(transform))
        samples.append(world['position'] + world['rotation_xyzw'])
    return {'fps': fps, 'samples': samples, 'flags': entry['flags'],
            'semantics': 'locator_world * inverse(apReference(t))'}
