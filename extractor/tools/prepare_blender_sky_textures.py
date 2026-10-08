"""Export native sky textures for Blender without guessing unrelated image nodes."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.texture_handler import TextureHandler
folder=Path(sys.argv[1]); output=folder/'sky_textures';output.mkdir(exist_ok=True)
bindings={}
for path in Path(sys.argv[2]).glob('sky-*-tstrm.pak'):
 handler=TextureHandler(PakFile(str(path)))
 textures=list(handler.textures_by_name.values())
 def role(name):
  if 'moon' in name and 'trans' not in name: return 'moon'
  if 'moon' in name and 'trans' in name:return 'moon_mask'
  if 'sky-' in name and '-color' in name:return 'dome'
 for t in textures:
  key=role(t.name)
  if key:
   _,png=handler.export_texture(t,str(output),export_dds=False,export_png=True)
   if not png:
    print('SKY TEXTURE UNRESOLVED', path.name, t.name, flush=True); continue
   bindings.setdefault(path.name,{})[key]=str(Path(png).resolve())
(folder/'sky_materials.json').write_text(json.dumps(bindings,indent=2))
print('SKY TEXTURES',len(bindings),flush=True)
