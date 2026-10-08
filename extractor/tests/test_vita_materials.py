"""Exercise the real texture export and material sidecar writer outside Blender."""
import ast
import hashlib
import math
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
import numpy as np

source=Path(__file__).resolve().parents[1]/'tlou_extractor/blender_vita_export.py'
tree=ast.parse(source.read_text(encoding='utf-8'))
functions=[node for node in tree.body if isinstance(node,ast.FunctionDef)
           and node.name in ('export_texture','resize_rgba','write_material_settings')]
images={}
namespace={'np':np,'hashlib':hashlib,'math':math,'struct':struct,
           'bpy':SimpleNamespace(data=SimpleNamespace(images=images)),
           'albedo':lambda mat: SimpleNamespace(image=mat.image),
           'pixels':lambda image,cache: image.rgba.copy()}
exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),namespace)

class Material(dict):
    def __init__(self,name,mode,alpha=(1.,1.)):
        super().__init__(nd_alpha_mode=mode)
        self.name=name
        self.use_nodes=False
        self.use_backface_culling=True
        self.image=SimpleNamespace(is_float=False,colorspace_settings=SimpleNamespace(name='Raw'),
                                  rgba=np.array([[[.2,.3,.4,a] for a in alpha]],dtype=np.float32))

class MaterialExportTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        (self.root/'assets/textures').mkdir(parents=True)
        (self.root/'assets/metadata').mkdir()
        self.report={'texture_dimensions':{},'alpha_materials':[],'material_settings':{}}
        self.exported={}
    def export(self,mat):
        return namespace['export_texture'](mat,self.root,{},self.exported,self.report)
    def alpha(self,path):
        data=(self.root/path.replace('app0:/','')).read_bytes()
        return list(data[15::4])
    def test_shared_pixels_different_modes_do_not_share_material(self):
        opaque=self.export(Material('opaque','OPAQUE'))
        glass=self.export(Material('glass','BLEND'))
        self.assertNotEqual(opaque,glass)
        self.assertEqual(self.report['material_settings'][glass]['alpha_mode'],'BLEND')
    def test_native_cutout_is_baked_into_rgba(self):
        mat=Material('leaves','MASK')
        mat['nd_transparency_image']='mask'
        images['mask']=SimpleNamespace(rgba=np.array([[[.2,0,0,1],[.8,0,0,1]]],dtype=np.float32))
        self.assertEqual(self.alpha(self.export(mat)),[0,255])
    def test_glass_keeps_fractional_alpha(self):
        self.assertEqual(self.alpha(self.export(Material('glass','BLEND',(.25,.75)))),[64,191])
    def test_sidecar_binary_layout(self):
        mat=Material('leaves','MASK')
        mat['nd_alpha_cutoff']=.3
        mat['nd_double_sided']=True
        path=self.export(mat)
        namespace['write_material_settings'](self.root,self.report['material_settings'])
        data=(self.root/'assets/metadata/materials.bin').read_bytes()
        self.assertEqual(struct.unpack_from('<4sI',data),(b'MAT1',1))
        length,=struct.unpack_from('<H',data,8)
        self.assertEqual(data[10:10+length].decode(),path)
        mode,two_sided,cutoff=struct.unpack_from('<BBf',data,10+length)
        self.assertEqual((mode,two_sided),(1,1))
        self.assertAlmostEqual(cutoff,.3)
        self.assertEqual(len(data),10+length+6)
    def test_byte_srgb_keeps_original_encoded_color(self):
        mat=Material('png','OPAQUE')
        mat.image.colorspace_settings.name='sRGB'
        mat.image.rgba[:,:,:3]=np.array([16,32,64])/255
        payload=(self.root/self.export(mat).removeprefix('app0:/')).read_bytes()
        self.assertEqual(list(payload[12:15]),[16,32,64])
    def test_scene_linear_float_is_encoded_once(self):
        mat=Material('exr','OPAQUE');mat.image.is_float=True
        mat.image.colorspace_settings.name='Linear Rec.709'
        mat.image.rgba[:,:,:3]=.0031308
        payload=(self.root/self.export(mat).removeprefix('app0:/')).read_bytes()
        self.assertEqual(list(payload[12:15]),[10,10,10])
    def test_invalid_mode_and_cutoff_rejected(self):
        with self.assertRaises(ValueError):self.export(Material('bad','UNKNOWN'))
        mat=Material('bad cutoff','MASK');mat['nd_alpha_cutoff']=float('nan')
        with self.assertRaises(ValueError):self.export(mat)

if __name__=='__main__':unittest.main()
