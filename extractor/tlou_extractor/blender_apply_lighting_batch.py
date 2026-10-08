"""Blender batch adapter; preserve the existing geometry, editor and visibility."""
import importlib.util
import json
from pathlib import Path
import sys
import hashlib
import shutil
from collections import Counter

import bpy


def package_images(output):
    """Make the new editor folder self-contained without packing all HDR buffers."""
    copied={}; total=0
    for image in bpy.data.images:
        if image.source!='FILE' or not image.filepath or image.packed_file: continue
        source=Path(bpy.path.abspath(image.filepath)).resolve()
        if not source.is_file(): raise ValueError('Missing image: '+str(source))
        if source.is_relative_to(output):
            target=source
        else:
            if source not in copied:
                target=output/'textures'/(hashlib.sha256(str(source).encode()).hexdigest()[:20]+source.suffix)
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target); copied[source]=target; total+=target.stat().st_size
            target=copied[source]
        image.filepath='//'+target.relative_to(output).as_posix()
    return {'copied_textures':len(copied),'copied_bytes':total}


def run(config_path):
    config=json.loads(Path(config_path).read_text(encoding='utf-8'))
    output=Path(config['output'])
    spec=importlib.util.spec_from_file_location('nd_static_batch',Path(__file__).with_name('blender_static_lighting.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    geometry={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.context.scene.objects if o.type=='MESH'}
    visibility={o.name:(o.hide_get(),o.hide_render) for o in bpy.context.scene.objects if o.type=='MESH'}
    summary={'experimental':True,'levels':{},'modes':{},'matched':0,'geometry_preserved':len(geometry)}
    modes=Counter()
    for path in config['lighting']:
        level=Path(path).parent.name
        report=module.apply_lighting(path,configure_view=False)
        summary['levels'][level]={'matched':report['matched'],'modes':report['modes'],
                                  'unmatched':len(report['unmatched']),'source':config['levels'][level]}
        summary['matched']+=report['matched'];modes.update(report['modes'])
        summary['modes']=dict(modes)
        (output/'lighting_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        print('LIGHTING APPLIED',level,report['matched'],report['modes'],flush=True)
    assert geometry=={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.context.scene.objects if o.type=='MESH'}
    assert visibility=={o.name:(o.hide_get(),o.hide_render) for o in bpy.context.scene.objects if o.type=='MESH'}
    module.configure_preview_view()
    bpy.context.scene['nd_static_lighting_manifests']=json.dumps(config['lighting'])
    runtime=Path(__file__).with_name('region_runtime.py')
    core=bpy.data.texts.get(runtime.name) or bpy.data.texts.new(runtime.name)
    core.clear();core.write(runtime.read_text(encoding='utf-8'));core.use_fake_user=True
    alpha_path=Path(__file__).with_name('blender_material_alpha.py')
    alpha_spec=importlib.util.spec_from_file_location('nd_batch_alpha',alpha_path)
    alpha=importlib.util.module_from_spec(alpha_spec);alpha_spec.loader.exec_module(alpha)
    alpha.toggle(bpy.context.scene)
    alpha_text=bpy.data.texts.get(alpha_path.name) or bpy.data.texts.new(alpha_path.name)
    alpha_text.clear();alpha_text.write(alpha_path.read_text(encoding='utf-8'));alpha_text.use_fake_user=True
    tools=Path(__file__).with_name('blender_streaming_tools.py')
    text=bpy.data.texts.get(tools.name) or bpy.data.texts.new(tools.name)
    text.clear();text.write(tools.read_text(encoding='utf-8'));text.use_fake_user=True
    summary['texture_package']=package_images(output)
    (output/'lighting_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    # Keep HDR maps external to avoid loading and packing every city atlas at once.
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'scene.blend'),compress=True,relative_remap=False)
    print('BATCH LIGHTING SAVED',summary['matched'],dict(modes),'geometry',len(geometry),flush=True)


if __name__=='__main__':
    run(sys.argv[sys.argv.index('--')+1])
