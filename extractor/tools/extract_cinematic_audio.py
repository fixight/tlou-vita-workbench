"""Attach native animation SFX and explicitly selected localized voice performances.
No speech silence is trimmed. --voice scene offsets are explicit; defaults are
never inferred from clip duration or filenames.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.streaming.psarc import Psarc
from research.streaming.visibility_base import string_id
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.cinematic_audio import animation_notes, voice_resource, subtitle_metadata, subtitle_text


def build(manifest, game_main, vox_source, voices, engine_tools, output, language='russian',
          runtime_root='app0:/assets/cinematics/bedroom/audio'):
    manifest=Path(manifest)
    scene=json.loads(manifest.read_text(encoding='utf-8'))
    evidence=json.loads((manifest.parent/'evidence.json').read_text(encoding='utf-8'))
    core=Psarc(Path(game_main)/'core.psarc')
    scripts=Psarc(Path(game_main)/'bin.psarc')
    speech=Psarc(Path(game_main)/f'sound1/streams/speech/{language}-sp.psarc')
    vox=scripts.read(vox_source)
    directory=manifest.parent/'audio';directory.mkdir(exist_ok=True)
    names={string_id('sfx-'+Path(n).stem):n for n in core.names if n.startswith('sound1/streams/sfx/') and n.endswith('.xvag')}
    sources={clip['clip']:clip for clip in evidence['clips']}
    cues=[];sounds={};resources=[];stage_time=0
    for stage in scene['stages']:
        for actor in stage['actors']:
            source=sources[actor['clip']]
            pak=PakFile(source['bank'])
            item=next(i for i in pak.get_items('ANIM') if i.name==actor['clip'])
            for note in animation_notes(pak,item,actor['motion']['fps']):
                name_id=note['properties'].get(string_id('name'))
                path=names.get(name_id)
                if not path:continue
                name='sfx-'+Path(path).stem
                file=directory/Path(path).name
                file.write_bytes(core.read(path))
                time=stage_time+note['time']
                cues.append({'time':time,'sound':name,'volume':1,'pan':0,'loop':False,
                             'timing_source':'native_animation_note','frame':note['frame'],
                             'note_offset':note['offset'],'clip':actor['clip']})
                sounds[name]={'name':name,'source':str(file.resolve()),'storage':'stream','bus':'effects'}
                resources.append({'source':path,'file':file.relative_to(manifest.parent).as_posix(),
                                  'name':name,'start_time':time,'status':'native_animation_note'})
        stage_time+=stage['duration']
    for name,time in voices:
        binding=voice_resource(vox,name)
        raw=speech.read(binding['speech_id'])
        metadata=subtitle_metadata(raw)
        if not metadata or metadata['speech_id']!=binding['speech_id']:
            raise ValueError('Localized voice identity mismatch')
        table=core.read(f"text1/{metadata['language_id']}.subtitles")
        for entry in metadata['entries']:
            entry['text']=subtitle_text(table,int(entry['text_id'],16), 'cp1251' if language=='russian' else 'cp1252')
        file=directory/(language+'-'+binding['speech_id']+'.xvag');file.write_bytes(raw)
        sounds[name]={'name':name,'source':str(file.resolve()),'storage':'stream','bus':'dialogue'}
        cues.append({'time':float(time),'sound':name,'volume':1,'pan':0,'loop':False,
                     'timing_source':'explicit_scene_offset_native_stream_preroll_preserved'})
        resources.append({'source':f'sound1/streams/speech/{language}-sp.psarc:{binding["speech_id"]}',
                          'file':file.relative_to(manifest.parent).as_posix(),'name':name,
                          'start_time':float(time),'binding':binding,'subtitles':metadata,
                          'status':'native_localized_performance_preroll_preserved'})
    cues.sort(key=lambda cue:cue['time'])
    sys.path.insert(0,str(engine_tools))
    from build_audio_bank import build as build_bank
    config=directory/'scene.bank.json'
    config.write_text(json.dumps({'sounds':list(sounds.values())},indent=2),encoding='utf-8')
    bank=build_bank(config,Path(output),runtime_root,'scene.vabk')
    runtime_path=manifest.parent/'scene.runtime.json'
    runtime=json.loads(runtime_path.read_text(encoding='utf-8')) if runtime_path.exists() else {}
    runtime.update(audio_banks=[runtime_root+'/scene.vabk'],audio=cues,
                   timing_source='native animation notes; explicit voice offsets with native preroll')
    runtime_path.write_text(json.dumps(runtime,ensure_ascii=False,indent=2),encoding='utf-8')
    scene['audio_resources']=resources
    scene['limitations']=[item for item in scene.get('limitations',[])
                          if item != 'Диалоги, звонок и сценарные события пока не подключены']
    scene['limitations'].append('Звук подключён в VCN движка; браузерный просмотрщик пока без аудио')
    manifest.write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'vox_source':vox_source,'language':language,'audio':cues,'resources':resources,'bank':bank,
            'voice_offset_note':'Zero is an explicitly selected stream origin; native pre-roll silence is kept. Validate scene alignment, not only audible onset.'}
    (directory/'scene.audio.evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'audio':cues,'sounds':len(sounds)},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('--game-main',required=True,type=Path)
    parser.add_argument('--vox-source',required=True)
    parser.add_argument('--voice',action='append',nargs=2,metavar=('NAME','SCENE_SECONDS'),default=[])
    parser.add_argument('--engine-tools',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--runtime-root',required=True)
    parser.add_argument('--language',default='russian',choices=['russian','english'])
    args=parser.parse_args()
    build(args.manifest,args.game_main,args.vox_source,args.voice,args.engine_tools,args.output,args.language,args.runtime_root)
