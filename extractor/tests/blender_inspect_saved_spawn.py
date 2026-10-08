"""Read marker objects from saved scenes without loading city geometry or changing scenes."""
import bpy,json,re
from pathlib import Path
results=[]
for source in ['D:/TLOUPS4/AustinStaticLighting/scene_alpha_preview.blend','D:/Новая папка (2)/Untitled.blend']:
    if not Path(source).is_file():continue
    for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
    with bpy.data.libraries.load(source,link=False) as (available,loaded):
        names=[n for n in available.objects if re.sub('[^a-z0-9]','',re.sub(r'\.\d{3}$','',n).lower()) in ('playerstart','playerspawn','spawnpoint')]
        loaded.objects=names
    for obj in loaded.objects:
        current=obj
        while current:
            if current.name not in bpy.context.scene.objects:bpy.context.scene.collection.objects.link(current)
            current=current.parent
    bpy.context.view_layer.update()
    markers=[]
    for obj in loaded.objects:
        evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        p=evaluated.matrix_world.translation
        markers.append({'name':obj.name,'blender_position':list(p),'engine_position':[p.x,p.z,-p.y],'nd_type':obj.get('nd_type')})
    results.append({'source':source,'markers':markers})
Path('D:/TLOUPS4/saved_spawn_inspection.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False),flush=True)
