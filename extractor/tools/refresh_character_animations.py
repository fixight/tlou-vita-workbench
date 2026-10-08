"""Replace GLB animations from native banks without re-extracting geometry/textures."""
import argparse,copy,json,struct,sys,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.skeleton_reader import SkeletonReader
from tlou_extractor.anim_reader import AnimationReader
from tlou_extractor.gltf_writer import GLTFWriter

def refresh(path,skeleton_path,banks,backup_root):
 raw=path.read_bytes();size=struct.unpack_from('<I',raw,12)[0]
 doc=json.loads(raw[20:20+size]);bin_size,tag=struct.unpack_from('<I4s',raw,20+size)
 assert tag==b'BIN\x00';binary=raw[28+size:28+size+bin_size]
 skeleton=SkeletonReader.read_skeleton(PakFile(str(skeleton_path)))
 assert skeleton and len(doc['skins'])==1
 joints=doc['skins'][0]['joints'];by_name={doc['nodes'][i]['name']:i for i in joints}
 assert set(by_name)==set(skeleton.bone_by_name),'GLB skin does not match target skeleton'
 joint_nodes=[by_name[b.name] for b in skeleton.bones]
 unique={}
 for bank in dict.fromkeys(banks):
  for clip in AnimationReader.read_animations(PakFile(str(bank)),skeleton):
   unique.setdefault((clip.name,clip.source_rig_id),clip)
 assert unique,'No compatible native clips'
 writer=GLTFWriter(path.stem)
 old_anim_accessors={s[k] for a in doc.get('animations',[]) for s in a['samplers'] for k in ('input','output')}
 geometry_accessors={i for m in doc.get('meshes',[]) for p in m['primitives'] for i in list(p.get('attributes',{}).values())+([p['indices']] if 'indices' in p else [])}
 geometry_accessors.update(s['inverseBindMatrices'] for s in doc['skins'] if 'inverseBindMatrices' in s)
 first=min(old_anim_accessors) if old_anim_accessors else len(doc['accessors'])
 # Native character exports put animations after meshes. Refuse an unexpected
 # layout rather than truncating embedded geometry, images, or morph targets.
 assert not any(p.get('targets') for m in doc['meshes'] for p in m['primitives'])
 assert max(geometry_accessors)<first
 assert not any('bufferView' in image for image in doc.get('images',[]))
 first_view=min(doc['accessors'][i]['bufferView'] for i in old_anim_accessors) if old_anim_accessors else len(doc['bufferViews'])
 prefix=min(doc['bufferViews'][i]['byteOffset'] for i in range(first_view,len(doc['bufferViews']))) if first_view<len(doc['bufferViews']) else len(binary)
 assert all(v.get('byteOffset',0)+v['byteLength']<=prefix for v in doc['bufferViews'][:first_view])
 writer.bin_buffer=bytearray(binary[:prefix]);writer.accessors=copy.deepcopy(doc['accessors'][:first]);writer.buffer_views=copy.deepcopy(doc['bufferViews'][:first_view])
 for clip in unique.values():writer.add_animation(clip,joint_nodes)
 updated=copy.deepcopy(doc);updated['animations']=writer.animations;updated['accessors']=writer.accessors;updated['bufferViews']=writer.buffer_views
 updated['buffers']=[{'byteLength':len(writer.bin_buffer)}]
 updated.setdefault('asset',{}).setdefault('extras',{})['animationBinding']='AC/AH rig signature + named variant mapping, codec revision 4'
 j=json.dumps(updated,separators=(',',':'),ensure_ascii=False).encode();j+=b' '*((-len(j))%4)
 b=bytes(writer.bin_buffer);b+=b'\x00'*((-len(b))%4)
 output=struct.pack('<4sII',b'glTF',2,28+len(j)+len(b))+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(b),b'BIN\x00')+b
 # Prove that all original mesh/skin buffer bytes and document fields survived.
 assert output[28+len(j):28+len(j)+prefix]==binary[:prefix]
 for key in ('nodes','meshes','skins','materials','images','textures','samplers'):
  assert updated.get(key)==doc.get(key),key
 backup=backup_root/path.parent.name/path.name;backup.parent.mkdir(parents=True,exist_ok=True)
 if not backup.exists():shutil.copy2(path,backup)
 tmp=path.with_suffix('.glb.tmp');tmp.write_bytes(output);tmp.replace(path)
 gltf=path.with_suffix('.gltf')
 if gltf.exists():
  for f in (gltf,path.with_suffix('.bin')):
   if f.exists():shutil.copy2(f,backup.parent/f.name)
  external=copy.deepcopy(updated);external['buffers'][0]['uri']=path.with_suffix('.bin').name
  path.with_suffix('.bin').write_bytes(bytes(writer.bin_buffer));gltf.write_text(json.dumps(external,indent=2),encoding='utf-8')
 report={'character':path.parent.name,'old_clips':len(doc.get('animations',[])),'new_clips':len(writer.animations),
         'unsupported':sorted({op for c in unique.values() for op in c.unsupported_opcodes}),
         'geometry_bytes_unchanged':prefix,'source_rigs':sorted({f'{c.source_rig_id:08x}' for c in unique.values()}),'target_rig':f'{skeleton.native_rig_id:08x}'}
 print(json.dumps(report),flush=True);return report

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('glb',type=Path);p.add_argument('--skeleton',required=True,type=Path);p.add_argument('--bank',required=True,action='append',type=Path);p.add_argument('--backup',required=True,type=Path)
 a=p.parse_args();refresh(a.glb,a.skeleton,a.bank,a.backup)
