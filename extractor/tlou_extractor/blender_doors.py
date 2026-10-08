"""Door sidecars for LVL5. Authored port bindings; no original script VM."""
import json,struct,math
from pathlib import Path
import numpy as np
import bpy
from mathutils import Vector


def native(point):
    return (float(point[0]),float(point[2]),-float(point[1]))


def definitions(scene):
    result={}
    for obj in scene.objects:
        if obj.get('nd_type') != 'interactive_door':continue
        key=str(obj.get('nd_door_id') or obj.name)
        if key in result:raise ValueError('Duplicate door ID: '+key)
        result[key]={
            'id':key,'name':str(obj.get('nd_door_label',key)),
            'owner':str(obj.get('nd_level_id','level')),'pivot':native(obj.matrix_world.translation),
            'angle':float(obj.get('nd_door_angle',90)),
            'duration':float(obj.get('nd_door_duration',1.0)),
            'delay':float(obj.get('nd_door_delay',.45)),
            'volumes':json.loads(obj['nd_door_volumes']),
            'closed_bounds':json.loads(obj['nd_door_closed_bounds']),
            'source_region':str(obj.get('nd_door_source_region','')),
            'required_objects':json.loads(obj.get('nd_door_objects','[]')),
            'interaction_profile':json.loads(obj.get('nd_door_interaction_profile','null')),
        }
    for obj in scene.objects:
        if obj.get('nd_type') != 'interactive_door':continue
        key=str(obj.get('nd_door_id') or obj.name)
        profile=result[key].get('interaction_profile')
        marker=scene.objects.get(str(obj.get('nd_door_entry_object','')))
        if profile and marker:
            profile['entry']=native(marker.matrix_world.translation)
            profile['visual_yaw']=math.degrees(marker.matrix_world.to_euler().z)
    return result


def _hash(data):
    result=14695981039346656037
    for byte in data:result=((result^byte)*1099511628211)&0xffffffffffffffff
    return result


def _box_triangles(bounds):
    lo,hi=np.asarray(bounds,float)
    # A simple authored collider is needed where native background has no leaf.
    points=np.array([(x,y,z) for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])])
    faces=((0,1,3),(0,3,2),(4,6,7),(4,7,5),(0,4,5),(0,5,1),
           (2,3,7),(2,7,6),(0,2,6),(0,6,4),(1,5,7),(1,7,3))
    return points[np.array(faces)]


def _leaf_collision(triangles, bounds, claimed):
    lo,hi=np.asarray(bounds,float)
    # Containment, not proximity: frames/floors spanning outside the slab stay static.
    selected=np.flatnonzero(np.all((triangles>=lo-.045)&(triangles<=hi+.045),axis=(1,2)))
    selected=[int(i) for i in selected if int(i) not in claimed]
    claimed.update(selected)
    return selected, triangles[selected].copy() if selected else _box_triangles(bounds)


def _write(path, level_bytes, doors):
    _,instance_count,collision_count,_,*_=struct.unpack_from('<4sIII4f',level_bytes)
    data=bytearray(struct.pack('<4sIIIQI',b'VDOR',1,instance_count,collision_count,_hash(level_bytes),len(doors)))
    def text(value):
        encoded=value.encode('utf-8');data.extend(struct.pack('<I',len(encoded)));data.extend(encoded)
    for door in doors:
        text(door['id']);text(door['name'])
        data.extend(struct.pack('<6f',*door['pivot'],door['angle'],door['duration'],door['delay']))
        data.extend(struct.pack('<I',len(door['volumes'])))
        for volume in door['volumes']:data.extend(struct.pack('<6f',*volume['min'],*volume['max']))
        for indices in (door['instance_indices'],door['static_collision_indices']):
            data.extend(struct.pack('<I',len(indices)))
            data.extend(np.array(indices,dtype='<u4').tobytes())
        data.extend(struct.pack('<I',len(door['collision_triangles'])))
        data.extend(np.array(door['collision_triangles'],dtype='<f4').tobytes())
    path.write_bytes(data)


def write_sidecars(root, level_files, door_defs, bindings, exported_names):
    metadata=root/'assets/metadata';metadata.mkdir(parents=True,exist_ok=True)
    all_doors=[];instance_offset=0;collision_offset=0
    for owner,filename in level_files.items():
        raw=(root/filename).read_bytes()
        _,instance_count,collision_count,_,*_=struct.unpack_from('<4sIII4f',raw)
        triangles=np.frombuffer(raw,dtype='<f4',count=collision_count*9,offset=32).reshape(-1,3,3)
        local=[];claimed=set()
        for key,indices in bindings.get(owner,{}).items():
            door=dict(door_defs[key])
            missing=set(door['required_objects'])-exported_names
            if missing:raise ValueError('Export all parts of door '+key+': '+', '.join(sorted(missing)))
            removed,geometry=_leaf_collision(triangles,door['closed_bounds'],claimed)
            door.update(instance_indices=indices,static_collision_indices=removed,
                        collision_triangles=geometry.tolist(),
                        collision_source='native_background_leaf' if removed else 'authored_leaf_box')
            local.append(door)
            combined=dict(door)
            combined['instance_indices']=[i+instance_offset for i in indices]
            combined['static_collision_indices']=[i+collision_offset for i in removed]
            all_doors.append(combined)
        _write(metadata/('doors_'+Path(filename).stem+'.bin'),raw,local)
        from .vita_door_profiles import write_profiles
        write_profiles(metadata/('door_interactions_'+Path(filename).stem+'.bin'),raw,
                       [d['interaction_profile'] for d in local if d.get('interaction_profile')])
        instance_offset+=instance_count;collision_offset+=collision_count
    _write(metadata/'doors.bin',(root/'level.bin').read_bytes(),all_doors)
    from .vita_door_profiles import write_profiles
    write_profiles(metadata/'door_interactions.bin',(root/'level.bin').read_bytes(),
                   [d['interaction_profile'] for d in all_doors if d.get('interaction_profile')])
    report={'schema':'vita.interactive_doors','version':1,'coordinate_system':'native Y up metres',
            'binding_origin':'authored_port_binding','doors':all_doors}
    (metadata/'doors.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'file':'assets/metadata/doors.bin','doors':len(all_doors),
            'native_leaf_triangles':sum(len(d['static_collision_indices']) for d in all_doors),
            'authored_leaf_colliders':sum(d['collision_source']=='authored_leaf_box' for d in all_doors)}
