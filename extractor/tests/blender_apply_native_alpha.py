import bpy,sys,json,importlib.util
from pathlib import Path
root=Path(sys.argv[sys.argv.index('--')+1]);out=Path('D:/TLOUPS4/AustinStaticLighting')
bpy.ops.wm.open_mainfile(filepath=str(out/'scene_player_preview.blend'),load_ui=False,use_scripts=False)
geometry={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.context.scene.objects if o.type=='MESH'}
visibility={o.name:o.hide_get() for o in bpy.context.scene.objects}
spec=importlib.util.spec_from_file_location('nd_alpha',root/'tlou_extractor/blender_material_alpha.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
report=m.apply_manifest(out/'transparency.json')
assert report['materials']>1500,report
assert not report['ambiguous'] and not report['missing_images'],report
assert report['by_material'].get('hom-houseplant-02') and report['by_material'].get('hom-house-glass-sarahs') and report['by_material'].get('hom-tree-cards'),report
for name in ('blender_streaming_tools.py','blender_material_alpha.py','region_runtime.py'):
    source=(root/'tlou_extractor'/name).read_text(encoding='utf-8')
    text=bpy.data.texts.get(name) or bpy.data.texts.new(name);text.clear();text.write(source);text.use_fake_user=True
    (out/name).write_text(source,encoding='utf-8')
spec2=importlib.util.spec_from_file_location('nd_image_package',root/'tlou_extractor/blender_apply_lighting_batch.py')
pack=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(pack)
report['texture_package']=pack.package_images(out)
assert geometry=={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.context.scene.objects if o.type=='MESH'}
assert visibility=={o.name:o.hide_get() for o in bpy.context.scene.objects}
assert all((out/image.filepath[2:]).is_file() for image in bpy.data.images if image.source=='FILE' and not image.packed_file and image.filepath.startswith('//'))
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.shading.type='SOLID'
            if bpy.context.scene.camera:
                from mathutils import Vector
                camera=bpy.context.scene.camera
                view=area.spaces.active.region_3d;view.view_rotation=camera.matrix_world.to_quaternion()
                view.view_distance=4;view.view_location=camera.matrix_world.translation+camera.matrix_world.to_quaternion()@Vector((0,0,-4));view.view_perspective='PERSP'
report['geometry_preserved']=len(geometry);report['visibility_preserved']=True
report['mask_images']=len({mat.get('nd_transparency_image') for mat in bpy.data.materials if mat.get('nd_transparency_image')})
(out/'transparency_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene_alpha_preview.blend'),compress=True,relative_remap=False)
print('NATIVE ALPHA SAVED',json.dumps(report),flush=True)
