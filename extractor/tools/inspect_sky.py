import bpy,json
from mathutils import Vector
for o in bpy.context.scene.objects:
 if o.type=='MESH' and '/levels/sky/domes/' in o.name and o.get('nd_export',True):
  print('SKY',o.name, 'bounds',[list(o.matrix_world@Vector(p)) for p in o.bound_box],'UV',list(o.data.uv_layers.keys()),'modifier',[(m.name,m.type) for m in o.modifiers],flush=True)
  for s in o.material_slots:
   m=s.material
   print('MAT',m.name,dict(m.items()),flush=True)
   for n in m.node_tree.nodes:
    print('NODE',n.name,n.type,getattr(n,'uv_map',''),getattr(getattr(n,'image',None),'filepath',''),[(l.from_node.name,l.from_socket.name,l.to_socket.name) for i in n.inputs for l in i.links],flush=True)
