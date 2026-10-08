"""Add native static lighting to an existing multi-level editor export."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import shutil

from .static_lighting import export
from .streaming_export import asset_folders
from .editor_export import find_blender


def build(scene_path, blend_path, output):
    output=Path(output).resolve()
    if (output/'scene.blend').exists():
        raise ValueError('Choose a new output directory to preserve the existing scene')
    output.mkdir(parents=True,exist_ok=True)
    scene=json.loads(Path(scene_path).read_text(encoding='utf-8'))
    index={}
    for folder in asset_folders():
        for path in folder.glob('*.pak'): index.setdefault(path.name,path)
    config={'lighting':[],'levels':{},'output':str(output),'source_blend':str(Path(blend_path).resolve())}
    for entry in scene['level_glbs']:
        name=entry['level_id']
        if Path(name).name!=name: raise ValueError('Invalid level identifier')
        raw=Path(entry['path']).read_bytes()
        size=struct.unpack_from('<I',raw,12)[0]
        document=json.loads(raw[20:20+size])
        names={match[1]+'.pak' for node in document['nodes']
               if (match:=re.match(r'^(.+?-tstrm)_',node.get('name','')))}
        if not names: names={name+'-tstrm.pak'}
        paths=[index[n] for n in sorted(names) if n in index]
        lighting_folder=output/'static_lighting'/name
        manifest=export(paths,lighting_folder,owner_level=name)
        config['lighting'].append(str(lighting_folder/'lighting.json'))
        config['levels'][name]={'records':len(manifest['records']),'textures':len(manifest['textures']),
                                'warnings':manifest['warnings'],'missing_paks':sorted(names-index.keys())}
        (output/'lighting_build.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
        print('LIGHTING EXTRACTED',name,len(manifest['records']),'meshes',flush=True)
    for guide in ('STATIC_LIGHTING.md','BLENDER_LEVEL_EDITOR.md'):
        shutil.copyfile(Path(__file__).resolve().parents[1]/guide,output/guide)
    shutil.copyfile(Path(__file__).with_name('blender_streaming_tools.py'),output/'blender_streaming_tools.py')
    with (output/'blender.log').open('w',encoding='utf-8') as log:
        subprocess.run([find_blender(),'--background',str(Path(blend_path).resolve()),
                        '--python-exit-code','1','--python',str(Path(__file__).with_name('blender_apply_lighting_batch.py')),
                        '--',str(output/'lighting_build.json')],stdout=log,stderr=subprocess.STDOUT,
                       check=True,timeout=1800,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print('FULL EDITOR LIGHTING DONE',output/'scene.blend',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene',required=True,type=Path)
    parser.add_argument('--blend',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    build(args.scene,args.blend,args.output)
