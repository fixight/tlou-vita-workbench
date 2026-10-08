import bpy
from pathlib import Path
root=Path('C:/Users/egors/Documents/antigravity/fervent-pascal')
out=Path('D:/TLOUPS4/AustinStaticLighting')
bpy.ops.wm.open_mainfile(filepath=str(out/'scene_player_preview.blend'),load_ui=False,use_scripts=False)
print('PLAYER PACKAGE OPEN',flush=True)
for name in ('blender_streaming_tools.py','region_runtime.py'):
    source=(root/'tlou_extractor'/name).read_text(encoding='utf-8')
    t=bpy.data.texts.get(name) or bpy.data.texts.new(name)
    t.clear();t.write(source);t.use_fake_user=True
    (out/name).write_text(source,encoding='utf-8')
bpy.context.scene['nd_player_sim_enabled']=False
bpy.context.scene['nd_player_report']='{}'
report=bpy.data.texts.get('TLOU_PLAYER_PREVIEW.json')
if report:report.clear();report.write('{}')
assert sum(o.get('nd_type')=='visual' for o in bpy.context.scene.objects)==9582
assert all((out/image.filepath[2:]).is_file() for image in bpy.data.images if image.source=='FILE' and image.filepath.startswith('//'))
bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene_player_preview.blend'),compress=True,relative_remap=False)
print('PLAYER PACKAGE UPDATED',flush=True)
