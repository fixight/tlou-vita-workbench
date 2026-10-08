"""Rebind decoded source-resolution textures and verify Solid preview nodes."""
import bpy
import importlib.util
import json
from pathlib import Path
import re

root=Path(__file__).resolve().parents[1]
folder=root/'editor_exports/austin_editor'
manifest=json.loads((folder/'texture_hq_manifest.json').read_text(encoding='utf-8'))
bpy.ops.wm.open_mainfile(filepath=str(folder/'scene_streaming_preview.blend'))
geometry={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.context.scene.objects if o.type=='MESH'}
images={}
replaced=0
missing=set()
for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    for node in mat.node_tree.nodes:
        if node.type != 'TEX_IMAGE' or not node.image:
            continue
        old=node.image
        name=re.sub(r'\.\d{3}$','',old.name).removesuffix('.png')
        entry=manifest.get(name)
        if not entry or 'error' in entry:
            missing.add(name)
            continue
        key=(entry['png'],old.colorspace_settings.name)
        if key not in images:
            image=bpy.data.images.load(entry['png'],check_existing=False)
            image.colorspace_settings.name=old.colorspace_settings.name
            image['nd_source_hash']=entry.get('hash','')
            image['nd_source_width']=entry['w']
            image['nd_source_height']=entry['h']
            assert tuple(image.size)==(entry['w'],entry['h'])
            images[key]=image
        node.image=images[key]
        replaced+=1
source=root/'tlou_extractor/blender_streaming_tools.py'
spec=importlib.util.spec_from_file_location('hq_tools',source)
tools=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)
tools.register()
previews=0
for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    shader=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
    if shader and shader.inputs['Base Color'].links:
        texture=shader.inputs['Base Color'].links[0].from_node
        if texture.type=='TEX_IMAGE':
            assert mat.node_tree.nodes.active==texture
            previews+=1
for image in list(bpy.data.images):
    if image.users==0 and image.name!='Render Result':
        bpy.data.images.remove(image)
# Keep HQ PNGs external so Blender can adjust/relink them without repacking
# the entire texture library into each scene revision.
scene=bpy.context.scene
scene.render.use_simplify=False
assert geometry=={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in scene.objects if o.type=='MESH'}
assert len(tools.metadata()['regions'])==221
text=bpy.data.texts.get(source.name) or bpy.data.texts.new(source.name)
text.clear()
text.write(source.read_text(encoding='utf-8'))
destination=folder/'scene_textures_hq.blend'
print('Saving HQ scene',str(destination),folder.exists(),flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(destination),compress=True)
report={'replaced_texture_nodes':replaced,'unique_hq_images':len(images),'solid_material_previews':previews,
        'unresolved_names':sorted(missing),'preserved_meshes':len(geometry),'regions':221,
        'image_sizes':{Path(path).name:list(image.size) for (path,space),image in images.items()}}
(folder/'texture_hq_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(folder/source.name).write_text(source.read_text(encoding='utf-8'),encoding='utf-8')
print('HQ BLENDER PASSED',replaced,len(images),previews,sorted(missing),flush=True)
