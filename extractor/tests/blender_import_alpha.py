import bpy,sys,json,importlib.util
from pathlib import Path
root=Path(sys.argv[sys.argv.index('--')+1]);sys.path.insert(0,str(root))
out=Path('D:/TLOUPS4/AlphaImportTest')
bpy.ops.import_scene.gltf(filepath=str(out/'test.glb'))
from tlou_extractor.blender_export import apply_imported_alpha
report=apply_imported_alpha(out);assert report['materials']==1 and not report['missing'],report
material=bpy.data.materials.get('native_alpha_test')
assert material.get('nd_transparency_hash')=='a1d0d8e29dc316ac'
assert any(n.get('nd_opacity_role')=='mix' for n in material.node_tree.nodes)
print('AUTOMATIC GLB ALPHA IMPORT PASSED',report,flush=True)
