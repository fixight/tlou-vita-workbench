"""Package an extracted scene.json into Vita SK16 actors and VCN1 timeline.
World motion and camera curves remain in native Y-up metres.
"""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
import numpy as np
import export_vita_character as skin


def text(value):
    data = value.encode('utf-8')
    if not 0 < len(data) <= 1024 or b'\0' in data: raise ValueError('Invalid scene string')
    return struct.pack('<I',len(data)) + data


def track(value):
    samples = np.asarray(value['samples'],dtype='<f4')
    fps = float(value['fps'])
    if samples.ndim != 2 or samples.shape[1] != 7 or not len(samples) or not np.isfinite(samples).all() or not 0 < fps <= 120:
        raise ValueError('Invalid scene track')
    return struct.pack('<fI',fps,len(samples)) + samples.tobytes()


def lens_track(camera):
    lens = camera.get('lens')
    if not lens:
        raise ValueError('Re-extract native lens metadata before exporting VCN version 2')
    samples = np.asarray(lens['samples'],dtype='<f4')
    count = len(camera['samples'])
    if samples.shape != (count,4) or lens['fps'] != camera['fps'] or not np.isfinite(samples).all():
        raise ValueError('Camera/lens samples disagree')
    if ((samples[:,0] <= 0) | (samples[:,0] >= 180)).any():
        raise ValueError('Invalid lens FOV')
    depth = lens.get('depth_of_field')
    dof = np.asarray(depth['samples'],dtype='<f4') if depth else np.tile([0,0,0,0,0,1],(count,1))
    if dof.shape != (count,6) or not np.isfinite(dof).all():
        raise ValueError('Invalid depth-of-field samples')
    values = np.concatenate([samples,dof],axis=1).astype('<f4')
    return struct.pack('<fII',camera['fps'],count,1 if depth else 0) + values.tobytes()


def runtime_tracks(scene, source):
    """Controller and audio edits live beside the recovered scene, not in C++."""
    sidecar = source / 'scene.runtime.json'
    runtime = json.loads(sidecar.read_text(encoding='utf-8')) if sidecar.exists() else {}
    duration = sum(stage['duration'] for stage in scene['stages'])
    profiles = {'full_cinematic': 3, 'camera_only': 9, 'gameplay': 60}
    controls = runtime.get('control')
    if controls is None:
        controls = []
        offset = 0
        for stage in scene['stages']:
            for cue in stage.get('control',{}).get('events',[{'time':0,'profile':'full_cinematic'}]):
                controls.append({'time':offset+cue['time'],'profile':cue['profile']})
            offset += stage['duration']
    if not controls or controls[0]['time'] != 0 or len(controls) > 1024:
        raise ValueError('Control timeline must start at zero')
    result = bytearray(struct.pack('<I',len(controls)))
    previous = -1
    for cue in controls:
        time = float(cue['time'])
        if not math.isfinite(time) or not previous < time < duration:
            raise ValueError('Invalid controller time')
        previous = time
        result += struct.pack('<fI',time,profiles[cue['profile']])
    banks = runtime.get('audio_banks',[])
    cues = runtime.get('audio',[])
    if len(banks) > 64 or len(cues) > 4096: raise ValueError('Too many audio records')
    result += struct.pack('<I',len(banks))
    for bank in banks: result += text(bank)
    result += struct.pack('<I',len(cues))
    previous = -1
    for cue in cues:
        time,volume,pan = float(cue['time']),float(cue.get('volume',1)),float(cue.get('pan',0))
        if not all(map(math.isfinite,[time,volume,pan])) or not 0 <= time < duration or time < previous or not 0 <= volume <= 1 or not -1 <= pan <= 1:
            raise ValueError('Invalid sound cue')
        previous = time
        result += struct.pack('<f',time) + text(cue['sound'])
        result += struct.pack('<ffI',volume,pan,int(bool(cue.get('loop',False))))
    return result, {'control':controls,'audio_banks':banks,'audio':cues,
                    'timing_source':runtime.get('timing_source','port_authored_not_recovered_script')}


def player_track(scene, stage, source, gameplay_glb, gameplay_feet_offset):
    binding = next(a for a in stage['actors'] if a['id'] == 'sarah')
    doc, read = skin.load_glb(source / scene['actors']['sarah']['glb'])
    animation = next(a for a in doc['animations'] if a['name'] == binding['clip'])
    game, read_game = skin.load_glb(gameplay_glb)
    idle = next(a for a in game['animations'] if a['name'] == skin.CLIP_NAMES[0])
    idle_root = skin.evaluate_world_transforms(game,read_game,idle,0)[game['skins'][0]['joints'][0]]
    idle_position = idle_root[:3,3].copy(); idle_position[1] -= gameplay_feet_offset
    inverse_idle_rotation = np.linalg.inv(idle_root[:3,:3])
    samples=[]
    for index, placement in enumerate(binding['motion']['samples']):
        root = skin.evaluate_world_transforms(doc,read,animation,index/binding['motion']['fps'])[doc['skins'][0]['joints'][0]]
        world = skin.compose_transform(np.array(placement[:3]),np.array(placement[3:]),np.ones(3))
        facing = (world[:3,:3] @ root[:3,:3] @ inverse_idle_rotation) @ np.array([0,0,-1])
        yaw = math.atan2(-facing[0],-facing[2])
        quaternion=np.array([0,math.sin(yaw/2),0,math.cos(yaw/2)])
        rotation=skin.compose_transform(np.zeros(3),quaternion,np.ones(3))
        position=(world @ root)[:3,3] - rotation[:3,:3] @ idle_position
        samples.append([*position,*quaternion])
    return {'fps':binding['motion']['fps'],'samples':samples}


