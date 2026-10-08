import bpy,json
from pathlib import Path
out=Path('D:/TLOUPS4/AustinStaticLighting')
bpy.ops.wm.open_mainfile(filepath=str(out/'scene_alpha_preview.blend'),load_ui=False,use_scripts=False)
materials=[mat for mat in bpy.data.materials if mat.get('nd_transparency_image')]
assert len(materials)>=2224
for mat in materials:
    output=next(n for n in mat.node_tree.nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output)
    assert output.inputs['Surface'].links[0].from_node.get('nd_opacity_role')=='mix',mat.name
    texture=next(n for n in mat.node_tree.nodes if n.get('nd_opacity_role')=='texture')
    assert texture.image.colorspace_settings.name=='Non-Color'
for image in bpy.data.images:
    if image.source=='FILE' and not image.packed_file and image.filepath:
        assert image.filepath.startswith('//'),image.filepath
        assert (out/image.filepath[2:]).is_file(),image.filepath
assert all(bpy.data.texts.get(n) for n in ('blender_streaming_tools.py','blender_material_alpha.py','region_runtime.py'))
assert any(o.get('nd_type')=='streaming_metadata' for o in bpy.context.scene.objects)
report={'reopened':True,'materials':len(materials),'paths_valid':True,'embedded_tools':True}
(out/'transparency_reopen.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('REOPEN VERIFIED',report,flush=True)
