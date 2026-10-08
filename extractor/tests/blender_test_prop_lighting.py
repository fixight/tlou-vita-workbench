import sys
from pathlib import Path
import bpy
sys.path.insert(0,r'D:\TLOUPS4\fervent-pascal')
from tlou_extractor.blender_prop_lighting import repair_prop_lighting, LAYER
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
def mesh(name, points, faces, lit=None, level='room'):
 data=bpy.data.meshes.new(name);data.from_pydata(points,[],faces)
 obj=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(obj)
 obj['nd_type']='visual';obj['nd_level_id']=level
 if lit is not None:
  attr=data.color_attributes.new(name=LAYER,type='FLOAT_COLOR',domain='POINT')
  for item in attr.data:item.color=(*lit,1)
  obj['nd_static_lighting_mode']='vertex_basis_candidate'
 return obj
wall=mesh('dark wall',[(1,-2,-2),(1,2,-2),(1,2,2),(1,-2,2)],[(0,1,2,3)],(.02,.03,.04))
bright=mesh('bright behind wall',[(2,-2,-2),(2,2,-2),(2,2,2),(2,-2,2)],[(0,1,2,3)],(1,1,1))
prop=mesh('prop',[(0,-.1,0),(0,.1,0),(0,0,.1)],[(0,1,2)])
shared=mesh('shared in other chunk',[],[]);shared.data=prop.data
orphan=mesh('unresolved in other chunk',[(0,0,0),(0,1,0),(0,0,1)],[(0,1,2)],level='empty')
bpy.context.view_layer.update()
common=mesh('shared package actor',[(0,-.1,0),(0,.1,0),(0,0,.1)],[(0,1,2)],level='room-const')
report=repair_prop_lighting([wall,bright,prop,orphan,common],update_preview=False)
assert common.name in report['repaired']
assert max(item.color[0] for item in common.data.color_attributes[LAYER].data)<.03
assert prop.data is not shared.data
assert not shared.data.color_attributes.get(LAYER)
assert orphan.name in report['unresolved']
for item in prop.data.color_attributes[LAYER].data:
 assert all(abs(item.color[i]-expected)<1e-6 for i,expected in enumerate((.02,.03,.04)))
assert repair_prop_lighting([wall,bright,prop],update_preview=False)['repaired']==[]
prop.location.x=1.5;bpy.context.view_layer.update()
assert prop.name in repair_prop_lighting([wall,bright,prop],update_preview=False)['repaired']
print('PASS: wall blocks bright surface, level isolation, shared mesh preserved, idempotence, moved prop recomputed',flush=True)