def share_textures(output, assets_root):
    assets_root=Path(assets_root)
    shared={hashlib.sha256(p.read_bytes()).digest():'app0:/'+p.relative_to(assets_root).as_posix()
            for p in (assets_root/'characters').rglob('*.bin')}
    for actor in output.iterdir():
        package=actor/'sarah.sk16'
        if not package.exists():continue
        old=package.read_bytes()
        magic,version,batches,joints,clips=struct.unpack_from('<4s4I',old)
        offset=20+(joints*12 if version==2 else 0); result=bytearray(old[:offset])
        for _ in range(batches):
            header=bytearray(old[offset:offset+32]);vertices,indices,palette,length=struct.unpack_from('<4I',header);offset+=32
            path=old[offset:offset+length].decode();offset+=length
            local=actor/Path(path).name
            replacement=shared.get(hashlib.sha256(local.read_bytes()).digest())
            encoded=(replacement or path).encode();struct.pack_into('<I',header,12,len(encoded));result+=header+encoded
            count=palette*2+vertices*16+indices*2;result+=old[offset:offset+count];offset+=count
        result+=old[offset:];package.write_bytes(result)


def build(manifest, output, gameplay_glb, feet_offset=0.0, runtime_root='app0:/assets/cinematics/bedroom', shared_assets=None, timeline_only=False):
    manifest,output = Path(manifest),Path(output)
    scene = json.loads(manifest.read_text(encoding='utf-8'))
    source = manifest.parent
    player_tracks=[player_track(scene,s,source,Path(gameplay_glb),feet_offset) for s in scene['stages']]
    exit_sample=player_tracks[-1]['samples'][-1]
    exit_pose=[*exit_sample[:3],math.degrees(2*math.atan2(exit_sample[4],exit_sample[6]))]
    output.mkdir(parents=True,exist_ok=True)
    if timeline_only:
        for name in scene['actors']:
            if not (output/name/'sarah.sk16').is_file():
                raise ValueError('Timeline-only export requires existing actor: '+name)
    else:
        for name, actor in scene['actors'].items():
            clips = list(dict.fromkeys(a['clip'] for s in scene['stages'] for a in s['actors'] if a['id']==name))
            skin.export(source/actor['glb'],output/name,clip_names=clips,cinematic=True,runtime_root=runtime_root+'/'+name)
        if shared_assets: share_textures(output,shared_assets)
    result = bytearray(struct.pack('<4sI',b'VCN1',3)) + text(manifest.parent.name)
    result += struct.pack('<4fI',*exit_pose,len(scene['stages']))
    for stage_index,stage in enumerate(scene['stages']):
        result += struct.pack('<ffI',stage['duration'],stage['camera']['fov_degrees'],len(stage['actors']))
        for actor in stage['actors']:
            result += text(runtime_root+'/'+actor['id']+'/sarah.sk16') + text(actor['clip']) + track(actor['motion'])
        result += track(stage['camera']) + track(player_tracks[stage_index])
        result += lens_track(stage['camera'])
    runtime_bytes, runtime_report = runtime_tracks(scene,source)
    result += runtime_bytes
    (output/'scene.vcn').write_bytes(result)
    report = {'scene':str(manifest),'duration':sum(s['duration'] for s in scene['stages']),
              'handoff':exit_pose,'camera_fov':'native animated focal length, 36 mm film gate; horizontal FOV',
              'depth_of_field':'original radius and four distance planes exported; blur pass not enabled',
              'runtime':runtime_report}
    (output/'scene.vcn.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--gameplay-glb',required=True,type=Path)
    parser.add_argument('--feet-offset',type=float,default=0.0)
    parser.add_argument('--runtime-root',default='app0:/assets/cinematics/bedroom')
    parser.add_argument('--shared-assets',type=Path,help='Existing app0 staging directory; share byte-identical character textures')
    parser.add_argument('--timeline-only',action='store_true',help='Refresh only timeline and lens; preserve existing SK16 actors')
    args=parser.parse_args()
    build(args.manifest,args.output,args.gameplay_glb,args.feet_offset,args.runtime_root,args.shared_assets,args.timeline_only)
