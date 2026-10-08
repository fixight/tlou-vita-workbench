import ast,json,re,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
source=Path(__file__).resolve().parents[1]/'tlou_extractor/blender_material_alpha.py'
functions=[n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ('canonical','apply_manifest')]
class Mat(dict):
    __hash__=object.__hash__
    def __init__(self,name,**props): super().__init__(props);self.name=name
class Scene(dict): pass
class AlphaIdentityTests(unittest.TestCase):
    def test_original_identity_survives_prop_lighting_names(self):
        mat=Mat('pot_plant_native.001_PortLighting.013',nd_diffuse_hash='a',nd_normal_hash='b',nd_material_source='pak')
        self.check(mat,[self.record('leaf')],1)
    def test_ambiguous_identity_is_not_guessed(self):
        mat=Mat('renamed',nd_diffuse_hash='a',nd_normal_hash='b',nd_material_source='pak')
        report=self.check(mat,[self.record('leaf'),self.record('glass','other')],0)
        self.assertEqual(report['ambiguous'],['renamed'])
    def test_existing_mask_is_preserved(self):
        mat=Mat('leaf',nd_diffuse_hash='a',nd_normal_hash='b',nd_material_source='pak',nd_transparency_image='custom')
        self.check(mat,[self.record('leaf')],0)
    @staticmethod
    def record(name,opacity='mask'):
        return dict(old_material=name,material_name=name,diffuse_hash='a',normal_hash='b',source='pak',transparency_hash=opacity,image='mask.png')
    def check(self,mat,records,count):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'transparency.json';path.write_text(json.dumps({'records':records}));(path.parent/'mask.png').touch()
            used=SimpleNamespace(type='MESH',material_slots=[SimpleNamespace(material=mat)])
            bpy=SimpleNamespace(context=SimpleNamespace(scene=Scene()),data=None)
            bpy.context.scene.objects=[used]
            attached=[]
            def attach(m,p,k): attached.append(m.name);return True
            ns=dict(Path=Path,json=json,re=re,bpy=bpy,attach=attach)
            exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),ns)
            report=ns['apply_manifest'](path,missing_only=True)
            self.assertEqual(len(attached),count)
            self.assertEqual(report['materials'],count)
            self.assertEqual(ns['canonical']('leaf_native.001_PortLighting.013'),'leaf')
            return report
if __name__=='__main__':unittest.main()
