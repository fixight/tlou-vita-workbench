"""Inspect the prologue car ride without executing the game's scripts.
Usage: python research/car_ride/inspect_car_ride.py IMAGE_MAIN EXTRACTED OUTPUT
"""
import json,math,re,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from research.streaming.psarc import Psarc
from research.streaming.visibility_base import string_id
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.anim_stream_reader import stream_packages
from tlou_extractor.door_interaction_data import spawner_records,animation_entry,compose_rigid,inverse_rigid
from tlou_extractor.cinematic_camera import read_transform_curve

def inspect(image,extracted,output):
    output.mkdir(parents=True,exist_ok=True)
    archive=Psarc(image/'bin.psarc');script_name='dc1/ss-home/ss-hom-road-drive-igc.bin'
    script=archive.read(script_name)
    core=Psarc(image/'core.psarc')
    placements=PakFile(str(extracted/'pak32/hom-const-road-ingame14.pak'))
    locators={s['name']:s for s in spawner_records(placements)}
    segments=[];inventory=[];references=[]
    for index in range(1,7):
        clip_name=f'hom2-drive-chunk{index}-wagoneer';locator_name=f'hom-road-drive-igc-ap-{index}'
        bank=PakFile(str(extracted/f'actor50/hom2-chunk{index}-stream-tstrm.pak'))
        item=next(i for i in bank.get_items('ANIM') if i.name==clip_name)
        entry=animation_entry(bank,item);curve=read_transform_curve(bank,entry['channel_offset'])
        locator=locators[locator_name];ac=bank.read_ptr(item.abs_offset+0x28)
        frames=struct.unpack_from('<H',bank.data,ac+14)[0];fps=struct.unpack_from('<f',bank.data,ac+28)[0]
        if frames!=curve['frame_count'] or fps<=0:raise ValueError('Pose/placement timing mismatch')
        motion=[]
        for sample in curve['samples']:
            if any(abs(v-1)>.005 for v in sample['scale']):raise ValueError('Non-rigid vehicle reference')
            motion.append(compose_rigid(locator,inverse_rigid(sample)))
        distance=sum(math.dist(a['position'],b['position']) for a,b in zip(motion,motion[1:]))
        segments.append({'clip':clip_name,'bank':bank.filepath,'animation_offset':item.abs_offset,
            'locator':locator_name,'locator_position':locator['position'],'locator_rotation_xyzw':locator['rotation_xyzw'],
            'fps':fps,'frames':frames,'duration':(frames-1)/fps,'path_metres':distance,
            'start':motion[0]['position'],'end':motion[-1]['position'],'samples':motion,'packing':curve['flags']})
        for name in (clip_name,locator_name,f'hom2-chunk{index}-stream'):
            offsets=[m.start() for m in re.finditer(re.escape(struct.pack('<I',string_id(name))),script)]
            if not offsets:raise ValueError('Script does not reference '+name)
            references.append({'name':name,'id':f'0x{string_id(name):08x}','script_offsets':offsets})
        stream_name=f'animstream14/igc-stream-hom2-drive-chunk{index}.stm'
        data=core.read(stream_name);roles=set();records=0
        for offset,package in stream_packages(data):
            records+=1
            for animation in package.get_items('ANIM'):roles.add(re.sub(r'-chunk-\d+$','',animation.name))
        if clip_name not in roles:raise ValueError('Missing streamed vehicle clip')
        inventory.append({'name':stream_name,'bytes':len(data),'records':records,'roles':sorted(roles)})
        print(clip_name,round((frames-1)/fps,3),'seconds;',round(distance,2),'metres')
    boundaries=[{'from':a['clip'],'to':b['clip'],'placement_gap_metres':math.dist(a['end'],b['start'])} for a,b in zip(segments,segments[1:])]
    result={'image_main':str(image),'script_archive':'bin.psarc','script_entry':script_name,
        'animation_archive':'core.psarc','segments':segments,'stream_inventory':inventory,
        'script_references':references,'boundaries':boundaries,
        'total_clip_duration':sum(s['duration'] for s in segments),
        'semantics':'locator_world * inverse(apReference(t)); actor reference only',
        'limitations':['Skeletal root motion is not included.','Script waits, animation blends and event times are not decoded.','No assumption of a separate spline route.']}
    (output/'car_ride_evidence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    inspect(*(Path(s) for s in sys.argv[1:4]))
