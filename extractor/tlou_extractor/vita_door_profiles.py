"""Offline native interaction compilation; runtime uses fixed-size samples."""
import json,math,struct
from pathlib import Path
import numpy as np
from .door_interaction_data import compose_rigid


def profile_from_evidence(document, door_name, locator_name=None):
    actors={r['name']:r for r in document['spawners']}
    actor=actors[door_name];character,door=document['paired_animation']['clips']
    transform={'position':actor['position'],'rotation_xyzw':actor['rotation_xyzw']}
    if locator_name:
        locator=actors[locator_name]
        shared={'position':locator['position'],'rotation_xyzw':locator['rotation_xyzw']}
    else:shared=compose_rigid(transform,door['animation_entry']['ap_reference'])
    entry=compose_rigid(shared,character['animation_entry']['relative_to_shared_locator'])
    def yaw(q):
        x,y,z,w=q
        return math.atan2(2*(w*y+x*z),1-2*(y*y+z*z))
    rotations=next(t for t in door['tracks'] if t['bone']=='door' and t['path']=='rotation')
    positions=next(t for t in character['tracks'] if t['bone']=='root' and t['path']=='translation')
    angles=np.unwrap([yaw(q) for q in rotations['values']]);angles-=angles[0]
    if rotations['times']!=positions['times']:raise ValueError('Paired sample clocks disagree')
    root=np.array(positions['values']);root-=root[0].copy()
    samples=[[time,float(angle),float(delta[0]),float(delta[2])]
             for time,angle,delta in zip(rotations['times'],angles,root)]
    return {'door_id':door_name,'clip':character['name'],'entry':entry['position'],
            'visual_yaw':math.degrees(yaw(entry['rotation_xyzw'])),
            'duration':character['duration'],'samples':samples,
            'origin':'native_apReference_and_paired_pose_curves',
            'locator':locator_name,'entry_reference':'character mesh/model origin, not pelvis',
            'root_motion':'XZ removed from skin matrices and applied once to actor/collider'}


def write_profiles(path,level_bytes,profiles):
    def _hash(raw):
        h=14695981039346656037
        for byte in raw:h=((h^byte)*1099511628211)&0xffffffffffffffff
        return h
    data=bytearray(struct.pack('<4sIQI',b'VDIP',1,_hash(level_bytes),len(profiles)))
    def text(value):
        encoded=value.encode('utf-8')
        if not encoded or len(encoded)>1024:raise ValueError('Profile identifier bounds')
        data.extend(struct.pack('<I',len(encoded))+encoded)
    seen=set()
    for p in profiles:
        if p['door_id'] in seen:raise ValueError('Duplicate door interaction profile')
        seen.add(p['door_id']);text(p['door_id']);text(p['clip'])
        data.extend(struct.pack('<5f',*p['entry'],p['visual_yaw'],p['duration']))
        keys=p['samples']
        if not 2<=len(keys)<=10000:raise ValueError('Interaction sample count')
        if abs(keys[0][0])>.001 or abs(keys[-1][0]-p['duration'])>.001:raise ValueError('Sample endpoints')
        if any(b[0]<=a[0] for a,b in zip(keys,keys[1:])):raise ValueError('Sample clock order')
        data.extend(struct.pack('<I',len(keys)))
        for key in keys:
            if len(key)!=4 or not all(math.isfinite(v) for v in key):raise ValueError('Invalid interaction sample')
            data.extend(struct.pack('<4f',*key))
    Path(path).write_bytes(data)
