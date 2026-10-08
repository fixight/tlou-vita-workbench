"""Editable port input policy, deliberately separate from native script evidence."""
import copy
import math

PROFILES = {
    'gameplay': {'character_pose': 'gameplay', 'camera_pose': 'gameplay',
        'movement': True, 'camera_look': True, 'interaction': True, 'debug_camera': True},
    'full_cinematic': {'character_pose': 'cinematic', 'camera_pose': 'cinematic',
        'movement': False, 'camera_look': False, 'interaction': False, 'debug_camera': False},
    'camera_only': {'character_pose': 'cinematic', 'camera_pose': 'gameplay',
        'movement': False, 'camera_look': True, 'interaction': False, 'debug_camera': False},
}


def control_track(duration, changes=None):
    """Times are local seconds; restore the saved policy on completion or abort.

    A scripted character still plays its animation in camera_only mode. This
    setting selects the ordinary orbit camera; it does not add look to a native
    camera track. Native script switching times have not been decoded.
    """
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid cinematic duration')
    changes = [(0, 'full_cinematic')] if changes is None else changes
    events, previous = [], -1
    for time, profile in changes:
        if profile not in PROFILES or not math.isfinite(time) or not 0 <= time < duration or time <= previous:
            raise ValueError('Invalid control profile or ordered local time')
        previous = time
        events.append({'time': time, 'profile': profile, **copy.deepcopy(PROFILES[profile])})
    if not events or events[0]['time'] != 0:
        raise ValueError('A control track must begin at zero')
    return {'version': 1, 'source': 'port_authored_not_recovered_script',
        'on_exit': 'restore_previous', 'events': events}
