from pathlib import Path
import json,struct,copy,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.skeleton_reader import SkeletonReader
from tlou_extractor.anim_reader import AnimationReader
from tlou_extractor.gltf_writer import GLTFWriter
source=Path('D:/TLOUPS4/fervent-pascal/extracted_models/sarah/sarah.glb')
raw=source.read_bytes();size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size]);length=struct.unpack_from('<I',raw,20+size)[0];binary=raw[28+size:28+size+length]
rig=SkeletonReader.read_skeleton(PakFile('D:/TLOUPS4/Extracted/actor50/sarah-skel-tstrm.pak'))
pak=PakFile('D:/TLOUPS4/Extracted/actor50/hom1-tstrm.pak');name='hom1-house-door-push--sarah';clip=AnimationReader._parse_clip(pak,next(i for i in pak.get_items('ANIM') if i.name==name),rig)
writer=GLTFWriter('sarah');writer.bin_buffer=bytearray(binary);writer.accessors=copy.deepcopy(doc['accessors']);writer.buffer_views=copy.deepcopy(doc['bufferViews'])
nodes={doc['nodes'][i]['name']:i for i in doc['skins'][0]['joints']};writer.add_animation(clip,[nodes[b.name] for b in rig.bones])
doc['animations'].extend(writer.animations);doc['accessors']=writer.accessors;doc['bufferViews']=writer.buffer_views;doc['buffers']=[{'byteLength':len(writer.bin_buffer)}]
j=json.dumps(doc,separators=(',',':')).encode();j+=b' '*(-len(j)%4);b=bytes(writer.bin_buffer);b+=b'\0'*(-len(b)%4)
output=struct.pack('<4sII',b'glTF',2,28+len(j)+len(b))+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(b),b'BIN\0')+b
assert bytes(writer.bin_buffer[:len(binary)])==binary
path=source.with_name('sarah_door_process.glb');path.write_bytes(output);print(path)
